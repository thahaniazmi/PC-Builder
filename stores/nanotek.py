from __future__ import annotations

import re
import time
from typing import Iterable

from .base_store import BaseStoreProvider, ProductRecord, parse_lkr_price


class NanotekProvider(BaseStoreProvider):
    store_name = "Nanotek"
    base_url = "https://www.nanotek.lk/"

    # Store selectors may change. These are the live category URLs observed on
    # Nanotek in May 2026.
    category_urls = {
        "PBA Systems": "category/pba-systems",
        "Apple": "category/apple",
        "Mobile Phones & Tablets": "category/mobile-phones-tablets",
        "All in One & NUC Systems": "category/all-in-one-nuc-systems",
        "Desktop Workstations": "category/desktop-workstations",
        "Console & Handheld Gaming": "category/console-handheld-gaming",
        "Graphic Tablet": "category/graphic-tablet",
        "Laptop": "category/laptop",
        "Laptop Bags & Accessories": "category/power-banks-laptop-bags-accessories",
        "Television": "category/television-tv",
        "Processors / CPUs": "category/processor",
        "Motherboards": "category/motherboards",
        "RAM": "category/memory-ram",
        "Graphics Cards / GPUs": "category/graphics-card",
        "SSDs / HDDs": "category/storage-nas",
        "Power Supplies": "category/power-supply-ups-surge-protectors",
        "Casing": "category/casings",
        "Coolers": "category/cooling-lighting",
        "Monitors": "category/monitors-monitor-arms",
        "Speakers & Headsets": "category/speakers-headsets-ear-buds",
        "Keyboards / Mice": "category/keyboard-mouse-gamepad-controller",
        "Projectors": "category/projectors",
        "Printers": "category/printers",
        "Gaming Chairs & Tables": "category/gaming-chairs-tables",
        "Cables & Connectors": "category/cables-connectors",
        "External Storage": "category/external-storage",
        "Streaming & Action Camera": "category/streaming-action-camera",
        "Expansion Cards & Networking": "category/expansion-cards-networking",
        "OS & Software": "category/os-software",
    }

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        count = 0
        for category, path in self.category_urls.items():
            next_url = self.absolute_url(path)
            visited: set[str] = set()
            while next_url and next_url not in visited:
                visited.add(next_url)
                try:
                    soup = self.get_soup(next_url)
                except Exception:
                    break
                for card in soup.select("li.ty-catPage-productListItem"):
                    link_el = card.select_one("a[href]")
                    title_el = card.select_one(".ty-productBlock-title h1")
                    price_el = card.select_one(".ty-productBlock-price-retail")
                    image_el = card.select_one("img")
                    status_el = card.select_one(".ty-productBlock-specialMsg span")
                    name = title_el.get_text(" ", strip=True) if title_el else ""
                    if not name:
                        continue
                    visible_text = card.get_text(" ", strip=True)
                    yield ProductRecord(
                        name=f"{name} {category.split('/')[0].strip()}".strip(),
                        store=self.store_name,
                        category=category,
                        price_lkr=parse_lkr_price(price_el.get_text(" ", strip=True) if price_el else visible_text),
                        availability=status_el.get_text(" ", strip=True) if status_el else ("Out of Stock" if re.search(r"out of stock", visible_text, re.I) else "Unknown"),
                        warranty="",
                        image_url=self.absolute_url(image_el.get("src") or image_el.get("data-src") or "") if image_el else "",
                        product_url=self.absolute_url(link_el.get("href") if link_el else next_url),
                        source=next_url,
                    ).normalized()
                    count += 1
                    if limit and count >= limit:
                        return
                next_link = soup.find("a", string=re.compile(r"^\s*›\s*$"))
                next_url = self.absolute_url(next_link.get("href")) if next_link else ""
                time.sleep(self.request_delay_seconds)
