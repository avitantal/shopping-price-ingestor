import argparse
import os
import sys

from chains import CHAINS
from fetcher import get_latest_pricefull
from parser import parse_pricefull
from uploader import compute_sha256, upload_batches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True, choices=list(CHAINS.keys()))
    args = ap.parse_args()

    chain_code: str = args.chain
    supabase_url: str = os.environ["SUPABASE_URL"].rstrip("/")
    ingest_key: str = os.environ["INGEST_KEY"]

    print(f"[{chain_code}] fetching latest PriceFull …")
    result = get_latest_pricefull(chain_code)
    if result is None:
        print(f"[{chain_code}] no PriceFull files found", file=sys.stderr)
        sys.exit(1)

    file_name, xml_bytes = result
    sha256 = compute_sha256(xml_bytes)
    print(f"[{chain_code}] file={file_name}  sha256={sha256[:16]}…  size={len(xml_bytes):,}B")

    rows = list(parse_pricefull(xml_bytes))
    print(f"[{chain_code}] parsed {len(rows):,} rows")

    if not rows:
        print(f"[{chain_code}] no valid rows after parsing — aborting", file=sys.stderr)
        sys.exit(1)

    final = upload_batches(supabase_url, ingest_key, chain_code, file_name, sha256, rows)
    print(f"[{chain_code}] done: {final}")


if __name__ == "__main__":
    main()
