from __future__ import annotations

import re
import time
from typing import Iterable

from bs4 import BeautifulSoup

from .base_store import BaseStoreProvider, ProductRecord, parse_lkr_price


class DisruptProvider(BaseStoreProvider):
    store_name = "Disrupt"
    base_url = "https://disrupt.lk/"
    request_delay_seconds = 0.5

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        count = 0
        page = 1
        while True:
            url = self.absolute_url(f"collections/all/products.json?limit=250&page={page}")
            response = self.session.get(url, timeout=25)
            response.raise_for_status()
            products = response.json().get("products", [])
            if not products:
                break
            for product in products:
                variants = product.get("variants") or []
                prices = [parse_lkr_price(v.get("price")) for v in variants if v.get("price")]
                prices = [price for price in prices if price is not None]
                compare_prices = [parse_lkr_price(v.get("compare_at_price")) for v in variants if v.get("compare_at_price")]
                compare_prices = [price for price in compare_prices if price is not None]
                current_price = min(prices) if prices else None
                previous_price = min([price for price in compare_prices if current_price and price > current_price] or []) if compare_prices else None
                available = any(v.get("available") for v in variants)
                image_url = ""
                if product.get("images"):
                    image_url = product["images"][0].get("src") or ""
                body_text = BeautifulSoup(product.get("body_html") or "", "html.parser").get_text(" ", strip=True)
                warranty = _extract_warranty(body_text)
                yield ProductRecord(
                    name=product.get("title") or "",
                    store=self.store_name,
                    category=product.get("product_type") or _category_from_tags(product.get("tags") or []),
                    price_lkr=current_price,
                    previous_price_lkr=previous_price,
                    discount_label=_discount_label(previous_price, current_price),
                    availability="In Stock" if available else "Out of Stock",
                    warranty=warranty,
                    image_url=image_url,
                    product_url=self.absolute_url(f"products/{product.get('handle')}") if product.get("handle") else "",
                    source=url,
                    notes=(body_text[:500] if body_text else ""),
                ).normalized()
                count += 1
                if limit and count >= limit:
                    return
            page += 1
            time.sleep(self.request_delay_seconds)


def _extract_warranty(text: str) -> str:
    match = re.search(r"(\d+\s*(?:year|years|month|months)\s*warranty)", text, re.I)
    return match.group(1) if match else ""


def _category_from_tags(tags: list[str]) -> str:
    joined = " ".join(tags)
    return joined or "Other"


def _discount_label(previous_price: int | None, current_price: int | None) -> str:
    if previous_price and current_price and previous_price > current_price:
        percent = round((previous_price - current_price) / previous_price * 100)
        return f"{percent}% off"
    return ""
