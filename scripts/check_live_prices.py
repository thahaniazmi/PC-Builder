from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rapidfuzz import fuzz
from sqlalchemy import select

from app import Product, SessionLocal
from stores.gamestreet import GameStreetProvider
from stores.nanotek import NanotekProvider

REPORT_PATH = Path("data/live_price_check.csv")


def clean(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def exact_key(value: str) -> str:
    words = clean(value).split()
    drop = {
        "processor",
        "processors",
        "motherboards",
        "motherboard",
        "ram",
        "graphics",
        "cards",
        "gpus",
        "ssds",
        "hdds",
        "power",
        "supplies",
        "casing",
        "coolers",
        "monitors",
    }
    return " ".join(word for word in words if word not in drop)


def best_match(live, existing):
    candidates = [p for p in existing if p.store == live.store and p.category == live.category]
    live_key = exact_key(live.name)
    for product in candidates:
        if exact_key(product.name) == live_key:
            return product, 100
    best = None
    best_score = 0
    live_name = clean(live.name)
    for product in candidates:
        score = fuzz.token_sort_ratio(live_name, clean(product.name))
        if score > best_score:
            best = product
            best_score = score
    return best, best_score


def main() -> None:
    providers = [GameStreetProvider(), NanotekProvider()]
    checked_at = datetime.now().isoformat(timespec="seconds")
    rows = []
    with SessionLocal() as db:
        existing = db.scalars(select(Product)).all()
        for provider in providers:
            print(f"Checking {provider.store_name}...")
            live_products = list(provider.iter_products())
            for live in live_products:
                match, score = best_match(live, existing)
                imported_price = match.price_lkr if match else None
                live_price = live.price_lkr if live.price_lkr and live.price_lkr > 0 else None
                delta = None
                status = "new_live_item"
                exact = bool(match and exact_key(live.name) == exact_key(match.name))
                if match and exact:
                    if live_price is None:
                        status = "missing_live_price"
                    elif imported_price is None:
                        status = "missing_imported_price"
                    else:
                        delta = live_price - imported_price
                    if live_price == imported_price and imported_price is not None:
                        status = "same"
                    elif delta is not None:
                        status = "changed"
                elif match:
                    status = "weak_match_review"
                rows.append(
                    {
                        "checked_at": checked_at,
                        "store": live.store,
                        "category": live.category,
                        "live_name": live.name,
                        "matched_imported_name": match.name if match else "",
                        "match_score": score,
                        "imported_price_lkr": imported_price or "",
                        "live_price_lkr": live_price or "",
                        "price_delta_lkr": delta if delta is not None else "",
                        "live_availability": live.availability,
                        "live_url": live.product_url,
                        "status": status,
                    }
                )

    REPORT_PATH.parent.mkdir(exist_ok=True)
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["checked_at"])
        writer.writeheader()
        writer.writerows(rows)

    changed = [row for row in rows if row["status"] == "changed"]
    same = [row for row in rows if row["status"] == "same"]
    review = [row for row in rows if row["status"] in {"new_live_item", "weak_match_review"}]
    print(f"Wrote {REPORT_PATH.resolve()}")
    print(f"Live rows checked: {len(rows)}")
    print(f"Same price: {len(same)}")
    print(f"Changed price: {len(changed)}")
    print(f"Needs review/new: {len(review)}")
    for row in changed[:25]:
        print(
            f"{row['store']} | {row['live_name'][:70]} | imported {row['imported_price_lkr']} -> live {row['live_price_lkr']} ({row['price_delta_lkr']})"
        )


if __name__ == "__main__":
    main()
