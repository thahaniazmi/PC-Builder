from __future__ import annotations

import re
import time
from typing import Iterable

from .base_store import BaseStoreProvider, ProductRecord, parse_lkr_price


class GameStreetProvider(BaseStoreProvider):
    store_name = "Game Street"
    base_url = "https://www.gamestreet.lk/"

    category_urls = {
        "Laptops": "products.php?cat=MQ==&scat=MA==",
        "Processors / CPUs": "products.php?cat=Mg==&scat=MQ==",
        "Motherboards": "products.php?cat=Mg==&scat=Mg==",
        "RAM": "products.php?cat=Mg==&scat=Mw==",
        "Casing": "products.php?cat=Mg==&scat=NA==",
        "Power Supplies": "products.php?cat=Mg==&scat=NQ==",
        "Graphics Cards / GPUs": "products.php?cat=Mg==&scat=Ng==",
        "Coolers": "products.php?cat=Mg==&scat=Nw==",
        "Monitors": "products.php?cat=Mg==&scat=OA==",
        "ODD": "products.php?cat=Mg==&scat=MTE=",
        "SSDs / HDDs": "products.php?cat=Mg==&scat=MTM=",
        "Gaming Chairs": "products.php?cat=Mw==&scat=MA==",
        "Mouse Mats": "products.php?cat=NA==&scat=OQ==",
        "USB & RGB Hubs": "products.php?cat=NA==&scat=MTA==",
        "Cables": "products.php?cat=NA==&scat=MTE=",
        "LED Strips": "products.php?cat=NA==&scat=MTI=",
        "Thermal Paste": "products.php?cat=NA==&scat=MTM=",
        "Fans": "products.php?cat=NA==&scat=MTQ=",
        "Streaming Devices": "products.php?cat=NA==&scat=MTU=",
        "Cooling Pads": "products.php?cat=NA==&scat=MTg=",
        "Gaming Backpacks": "products.php?cat=NA==&scat=MTk=",
        "Prebuilt PCs": "products.php?cat=NQ==&scat=MA==",
        "Keyboards": "products.php?cat=Ng==&scat=MTY=",
        "Mice": "products.php?cat=Ng==&scat=MTc=",
        "Headsets": "products.php?cat=Ng==&scat=MjA=",
        "Speakers": "products.php?cat=Ng==&scat=MjE=",
        "Headset Stands": "products.php?cat=Ng==&scat=MjI=",
        "Controllers": "products.php?cat=Ng==&scat=MjM=",
        "External Hard Disks": "products.php?cat=Ng==&scat=MjQ=",
        "Webcams": "products.php?cat=Ng==&scat=MjU=",
        "Microphones": "products.php?cat=Ng==&scat=MjY=",
    }

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        count = 0
        seen_urls: set[str] = set()
        for category, path in self.category_urls.items():
            url = self.absolute_url(path)
            try:
                soup = self.get_soup(url)
            except Exception:
                continue
            # Game Street pages historically use broad product boxes and product_view.php links.
            cards = soup.select("div.col-sm-4.MrgTp35")
            for card in cards:
                link_el = card.select_one('.product_title a[href*="product_view"]')
                name_el = card.select_one(".product_title a")
                price_el = card.select_one(".redPrice")
                image_el = card.select_one("img")
                product_url = self.absolute_url(link_el.get("href") if link_el else "")
                if product_url in seen_urls:
                    continue
                name = name_el.get_text(" ", strip=True) if name_el else ""
                if len(name) < 4:
                    continue
                text = card.get_text(" ", strip=True)
                availability = self._product_page_availability(product_url) if product_url else ""
                seen_urls.add(product_url)
                yield ProductRecord(
                    name=name,
                    store=self.store_name,
                    category=category,
                    price_lkr=parse_lkr_price(price_el.get_text(" ", strip=True) if price_el else text),
                    availability=availability or ("Out of Stock" if re.search(r"out of stock", text, re.I) else "Unknown"),
                    warranty=_extract_warranty(text),
                    image_url=self.absolute_url(image_el.get("src") or image_el.get("data-src") or "") if image_el else "",
                    product_url=product_url or url,
                    source=url,
                ).normalized()
                count += 1
                if limit and count >= limit:
                    return
            time.sleep(self.request_delay_seconds)

    def _product_page_availability(self, product_url: str) -> str:
        try:
            soup = self.get_soup(product_url, timeout=25)
        except Exception:
            return ""
        text = soup.get_text(" ", strip=True)
        match = re.search(r"Stock\s+Availability\s*:\s*([^:]+?)\s+Price\s*:", text, re.I)
        if match:
            return _normalize_availability(match.group(1))
        if re.search(r"\bout\s+of\s+stock\b", text, re.I):
            return "Out of Stock"
        if re.search(r"\bin\s+stock\b", text, re.I):
            return "In Stock"
        return ""


def _extract_warranty(text: str) -> str:
    match = re.search(r"(\d+\s*(?:year|years|month|months)\s*warranty)", text, re.I)
    return match.group(1) if match else ""


def _normalize_availability(value: str) -> str:
    value = " ".join(value.split()).strip(" -:|")
    if re.search(r"\bout\s+of\s+stock\b", value, re.I):
        return "Out of Stock"
    if re.search(r"\bin\s+stock\b", value, re.I):
        return "In Stock"
    return value or "Unknown"
