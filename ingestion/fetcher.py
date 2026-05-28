import ftplib
import gzip
import html as html_mod
import io
import re
from typing import Optional

import requests

from chains import CHAINS, FTP_HOST

HEADERS = {"User-Agent": "ShoppingListApp/1.0 (avitantal@gmail.com)"}

FTP_TIMEOUT = 90   # seconds — FTP server can be slow to respond


def _list_shufersal_files() -> list[dict]:
    """Scrape Shufersal HTML listing (catID=2) for PriceFull download links."""
    r = requests.get(
        "https://prices.shufersal.co.il/FileObject/UpdateCategory",
        params={"catID": "2", "storeId": "0", "page": "1", "size": "50"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    results = []
    for match in re.finditer(r'href="([^"]*PriceFull[^"]*\.gz[^"]*)"', r.text):
        url = html_mod.unescape(match.group(1))
        fname = url.split("?")[0].split("/")[-1]
        results.append({"fname": fname, "url": url})
    return results


def _list_ftp_files(ftp_user: str) -> list[str]:
    with ftplib.FTP(FTP_HOST, timeout=FTP_TIMEOUT) as ftp:
        ftp.login(user=ftp_user, passwd="")
        files = ftp.nlst()
    return sorted(
        [f for f in files if "PriceFull" in f and f.endswith(".gz")],
        reverse=True,
    )


def _download_ftp(ftp_user: str, filename: str) -> bytes:
    buf = io.BytesIO()
    with ftplib.FTP(FTP_HOST, timeout=FTP_TIMEOUT) as ftp:
        ftp.login(user=ftp_user, passwd="")
        ftp.retrbinary(f"RETR {filename}", buf.write)
    buf.seek(0)
    with gzip.open(buf) as f:
        return f.read()


def _download_web(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    with gzip.open(io.BytesIO(r.content)) as f:
        return f.read()


def get_latest_pricefull(chain_code: str) -> Optional[tuple[str, bytes]]:
    """Return (filename, xml_bytes) for the newest PriceFull file, or None."""
    cfg = CHAINS[chain_code]

    if cfg["access"] == "web":
        files = _list_shufersal_files()
        if not files:
            return None
        files.sort(key=lambda x: x["fname"], reverse=True)
        f = files[0]
        return f["fname"], _download_web(f["url"])

    # ftp
    files = _list_ftp_files(cfg["ftp_user"])
    if not files:
        return None
    return files[0], _download_ftp(cfg["ftp_user"], files[0])
