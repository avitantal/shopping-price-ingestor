import gzip
import html as html_mod
import io
import json
import re
import subprocess
from typing import Optional

import requests

from chains import CHAINS, FTP_HOST

HEADERS = {"User-Agent": "ShoppingListApp/1.0 (avitantal@gmail.com)"}


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


def _list_carrefour_files() -> list[dict]:
    """Scrape Carrefour portal: extract const files JSON and path from page."""
    r = requests.get(
        "https://prices.carrefour.co.il/",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    path_m = re.search(r"const path\s*=\s*'(\d+)'", r.text)
    files_m = re.search(r"const files\s*=\s*(\[.*?\]);", r.text, re.DOTALL)
    if not path_m or not files_m:
        return []
    path = path_m.group(1)
    files = json.loads(files_m.group(1))
    return [
        {
            "fname": f["name"],
            "url": f"https://prices.carrefour.co.il/{path}/{f['name']}",
        }
        for f in files
        if "PriceFull" in f.get("name", "")
    ]


def _curl_ftp(url: str, extra_args: list[str] | None = None) -> bytes:
    """Run curl for FTP — handles PASV/PORT negotiation better than ftplib."""
    cmd = [
        "curl", "-s", "--ftp-pasv", "--retry", "2",
        "--connect-timeout", "30", "--max-time", "120",
        "-A", "ShoppingListApp/1.0 (avitantal@gmail.com)",
    ] + (extra_args or []) + [url]
    result = subprocess.run(cmd, capture_output=True, timeout=150)
    if result.returncode != 0:
        raise RuntimeError(f"curl FTP failed (rc={result.returncode}): {result.stderr.decode()[:300]}")
    return result.stdout


def _list_ftp_files(ftp_user: str) -> list[str]:
    url = f"ftp://{ftp_user}:@{FTP_HOST}/"
    raw = _curl_ftp(url, ["--list-only"])
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return sorted(
        [ln.strip() for ln in lines if "PriceFull" in ln and ln.strip().endswith(".gz")],
        reverse=True,
    )


def _download_ftp(ftp_user: str, filename: str) -> bytes:
    url = f"ftp://{ftp_user}:@{FTP_HOST}/{filename}"
    gz_data = _curl_ftp(url)
    with gzip.open(io.BytesIO(gz_data)) as f:
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
    elif cfg["access"] == "carrefour":
        files = _list_carrefour_files()
    else:
        files = None

    if files is not None:
        if not files:
            return None
        files.sort(key=lambda x: x["fname"], reverse=True)
        f = files[0]
        return f["fname"], _download_web(f["url"])

    # ftp — via curl (handles PASV negotiation better than ftplib)
    ftp_files = _list_ftp_files(cfg["ftp_user"])
    if not ftp_files:
        return None
    return ftp_files[0], _download_ftp(cfg["ftp_user"], ftp_files[0])
