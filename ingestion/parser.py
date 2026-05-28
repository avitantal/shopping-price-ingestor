import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterator

_DATE_FORMATS = [
    (19, "%Y-%m-%d %H:%M:%S"),
    (19, "%Y-%m-%dT%H:%M:%S"),
    (14, "%Y%m%d%H%M%S"),
    (8,  "%Y%m%d"),
]


def _text(elem, *tags: str) -> str:
    for tag in tags:
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _parse_date(s: str) -> str:
    if not s:
        return datetime.now(timezone.utc).isoformat()
    s = s.strip()
    for length, fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s[:length], fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def parse_pricefull(xml_bytes: bytes) -> Iterator[dict]:
    """Yield normalized {barcode, item_name, price, updated_at} rows."""
    root = ET.fromstring(xml_bytes)
    container = root.find(".//Items") or root.find(".//Products") or root

    for item in container:
        barcode = _text(item, "ItemCode", "Barcode", "barcodeNumber")
        name = _text(item, "ItemName", "ItemNm", "productName")
        price_str = _text(item, "ItemPrice", "UnitOfMeasurePrice", "price")
        date_str = _text(item, "PriceUpdateDate", "LastUpdateDate", "UpdateDate")

        if not barcode or not name or not price_str:
            continue
        try:
            price = float(price_str)
        except ValueError:
            continue
        if price <= 0:
            continue

        yield {
            "barcode": barcode,
            "item_name": name,
            "price": round(price, 2),
            "updated_at": _parse_date(date_str),
        }
