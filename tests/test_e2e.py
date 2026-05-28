"""
End-to-end pipeline test: XML → parse → upload.
All network calls are mocked — this runs offline in CI.
"""

import gzip
import hashlib
import io
import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from fetcher import FetchedFile, _decompress
from parser import parse_price_full
from uploader import upload_price_rows, BATCH_SIZE


def _make_price_xml(n_items: int) -> bytes:
    items = "\n".join(
        f"""    <Item>
      <ItemCode>{1_000_000_000_000 + i}</ItemCode>
      <ItemName>מוצר {i}</ItemName>
      <ItemPrice>{(i % 50) + 1}.90</ItemPrice>
      <PriceUpdateDate>2026-05-28 03:40:00</PriceUpdateDate>
    </Item>"""
        for i in range(1, n_items + 1)
    )
    xml = f"<Root><Items>\n{items}\n</Items></Root>"
    return xml.encode("utf-8")


def _make_gz_file(n_items: int) -> tuple[str, bytes]:
    """Returns (file_name, compressed_bytes)."""
    xml_bytes = _make_price_xml(n_items)
    compressed = gzip.compress(xml_bytes)
    sha = hashlib.sha256(compressed).hexdigest()
    name = f"PriceFull7290027600007-001-357-20260528-034000.gz"
    return name, compressed


# ── parse ↔ uploader integration ────────────────────────────────────────────

def test_parse_and_upload_small(mock_post):
    """Small payload: one batch, is_final=True."""
    file_name, compressed = _make_gz_file(100)
    fetched = _decompress(file_name, compressed)

    rows = list(parse_price_full(fetched.stream))
    assert len(rows) == 100

    upload_price_rows(rows, "shufersal", fetched.file_name, fetched.sha256,
                      "http://edge/ingest", "secret")

    assert mock_post.call_count == 1
    payload = json.loads(mock_post.call_args.kwargs["data"])
    assert payload["chain_code"] == "shufersal"
    assert payload["is_final"] is True
    assert len(payload["rows"]) == 100


def test_parse_and_upload_large(mock_post):
    """Large payload: multiple batches, only last is final."""
    n = BATCH_SIZE * 2 + 300
    file_name, compressed = _make_gz_file(n)
    fetched = _decompress(file_name, compressed)

    rows = list(parse_price_full(fetched.stream))
    assert len(rows) == n

    upload_price_rows(rows, "rami_levy", fetched.file_name, fetched.sha256,
                      "http://edge/ingest", "secret")

    assert mock_post.call_count == 3
    finals = [json.loads(c.kwargs["data"])["is_final"] for c in mock_post.call_args_list]
    assert finals == [False, False, True]
    total_rows = sum(len(json.loads(c.kwargs["data"])["rows"]) for c in mock_post.call_args_list)
    assert total_rows == n


def test_sha256_consistent(mock_post):
    """SHA256 in every batch is the sha256 of the compressed file."""
    file_name, compressed = _make_gz_file(50)
    expected_sha = hashlib.sha256(compressed).hexdigest()
    fetched = _decompress(file_name, compressed)
    assert fetched.sha256 == expected_sha

    rows = list(parse_price_full(fetched.stream))
    upload_price_rows(rows, "shufersal", fetched.file_name, fetched.sha256,
                      "http://edge/ingest", "secret")

    payload = json.loads(mock_post.call_args.kwargs["data"])
    assert payload["sha256"] == expected_sha


def test_row_payload_shape(mock_post):
    """Each row in the payload has exactly the four required fields."""
    file_name, compressed = _make_gz_file(5)
    fetched = _decompress(file_name, compressed)
    rows = list(parse_price_full(fetched.stream))
    upload_price_rows(rows, "shufersal", fetched.file_name, fetched.sha256,
                      "http://edge/ingest", "secret")

    payload = json.loads(mock_post.call_args.kwargs["data"])
    for row in payload["rows"]:
        assert set(row.keys()) == {"barcode", "item_name", "price", "updated_at"}
        assert isinstance(row["price"], float)
        assert row["updated_at"].endswith("+00:00")


# ── run.py orchestration ──────────────────────────────────────────────────────

def test_run_main_success(tmp_path):
    """run.main() calls fetch → parse → upload for each chain."""
    import os, run
    from chains import CHAINS

    n_items = 20
    xml = _make_price_xml(n_items)
    compressed = gzip.compress(xml)
    sha = hashlib.sha256(compressed).hexdigest()

    mock_fetched = FetchedFile(
        file_name="PriceFull7290027600007-001.gz",
        sha256=sha,
        stream=io.BytesIO(gzip.decompress(compressed)),
    )

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"status": "ok"}

    env = {"INGEST_URL": "http://edge/ingest", "INGEST_KEY": "tok", "FTP_PASSWORD": "pw"}

    with patch.dict(os.environ, env), \
         patch("run.fetch_latest_price_full", return_value=mock_fetched) as mock_fetch, \
         patch("uploader.requests.post", return_value=mock_resp) as mock_post:
        # Refresh stream for each chain call
        def fresh_fetched(*args, **kwargs):
            return FetchedFile(
                file_name="PriceFull.gz",
                sha256=sha,
                stream=io.BytesIO(gzip.decompress(compressed)),
            )
        mock_fetch.side_effect = fresh_fetched

        exit_code = run.main(["shufersal"])

    assert exit_code == 0
    assert mock_fetch.call_count == 1
    assert mock_post.call_count == 1


def test_run_main_chain_failure_returns_1(tmp_path):
    """run.main() returns exit code 1 if any chain fails."""
    import os, run

    env = {"INGEST_URL": "http://edge/ingest", "INGEST_KEY": "tok", "FTP_PASSWORD": "pw"}
    with patch.dict(os.environ, env), \
         patch("run.fetch_latest_price_full", side_effect=RuntimeError("FTP timeout")):
        exit_code = run.main(["shufersal"])

    assert exit_code == 1


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_post():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"status": "ok"}
    with patch("uploader.requests.post", return_value=mock_resp) as m:
        yield m
