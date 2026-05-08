from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .base_store import ProductRecord, parse_lkr_price


FIELD_ALIASES = {
    "store": ["store", "vendor"],
    "category": ["category", "sub category"],
    "name": ["product name", "name", "product"],
    "price_lkr": ["current price (lkr)", "price_lkr", "price", "price lkr"],
    "previous_price_lkr": ["previous price (lkr)", "previous_price_lkr", "old price", "compare at price", "original price"],
    "discount_label": ["discount", "discount label", "offer / condition", "sale"],
    "availability": ["stock availability", "availability", "stock"],
    "warranty": ["warranty"],
    "image_url": ["image url", "image_url", "image"],
    "product_url": ["product url", "product_url", "url", "link"],
    "notes": ["specs / notes", "notes", "review notes"],
}


def _get(row: dict, field: str, default: str = ""):
    for alias in FIELD_ALIASES[field]:
        if alias in row and pd.notna(row[alias]):
            return row[alias]
    return default


def import_file(path: str | Path) -> Iterable[ProductRecord]:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, sheet_name=0)
    else:
        frame = pd.read_csv(path)

    frame.columns = [str(col).strip().lower() for col in frame.columns]
    now = datetime.now(timezone.utc)
    for raw in frame.to_dict(orient="records"):
        name = _get(raw, "name")
        if not str(name).strip():
            continue
        yield ProductRecord(
            name=str(name),
            store=str(_get(raw, "store", "Manual")),
            category=str(_get(raw, "category", "Other")),
            price_lkr=parse_lkr_price(_get(raw, "price_lkr", None)),
            previous_price_lkr=parse_lkr_price(_get(raw, "previous_price_lkr", None)),
            discount_label=str(_get(raw, "discount_label", "")),
            availability=str(_get(raw, "availability", "Unknown") or "Unknown"),
            warranty=str(_get(raw, "warranty", "")),
            image_url=str(_get(raw, "image_url", "")),
            product_url=str(_get(raw, "product_url", "")),
            last_updated=now,
            source=f"import:{path.name}",
            notes=str(_get(raw, "notes", "")),
        ).normalized()
