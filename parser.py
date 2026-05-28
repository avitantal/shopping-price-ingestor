"""
Parse Israeli supermarket PriceFull XML files.

Uses iterparse for streaming so multi-MB files never fully load into RAM.
Yields one PriceRow per valid <Item>. Silently drops items that are missing
required fields or have zero/negative prices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import IO, Iterator
from xml.etree.ElementTree import iterparse


@dataclass(frozen=True)
class PriceRow:
    barcode: str
    item_name: str
    price: float
    updated_at: str  # ISO 8601 with UTC offset: "YYYY-MM-DDTHH:MM:SS+00:00"


_EPOCH_ISO = "1970-01-01T00:00:00+00:00"

# Israeli price XML uses mixed-case tags; normalise once per document.
_TAG_ALIASES = {
    "itemcode": "ItemCode",
    "itemname": "ItemName",
    "itemprice": "ItemPrice",
    "priceupdatedate": "PriceUpdateDate",
}

_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]


def parse_price_full(stream: IO[bytes]) -> Iterator[PriceRow]:
    """Yield PriceRow for every valid Item in a PriceFull XML stream."""
    current: dict[str, str] = {}
    inside_item = False

    for event, elem in iterparse(stream, events=("start", "end")):
        tag_lower = elem.tag.lower()

        if event == "start" and tag_lower == "item":
            current = {}
            inside_item = True
            continue

        if event == "end":
            if tag_lower == "item":
                inside_item = False
                row = _build_row(current)
                if row is not None:
                    yield row
                elem.clear()  # free memory
                continue

            if inside_item and tag_lower in _TAG_ALIASES:
                canonical = _TAG_ALIASES[tag_lower]
                current[canonical] = (elem.text or "").strip()


def _build_row(fields: dict[str, str]) -> PriceRow | None:
    barcode = fields.get("ItemCode", "").strip()
    if not barcode:
        return None

    item_name = fields.get("ItemName", "").strip()
    if not item_name:
        return None

    try:
        price = float(fields.get("ItemPrice", "0"))
    except ValueError:
        return None
    if price <= 0:
        return None

    updated_at = _parse_date(fields.get("PriceUpdateDate", ""))

    return PriceRow(barcode=barcode, item_name=item_name, price=price, updated_at=updated_at)


def _parse_date(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return _EPOCH_ISO
    # Normalise separators
    normalised = re.sub(r"[T/]", " ", raw).rstrip("Z")
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(normalised, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return _EPOCH_ISO
