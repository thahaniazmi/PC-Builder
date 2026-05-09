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
    raw = str(category or "Other").strip() or "Other"
    text = raw.lower()
    normalized_text = re.sub(r"[^a-z0-9+]+", " ", text)

    exact = {
        "processors cpus": "Processors / CPUs",
        "motherboards": "Motherboards",
        "ram": "RAM",
        "graphics cards gpus": "Graphics Cards / GPUs",
        "ssds hdds": "SSDs / HDDs",
        "power supplies": "Power Supplies",
        "case": "Casing",
        "casing": "Casing",
        "casings": "Casing",
        "coolers": "Coolers",
        "monitors": "Monitors",
        "keyboards": "Keyboards",
        "mice": "Mice",
        "headsets": "Headsets",
        "speakers headsets": "Speakers & Headsets",
        "keyboards mice": "Keyboards / Mice",
    }
    if normalized_text in exact:
        return exact[normalized_text]

    rules = [
        (r"\b(processors?|cpus?)\b", "Processors / CPUs"),
        (r"\bmotherboards?\b", "Motherboards"),
        (r"\b(memory|ram|ddr[345]?|sodimm|so dimm)\b", "RAM"),
        (r"\b(graphics?|gpus?|vga)\b", "Graphics Cards / GPUs"),
        (r"\b(ssds?|hdds?|storage|nvme|m\.?2)\b", "SSDs / HDDs"),
        (r"\b(power supplies|power supply|psus?)\b", "Power Supplies"),
        (r"\b(casings?|pc cases?|computer cases?|atx cases?|mid tower|micro tower|mini tower|chassis|cabinets?)\b", "Casing"),
        (r"\b(cooling|coolers?|cpu coolers?|fans?)\b", "Coolers"),
        (r"\bmonitors?\b", "Monitors"),
        (r"\bkeyboards?\b", "Keyboards"),
        (r"\b(mice|mouse)\b", "Mice"),
        (r"\b(headsets?|headphones?)\b", "Headsets"),
        (r"\b(prebuilt|desktop workstations?|desktop pcs?)\b", "Prebuilt PCs"),
    ]
    for pattern, normalized in rules:
        if re.search(pattern, text):
            return normalized
    return raw
