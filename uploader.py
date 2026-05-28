"""
Upload PriceRow batches to the Supabase Edge Function (POST /ingest).

Sends rows in chunks of BATCH_SIZE. The last batch always has is_final=True,
which triggers the Edge Function to merge staging→production tables.
"""

from __future__ import annotations

import json
from typing import Iterable

import requests

from parser import PriceRow

BATCH_SIZE = 5_000


def upload_price_rows(
    rows: Iterable[PriceRow],
    chain_code: str,
    file_name: str,
    sha256: str,
    ingest_url: str,
    ingest_key: str,
) -> None:
    rows_list = list(rows)
    if not rows_list:
        return

    headers = {
        "Authorization": f"Bearer {ingest_key}",
        "Content-Type": "application/json",
    }

    batches = [rows_list[i : i + BATCH_SIZE] for i in range(0, len(rows_list), BATCH_SIZE)]

    for idx, batch in enumerate(batches):
        is_final = idx == len(batches) - 1
        payload = {
            "chain_code": chain_code,
            "file_name": file_name,
            "sha256": sha256,
            "is_final": is_final,
            "rows": [
                {
                    "barcode": r.barcode,
                    "item_name": r.item_name,
                    "price": r.price,
                    "updated_at": r.updated_at,
                }
                for r in batch
            ],
        }
        resp = requests.post(ingest_url, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
