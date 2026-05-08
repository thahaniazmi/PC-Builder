import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import SessionLocal, upsert_products
from stores import PROVIDERS

if __name__ == "__main__":
    with SessionLocal() as db:
        for name, provider_cls in PROVIDERS.items():
            count = upsert_products(db, provider_cls().iter_products())
            print(f"{provider_cls.store_name}: {count} products")
