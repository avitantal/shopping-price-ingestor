"""
Orchestrator for the price ingestion worker.

Usage:
  python run.py [chain_code ...]

If no chain codes are given, all chains in CHAINS are processed.

Required environment variables:
  INGEST_URL       — Supabase Edge Function URL (POST /ingest)
  INGEST_KEY       — Bearer token for the Edge Function
  FTP_PASSWORD     — shared FTP password for all FTP chains
                     (all 6 FTP chains share one password on the
                     url.retail.publishedprices.co.il server)

Exit code 0 if all chains succeeded, 1 if any failed.
"""

import os
import sys
import traceback

from chains import CHAINS, ChainConfig
from fetcher import fetch_latest_price_full
from parser import parse_price_full
from uploader import upload_price_rows


def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return val


def run_chain(chain: ChainConfig, ingest_url: str, ingest_key: str, ftp_password: str) -> None:
    print(f"[{chain.chain_code}] fetching...", flush=True)
    fetched = fetch_latest_price_full(
        chain,
        ftp_password=ftp_password if chain.access_type == "ftp" else None,
    )
    print(f"[{chain.chain_code}] downloaded {fetched.file_name} sha256={fetched.sha256[:12]}...", flush=True)

    rows = list(parse_price_full(fetched.stream))
    print(f"[{chain.chain_code}] parsed {len(rows)} items", flush=True)

    if not rows:
        print(f"[{chain.chain_code}] no valid rows — skipping upload", flush=True)
        return

    upload_price_rows(
        rows=rows,
        chain_code=chain.chain_code,
        file_name=fetched.file_name,
        sha256=fetched.sha256,
        ingest_url=ingest_url,
        ingest_key=ingest_key,
    )
    print(f"[{chain.chain_code}] upload complete", flush=True)


def main(chain_codes: list[str]) -> int:
    ingest_url = _env("INGEST_URL")
    ingest_key = _env("INGEST_KEY")
    ftp_password = os.environ.get("FTP_PASSWORD", "")

    targets = {k: v for k, v in CHAINS.items() if k in chain_codes} if chain_codes else CHAINS
    if not targets:
        print(f"Unknown chain codes: {chain_codes}. Known: {list(CHAINS)}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for code, chain in targets.items():
        try:
            run_chain(chain, ingest_url, ingest_key, ftp_password)
        except Exception:
            print(f"[{code}] FAILED:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            failures.append(code)

    if failures:
        print(f"\nFailed chains: {failures}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
