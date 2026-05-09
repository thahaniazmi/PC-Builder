from __future__ import annotations

from html import unescape
import time
from typing import Iterable

from .base_store import BaseStoreProvider, ProductRecord


class MDComputersProvider(BaseStoreProvider):
    store_name = "MDComputers"
    base_url = "https://mdcomputers.lk/"
    request_delay_seconds = 0.2
    products_api = "https://mdcomputers.lk/wp-json/wc/store/v1/products"

    @staticmethod
    def _parse_price(prices: dict | None) -> tuple[int | None, int | None]:
        prices = prices or {}
        minor_unit = int(prices.get("currency_minor_unit") or 0)

        def to_int(value: object) -> int | None:
            if value in (None, ""):
                return None
            try:
                raw = int(str(value))
            except (TypeError, ValueError):
                return None
            if raw <= 0:
                return None
            divisor = 10 ** minor_unit if minor_unit > 0 else 1
            return raw // divisor if divisor else raw

        return to_int(prices.get("price")), to_int(prices.get("regular_price"))

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        count = 0
        page = 1
        per_page = 100

        while True:
            response = self.session.get(
                self.products_api,
                params={"page": page, "per_page": per_page},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break

            for item in items:
                price_lkr, previous_price_lkr = self._parse_price(item.get("prices"))
                categories = [unescape((category or {}).get("name", "")).strip() for category in item.get("categories") or []]
                categories = [category for category in categories if category]
                images = item.get("images") or []
                image_url = images[0].get("src", "").strip() if images else ""
                name = unescape(item.get("name", "")).strip()
                if not name:
                    continue

                yield ProductRecord(
                    name=name,
                    store=self.store_name,
                    category=", ".join(categories) if categories else "Other",
                    price_lkr=price_lkr,
                    previous_price_lkr=previous_price_lkr if previous_price_lkr and price_lkr and previous_price_lkr > price_lkr else None,
                    discount_label="",
                    availability="In Stock" if item.get("is_in_stock") else "Out of Stock",
                    warranty="",
                    image_url=image_url,
                    product_url=(item.get("permalink") or "").strip(),
                    source=f"{self.products_api}?page={page}",
                ).normalized()
                count += 1
                if limit and count >= limit:
                    return

            total_pages = int(response.headers.get("X-WP-TotalPages") or page)
            if page >= total_pages:
                break
            page += 1
            time.sleep(self.request_delay_seconds)
