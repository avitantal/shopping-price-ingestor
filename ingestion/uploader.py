import hashlib
import sys

import requests

BATCH_SIZE = 5_000


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload_batches(
    supabase_url: str,
    ingest_key: str,
    chain_code: str,
    file_name: str,
    sha256: str,
    rows: list[dict],
) -> dict:
    """POST rows to Edge Function in batches. Returns the final response body."""
    url = f"{supabase_url}/functions/v1/refresh-products/ingest"
    headers = {
        "Authorization": f"Bearer {ingest_key}",
        "Content-Type": "application/json",
        "User-Agent": "ShoppingListApp/1.0 (avitantal@gmail.com)",
    }
    session = requests.Session()
    total = len(rows)
    result: dict = {}

    for i in range(0, max(total, 1), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        is_final = (i + BATCH_SIZE) >= total

        resp = session.post(
            url,
            headers=headers,
            json={
                "chain_code": chain_code,
                "file_name": file_name,
                "sha256": sha256,
                "is_final": is_final,
                "rows": batch,
            },
            timeout=60,
        )

        if resp.status_code != 200:
            print(
                f"  [error] batch {i // BATCH_SIZE + 1}: HTTP {resp.status_code} {resp.text[:300]}",
                file=sys.stderr,
            )
            resp.raise_for_status()

        data = resp.json()
        if data.get("status") == "already_ingested":
            print(f"  [skip] {file_name} already ingested")
            return data

        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  batch {batch_num}/{total_batches}: {data}")
        result = data

    return result
