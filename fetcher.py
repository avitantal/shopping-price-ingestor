"""
Download the latest PriceFull XML file for a given chain.

- Shufersal: HTTPS via prices.shufersal.co.il listing (Azure Blob SAS URLs)
- FTP chains: ftplib connecting to url.retail.publishedprices.co.il
"""

import ftplib
import gzip
import hashlib
import html
import io
import re
from dataclasses import dataclass

import requests

from chains import ChainConfig, FTP_HOST, SHUFERSAL_BASE_URL, USER_AGENT

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = USER_AGENT


@dataclass
class FetchedFile:
    file_name: str
    sha256: str       # hex digest of the compressed bytes (dedup key)
    stream: io.BytesIO  # decompressed XML, seeked to position 0


def fetch_latest_price_full(chain: ChainConfig, ftp_password: str | None = None) -> FetchedFile:
    if chain.access_type == "https_shufersal":
        return _fetch_shufersal(chain)
    if chain.access_type == "ftp":
        if not ftp_password:
            raise ValueError(f"ftp_password required for {chain.chain_code}")
        return _fetch_ftp(chain, ftp_password)
    raise ValueError(f"Unknown access_type: {chain.access_type}")


# ── Shufersal (HTTPS / Azure Blob) ──────────────────────────────────────────

_SHUFERSAL_LISTING_URL = f"{SHUFERSAL_BASE_URL}/FileObject/UpdateCategory"
_SHUFERSAL_LISTING_PARAMS = {"catID": "5", "storeId": "0", "pageSizeCount": "50"}


def _fetch_shufersal(chain: ChainConfig) -> FetchedFile:
    resp = _SESSION.get(_SHUFERSAL_LISTING_URL, params=_SHUFERSAL_LISTING_PARAMS, timeout=30)
    resp.raise_for_status()

    file_name, download_url = _pick_shufersal_file(resp.text, chain.gs1_id)

    gz_resp = _SESSION.get(download_url, timeout=120, stream=True)
    gz_resp.raise_for_status()

    compressed = gz_resp.content
    return _decompress(file_name, compressed)


def _pick_shufersal_file(html_text: str, gs1_id: str) -> tuple[str, str]:
    """
    Returns (file_name, url) for the first PriceFull file matching gs1_id.
    Shufersal's listing page embeds Azure Blob SAS URLs in anchor href attributes.
    The HTML may have &amp;-encoded query strings.
    """
    # Match any URL that contains the PriceFull filename
    pattern = re.compile(
        r'href=["\']([^"\']*PriceFull' + re.escape(gs1_id) + r'[^"\']*\.gz[^"\']*)["\']',
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(html_text))
    if not matches:
        raise RuntimeError(f"No PriceFull{gs1_id} files found in Shufersal listing")

    raw_url = html.unescape(matches[0].group(1))
    # Extract clean filename from path component
    name_match = re.search(r'(PriceFull[^/?]+\.gz)', raw_url, re.IGNORECASE)
    if not name_match:
        raise RuntimeError(f"Cannot parse file name from URL: {raw_url}")
    return name_match.group(1), raw_url


# ── FTP chains ───────────────────────────────────────────────────────────────

def _fetch_ftp(chain: ChainConfig, password: str) -> FetchedFile:
    with ftplib.FTP(FTP_HOST, timeout=60) as ftp:
        ftp.set_pasv(True)
        ftp.login(user=chain.ftp_user, passwd=password)

        all_files = ftp.nlst(".")
        candidates = [
            f for f in all_files
            if re.match(
                r"PriceFull" + re.escape(chain.gs1_id) + r".*\.gz$",
                f.split("/")[-1],   # strip any path prefix
                re.IGNORECASE,
            )
        ]

        if not candidates:
            raise RuntimeError(f"No PriceFull files on FTP for chain {chain.chain_code}")

        # Most-recent file sorts last lexicographically (date is in the name)
        file_path = sorted(candidates)[-1]
        file_name = file_path.split("/")[-1]

        buf = io.BytesIO()
        ftp.retrbinary(f"RETR {file_path}", buf.write)
        buf.seek(0)

    return _decompress(file_name, buf.read())


# ── Shared helpers ────────────────────────────────────────────────────────────

def _decompress(file_name: str, compressed: bytes) -> FetchedFile:
    sha256 = hashlib.sha256(compressed).hexdigest()
    xml_bytes = gzip.decompress(compressed)
    return FetchedFile(
        file_name=file_name,
        sha256=sha256,
        stream=io.BytesIO(xml_bytes),
    )
