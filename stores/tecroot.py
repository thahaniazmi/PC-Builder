from __future__ import annotations

import time
from typing import Iterable

from .base_store import BaseStoreProvider, ProductRecord


class TecRootProvider(BaseStoreProvider):
    store_name = "Tecroot"
    base_url = "https://tecroot.lk/"
    request_delay_seconds = 0.35
    search_url = "https://ts2.37left.lk:443/collections/37left-products2/documents/search"
    api_key = "Y7E35yMqmWjoJ5myLPpKdeNbr0iKOu9V"

    def iter_products(self, limit: int | None = None) -> Iterable[ProductRecord]:
        # TecRoot currently blocks unauthenticated local scraping with Cloudflare.
        # 37Left indexes TecRoot listings and keeps the original TecRoot product URL.
        count = 0
        page = 1
        while True:
            response = self.session.get(
                self.search_url,
                params={
                    "q": "*",
                    "query_by": "name,manual_categories",
                    "page": page,
                    "per_page": 250,
                    "filter_by": "shop_name: [Tecroot]",
                },
                headers={"x-typesense-api-key": self.api_key, "Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            hits = data.get("hits") or []
            if not hits:
                break
            for hit in hits:
                doc = hit.get("document") or {}
                categories = doc.get("manual_categories") or doc.get("categories") or []
                images = doc.get("images") or []
                yield ProductRecord(
                    name=doc.get("name") or "",
                    store=self.store_name,
                    category=", ".join(categories) if categories else "Other",
                    price_lkr=doc.get("price"),
                    availability="In Stock" if doc.get("in_stock") == "Yes" else "Out of Stock",
                    warranty="",
                    image_url=images[0] if images else "",
                    product_url=doc.get("original_url") or "",
                    source="37left Tecroot index",
                ).normalized()
                count += 1
                if limit and count >= limit:
                    return
            page += 1
            if page > ((data.get("found", 0) + 249) // 250):
                break
            time.sleep(self.request_delay_seconds)
