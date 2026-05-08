from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class ProductRecord:
    name: str
    store: str
    category: str
    price_lkr: Optional[int] = None
    previous_price_lkr: Optional[int] = None
    discount_label: str = ""
    availability: str = "Unknown"
    warranty: str = ""
    image_url: str = ""
    product_url: str = ""
    last_updated: datetime | None = None
    source: str = "scraper"
    notes: str = ""

    def normalized(self) -> "ProductRecord":
        self.name = (self.name or "").strip()
        self.store = (self.store or "").strip()
        self.category = normalize_category(self.category)
        self.availability = (self.availability or "Unknown").strip()
        self.warranty = (self.warranty or "").strip()
        self.image_url = (self.image_url or "").strip()
        self.product_url = (self.product_url or "").strip()
        self.last_updated = self.last_updated or datetime.now(timezone.utc)
        return self


class BaseStoreProvider:
    store_name = "Base"
    base_url = ""
    request_delay_seconds = 1.0

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 PCBuilderLocalApp/1.0 (+local user initiated price comparison)",
                "Accept": "text/html,application/xhtml+xml",
            }
        )

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        raise NotImplementedError

    def get_soup(self, url: str, timeout: int = 20) -> BeautifulSoup:
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def absolute_url(self, url: str) -> str:
        return urljoin(self.base_url, url) if url else ""


def parse_lkr_price(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if parsed > 0 else None
    text = str(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d{1,2})?)", text)
    parsed = int(float(match.group(1))) if match else None
    return parsed if parsed and parsed > 0 else None


def normalize_category(category: object) -> str:
    text = (str(category or "Other").strip() or "Other").lower()
    mapping = {
        "processor": "Processors / CPUs",
        "cpu": "Processors / CPUs",
        "motherboard": "Motherboards",
        "memory": "RAM",
        "ram": "RAM",
        "graphics": "Graphics Cards / GPUs",
        "gpu": "Graphics Cards / GPUs",
        "storage": "SSDs / HDDs",
        "ssd": "SSDs / HDDs",
        "hdd": "SSDs / HDDs",
        "power": "Power Supplies",
        "psu": "Power Supplies",
        "casing": "Casing",
        "case": "Casing",
        "cooling": "Coolers",
        "cooler": "Coolers",
        "monitor": "Monitors",
        "keyboard": "Keyboards / Mice",
        "mouse": "Keyboards / Mice",
        "prebuilt": "Prebuilt PCs",
        "desktop": "Prebuilt PCs",
    }
    for key, normalized in mapping.items():
        if key in text:
            return normalized
    return str(category or "Other").strip() or "Other"
