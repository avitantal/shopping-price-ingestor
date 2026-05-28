import json
import pytest
from unittest.mock import MagicMock, patch, call

from parser import PriceRow
from uploader import upload_price_rows, BATCH_SIZE


def make_rows(n: int) -> list[PriceRow]:
    return [
        PriceRow(
            barcode=f"{i:013d}",
            item_name=f"product {i}",
            price=float(i) + 0.99,
            updated_at="2026-05-28T03:40:00+00:00",
        )
        for i in range(1, n + 1)
    ]


# ── Batch sizing ─────────────────────────────────────────────────────────────

def test_single_batch_for_small_input(mock_post):
    rows = make_rows(10)
    upload_price_rows(rows, "test_chain", "file.gz", "abc123", "http://edge/ingest", "secret")
    assert mock_post.call_count == 1
    payload = json.loads(mock_post.call_args.kwargs["data"])
    assert payload["is_final"] is True
    assert len(payload["rows"]) == 10


def test_multiple_batches_for_large_input(mock_post):
    rows = make_rows(BATCH_SIZE + 1)
    upload_price_rows(rows, "test_chain", "file.gz", "abc123", "http://edge/ingest", "secret")
    assert mock_post.call_count == 2
    # First batch not final
    first = json.loads(mock_post.call_args_list[0].kwargs["data"])
    assert first["is_final"] is False
    assert len(first["rows"]) == BATCH_SIZE
    # Last batch is final
    last = json.loads(mock_post.call_args_list[1].kwargs["data"])
    assert last["is_final"] is True
    assert len(last["rows"]) == 1


def test_exactly_one_batch_size(mock_post):
    rows = make_rows(BATCH_SIZE)
    upload_price_rows(rows, "test_chain", "file.gz", "abc123", "http://edge/ingest", "secret")
    assert mock_post.call_count == 1
    payload = json.loads(mock_post.call_args.kwargs["data"])
    assert payload["is_final"] is True
    assert len(payload["rows"]) == BATCH_SIZE


def test_three_batches(mock_post):
    rows = make_rows(BATCH_SIZE * 2 + 50)
    upload_price_rows(rows, "test_chain", "file.gz", "abc123", "http://edge/ingest", "secret")
    assert mock_post.call_count == 3
    finals = [json.loads(c.kwargs["data"])["is_final"] for c in mock_post.call_args_list]
    assert finals == [False, False, True]


# ── Payload shape ─────────────────────────────────────────────────────────────

def test_payload_fields(mock_post):
    rows = make_rows(1)
    upload_price_rows(rows, "shufersal", "PriceFull.gz", "deadbeef", "http://x/ingest", "tok")
    payload = json.loads(mock_post.call_args.kwargs["data"])
    assert payload["chain_code"] == "shufersal"
    assert payload["file_name"] == "PriceFull.gz"
    assert payload["sha256"] == "deadbeef"
    row = payload["rows"][0]
    assert set(row.keys()) == {"barcode", "item_name", "price", "updated_at"}


def test_auth_header(mock_post):
    rows = make_rows(1)
    upload_price_rows(rows, "shufersal", "f.gz", "abc", "http://x/ingest", "my-secret")
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer my-secret"


# ── Error handling ────────────────────────────────────────────────────────────

def test_raises_on_http_error(mock_post):
    mock_post.return_value.raise_for_status.side_effect = Exception("HTTP 401")
    rows = make_rows(1)
    with pytest.raises(Exception, match="HTTP 401"):
        upload_price_rows(rows, "shufersal", "f.gz", "abc", "http://x/ingest", "tok")


def test_empty_rows_sends_no_requests(mock_post):
    upload_price_rows([], "shufersal", "f.gz", "abc", "http://x/ingest", "tok")
    assert mock_post.call_count == 0


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_post():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"status": "ok"}
    with patch("uploader.requests.post", return_value=mock_resp) as m:
        yield m
