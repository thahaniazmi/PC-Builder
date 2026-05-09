from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from urllib.parse import urlencode

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    create_engine,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from stores import PROVIDERS
from stores.base_store import ProductRecord, normalize_category, parse_lkr_price
from stores.manual_import import import_file

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pc_builder.sqlite3"
PLACEHOLDER_IMAGE = "/static/img/placeholder.svg"
SOURCE_WORKBOOK = Path(r"C:\Users\study\Downloads\PC Build\pc_components_vendor_pricing.xlsx")
BUILD_CATEGORIES = [
    "Processors / CPUs",
    "Motherboards",
    "RAM",
    "Graphics Cards / GPUs",
    "SSDs / HDDs",
    "Power Supplies",
    "Casing",
    "Coolers",
    "Monitors",
    "Keyboards",
    "Mice",
    "Headsets",
]
BUILD_CATEGORY_ALIASES = {
    "Keyboards": ["Keyboards", "Keyboards / Mice"],
    "Mice": ["Mice", "Keyboards / Mice"],
    "Headsets": ["Headsets", "Speakers & Headsets"],
}
CATEGORY_GROUP_ORDER = [
    "Processors / CPUs",
    "Motherboards",
    "RAM",
    "Graphics Cards / GPUs",
    "SSDs / HDDs",
    "Power Supplies",
    "Casing",
    "Coolers",
    "Monitors",
    "Keyboards / Mice",
    "Audio",
    "Games",
    "Gaming Consoles",
    "Controllers & Sim Gear",
    "Accessories",
    "Merchandise",
    "Laptops",
    "Prebuilt PCs",
    "Networking & Cables",
    "Printers & Projectors",
    "Phones & Tablets",
    "TV",
    "Software",
    "Other",
]

# FastAPI + SQLite keeps this app easy to run on Windows while still giving a
# clean API boundary for future scrapers, imports, and richer frontend views.
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    website: Mapped[str] = mapped_column(String(500), default="")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("store", "dedupe_key", name="uq_product_store_dedupe"),)

    # A Product is a vendor listing/offer, not a globally merged catalogue item.
    # Same/similar items from different stores stay as separate rows and can be
    # linked through product_matches for comparison.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    store: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    price_lkr: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    previous_price_lkr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_label: Mapped[str] = mapped_column(String(120), default="")
    availability: Mapped[str] = mapped_column(String(120), default="Unknown", index=True)
    warranty: Mapped[str] = mapped_column(String(250), default="")
    image_url: Mapped[str] = mapped_column(String(1000), default="")
    product_url: Mapped[str] = mapped_column(String(1000), default="")
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(500), default="")
    dedupe_key: Mapped[str] = mapped_column(String(600), index=True)


class Favourite(Base):
    __tablename__ = "favourites"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    product: Mapped[Product] = relationship()


class Build(Base):
    __tablename__ = "builds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    budget_lkr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_mode: Mapped[str] = mapped_column(String(40), default="manual")
    preferred_store: Mapped[str] = mapped_column(String(120), default="")
    favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    items: Mapped[list["BuildItem"]] = relationship(cascade="all, delete-orphan", back_populates="build")

    @property
    def total_lkr(self) -> int:
        return sum(item.selected_price or item.product.price_lkr or 0 for item in self.items)


class BuildItem(Base):
    __tablename__ = "build_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(ForeignKey("builds.id"))
    category: Mapped[str] = mapped_column(String(120))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    offer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_store: Mapped[str] = mapped_column(String(120), default="")
    selected_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selection_method: Mapped[str] = mapped_column(String(40), default="manual")
    build: Mapped[Build] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class ProductMatch(Base):
    __tablename__ = "product_matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_a_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_b_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    score: Mapped[int] = mapped_column(Integer, default=0)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    product_a: Mapped[Product] = relationship(foreign_keys=[product_a_id])
    product_b: Mapped[Product] = relationship(foreign_keys=[product_b_id])


class DuplicateDecision(Base):
    __tablename__ = "duplicate_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_a_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_b_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    decision: Mapped[str] = mapped_column(String(60), default="review")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    product_a: Mapped[Product] = relationship(foreign_keys=[product_a_id])
    product_b: Mapped[Product] = relationship(foreign_keys=[product_b_id])


app = FastAPI(title="PC Builder")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def display_category(category: str | None) -> str:
    value = (category or "Other").strip() or "Other"
    text_value = value.lower()
    exact = {
        "processors / cpus",
        "motherboards",
        "ram",
        "graphics cards / gpus",
        "ssds / hdds",
        "power supplies",
        "casing",
        "coolers",
        "monitors",
        "prebuilt pcs",
    }
    if text_value in exact:
        return value
    if "keyboard" in text_value or "mouse" in text_value or "mice" in text_value or "keycaps" in text_value or "switches" in text_value or "switch lube" in text_value or "switch puller" in text_value:
        return "Keyboards / Mice"
    if any(term in text_value for term in ["audio", "headphone", "headset", "speaker", "microphone", "amplifier", "sound bar", "radio", "earbuds", "in-ear", "on-ear", "over-ear"]):
        return "Audio"
    if any(term in text_value for term in ["video games", "playstation 4", "playstation 5", "switch", "xbox", "action", "rpg", "fps", "simulation", "sports", "strategy"]):
        return "Games"
    if "gaming consoles" in text_value or "console & handheld" in text_value or "nintendo" in text_value or "series x" in text_value or "series s" in text_value or "retro" in text_value:
        return "Gaming Consoles"
    if any(term in text_value for term in ["controller", "steering wheel", "wheel base", "pedal", "shifter", "flight simulator", "racing cockpit"]):
        return "Controllers & Sim Gear"
    if any(term in text_value for term in ["merchandise", "toys", "figurines", "wearables", "tableware", "posters", "collectibles", "keychains", "luggage", "backpacks", "mugs", "t-shirts", "badges", "pins", "blankets", "calendars"]):
        return "Merchandise"
    if "laptop" in text_value:
        return "Laptops"
    if any(term in text_value for term in ["cables", "adapters", "networking", "routers", "expansion cards"]):
        return "Networking & Cables"
    if "printer" in text_value or "projector" in text_value or "graphic tablet" in text_value:
        return "Printers & Projectors"
    if "mobile phones" in text_value or "phone accessories" in text_value or "tablet" in text_value or "apple" in text_value:
        return "Phones & Tablets"
    if "television" in text_value:
        return "TV"
    if "software" in text_value or text_value == "os & software":
        return "Software"
    if any(term in text_value for term in ["accessories", "charging dock", "covers", "grips", "skins", "stands", "mounts", "lights", "batteries", "travel bags", "webcams", "gift cards", "spare parts", "screen protectors", "virtual reality", "meta quest"]):
        return "Accessories"
    return value if value in CATEGORY_GROUP_ORDER else "Other"


templates.env.globals["display_category"] = display_category


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    ensure_schema_columns()
    with SessionLocal() as db:
        for name, website in [
            ("Nanotek", "https://www.nanotek.lk/"),
            ("Game Street", "https://www.gamestreet.lk/"),
            ("Tecroot", "https://tecroot.lk/"),
            ("Disrupt", "https://disrupt.lk/"),
            ("Manual", ""),
        ]:
            if not db.scalar(select(Store).where(Store.name == name)):
                db.add(Store(name=name, website=website))
        db.commit()
        if SOURCE_WORKBOOK.exists() and db.scalar(select(func.count(Product.id))) == 0:
            upsert_products(db, import_file(SOURCE_WORKBOOK))
        else:
            repair_category_false_positives(db)
            collapse_same_store_duplicates(db)


def repair_category_false_positives(db: Session) -> int:
    changed = 0
    memory_pattern = re.compile(r"\b(ddr[345]?|memory|ram|sodimm|so-dimm|\d+\s*gb\s+\d{3,5}\s*mhz)\b", re.I)
    phone_accessory_pattern = re.compile(r"\b(cellphone|phone|iphone|ipad|tablet|mobile)\b", re.I)
    poster_collectible_pattern = re.compile(r"\b(poster|framed|comic covers?|pop!)\b", re.I)

    for product in db.scalars(select(Product).where(Product.category == "RAM")).all():
        if not memory_pattern.search(product.name) and poster_collectible_pattern.search(product.name):
            product.category = "Posters & Collectibles"
            changed += 1

    for product in db.scalars(select(Product).where(Product.category == "Casing")).all():
        if phone_accessory_pattern.search(product.name):
            product.category = "Phone Accessories"
            changed += 1

    if changed:
        db.commit()
    return changed


def ensure_schema_columns() -> None:
    with engine.begin() as conn:
        existing_products = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()}
        product_additions = {
            "previous_price_lkr": "INTEGER",
            "discount_label": "VARCHAR(120) DEFAULT ''",
        }
        for column, ddl in product_additions.items():
            if column not in existing_products:
                conn.execute(text(f"ALTER TABLE products ADD COLUMN {column} {ddl}"))

        existing_builds = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(builds)").fetchall()}
        build_additions = {
            "selection_mode": "VARCHAR(40) DEFAULT 'manual'",
            "preferred_store": "VARCHAR(120) DEFAULT ''",
        }
        for column, ddl in build_additions.items():
            if column not in existing_builds:
                conn.execute(text(f"ALTER TABLE builds ADD COLUMN {column} {ddl}"))

        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(build_items)").fetchall()}
        additions = {
            "offer_id": "INTEGER",
            "selected_store": "VARCHAR(120) DEFAULT ''",
            "selected_price": "INTEGER",
            "selected_at": "DATETIME",
            "selection_method": "VARCHAR(40) DEFAULT 'manual'",
        }
        for column, ddl in additions.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE build_items ADD COLUMN {column} {ddl}"))


@app.on_event("startup")
def startup() -> None:
    init_db()


def dedupe_key(record: ProductRecord) -> str:
    if record.product_url:
        return record.product_url.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", record.name.lower()).strip()


def is_manual_source(source: str | None) -> bool:
    return bool(source and source.startswith("import:"))


def stock_rank(availability: str | None) -> int:
    value = (availability or "").lower()
    if "stock" in value and "out" not in value:
        return 0
    if "out" in value and "stock" in value:
        return 2
    return 1


def duplicate_preference_key(product: Product) -> tuple:
    return (
        is_manual_source(product.source),
        stock_rank(product.availability),
        product.price_lkr is None,
        product.price_lkr or 10**12,
        len(display_product_name(product)),
        product.id,
    )


def same_store_duplicate_key(product: Product) -> str:
    if product.product_url:
        return f"url::{product.product_url.lower().strip()}"
    return f"name::{product.category.lower()}::{clean_name(display_product_name(product))}"


def merge_product_data(winner: Product, loser: Product) -> None:
    if not winner.previous_price_lkr and loser.previous_price_lkr:
        winner.previous_price_lkr = loser.previous_price_lkr
    if not winner.discount_label and loser.discount_label:
        winner.discount_label = loser.discount_label
    if not winner.warranty and loser.warranty:
        winner.warranty = loser.warranty
    if (not winner.image_url or winner.image_url == PLACEHOLDER_IMAGE) and loser.image_url:
        winner.image_url = loser.image_url
    if not winner.product_url and loser.product_url:
        winner.product_url = loser.product_url
    if not winner.notes and loser.notes:
        winner.notes = loser.notes
    if not winner.source and loser.source:
        winner.source = loser.source
    if loser.last_updated and (not winner.last_updated or loser.last_updated > winner.last_updated):
        winner.last_updated = loser.last_updated


def replace_product_references(db: Session, loser: Product, winner: Product) -> None:
    for favourite in db.scalars(select(Favourite).where(Favourite.product_id == loser.id)).all():
        if db.get(Favourite, winner.id):
            db.delete(favourite)
        else:
            favourite.product_id = winner.id
    for item in db.scalars(select(BuildItem).where(BuildItem.product_id == loser.id)).all():
        item.product_id = winner.id
        if item.offer_id == loser.id:
            item.offer_id = winner.id
            item.selected_store = winner.store
            item.selected_price = winner.price_lkr
    for item in db.scalars(select(BuildItem).where(BuildItem.offer_id == loser.id)).all():
        item.offer_id = winner.id
        item.selected_store = winner.store
        item.selected_price = winner.price_lkr
    for match in db.scalars(select(ProductMatch).where(or_(ProductMatch.product_a_id == loser.id, ProductMatch.product_b_id == loser.id))).all():
        if match.product_a_id == loser.id:
            match.product_a_id = winner.id
        if match.product_b_id == loser.id:
            match.product_b_id = winner.id
        if match.product_a_id == match.product_b_id:
            db.delete(match)
    for decision in db.scalars(select(DuplicateDecision).where(or_(DuplicateDecision.product_a_id == loser.id, DuplicateDecision.product_b_id == loser.id))).all():
        if decision.product_a_id == loser.id:
            decision.product_a_id = winner.id
        if decision.product_b_id == loser.id:
            decision.product_b_id = winner.id
        if decision.product_a_id == decision.product_b_id:
            db.delete(decision)


def collapse_same_store_duplicates(db: Session) -> int:
    products = db.scalars(select(Product)).all()
    grouped: dict[tuple[str, str], list[Product]] = {}
    for product in products:
        key = same_store_duplicate_key(product)
        if key:
            grouped.setdefault((product.store, key), []).append(product)

    removed = 0
    for offers in grouped.values():
        if len(offers) < 2:
            continue
        ordered = sorted(offers, key=duplicate_preference_key)
        winner = ordered[0]
        for loser in ordered[1:]:
            merge_product_data(winner, loser)
            replace_product_references(db, loser, winner)
            db.delete(loser)
            removed += 1
    if removed:
        db.commit()
    return removed


VALID_SELECTION_METHODS = {"manual", "preferred_store"}
VALID_ADMIN_STATUS_KINDS = {"import", "refresh"}
VALID_ADMIN_STATUS_STATES = {"success", "failed"}


def upsert_products(db: Session, records, price_stock_only: bool = False) -> int:
    count = 0
    for record in records:
        record = record.normalized()
        if not record.name:
            continue
        key = dedupe_key(record)
        product = db.scalar(select(Product).where(Product.store == record.store, Product.dedupe_key == key))
        if product is None:
            product = find_existing_listing(db, record)
        if product is not None and is_manual_source(record.source) and not is_manual_source(product.source):
            continue
        if price_stock_only and product is None:
            continue
        if product is None:
            product = Product(store=record.store, dedupe_key=key, name=record.name, category=record.category)
            db.add(product)
        product.price_lkr = record.price_lkr
        product.previous_price_lkr = record.previous_price_lkr if record.previous_price_lkr and record.price_lkr and record.previous_price_lkr > record.price_lkr else None
        product.discount_label = record.discount_label or discount_label(product.previous_price_lkr, product.price_lkr)
        product.availability = record.availability or "Unknown"
        if not price_stock_only:
            product.name = record.name
            product.category = normalize_category(record.category)
            product.warranty = record.warranty or ""
            product.image_url = record.image_url or PLACEHOLDER_IMAGE
            product.product_url = record.product_url or ""
            product.last_updated = record.last_updated or datetime.now(timezone.utc)
            product.notes = product.notes or record.notes or ""
            product.source = record.source or ""
        count += 1
    db.flush()
    if not price_stock_only:
        collapse_same_store_duplicates(db)
    db.commit()
    return count


def find_existing_listing(db: Session, record: ProductRecord) -> Product | None:
    normalized_name = re.sub(r"[^a-z0-9]+", " ", record.name.lower()).strip()
    candidates = db.scalars(select(Product).where(Product.store == record.store, Product.category == normalize_category(record.category))).all()
    for product in candidates:
        candidate_name = re.sub(r"[^a-z0-9]+", " ", product.name.lower()).strip()
        if candidate_name == normalized_name:
            return product
    record_key = f"{normalize_category(record.category).lower()}::{model_signature(record.name, record.category)}"
    if record_key.endswith("::"):
        record_key = product_model_key(Product(store=record.store, dedupe_key="", name=record.name, category=record.category))
    for product in candidates:
        if product_model_key(product) == record_key:
            return product
    return None


def product_query(db: Session, request: Request):
    params = request.query_params
    stmt = select(Product)
    if q := params.get("q"):
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if store := params.get("store"):
        stmt = stmt.where(Product.store == store)
    if category := params.get("category"):
        stmt = stmt.where(Product.category.in_(category_filter_values(db, category)))
    if availability := params.get("availability"):
        stmt = stmt.where(Product.availability == availability)
    if params.get("fav") == "1":
        stmt = stmt.join(Favourite, Favourite.product_id == Product.id)
    if min_price := parse_lkr_price(params.get("min_price")):
        stmt = stmt.where(Product.price_lkr >= min_price)
    if max_price := parse_lkr_price(params.get("max_price")):
        stmt = stmt.where(Product.price_lkr <= max_price)
    sort = params.get("sort", "recent")
    orderings = {
        "price_asc": Product.price_lkr.asc().nullslast(),
        "price_desc": Product.price_lkr.desc().nullslast(),
        "store": Product.store.asc(),
        "category": Product.category.asc(),
        "recent": Product.last_updated.desc(),
    }
    return stmt.order_by(orderings.get(sort, Product.last_updated.desc()))


def filter_options(db: Session) -> dict:
    raw_categories = db.scalars(select(Product.category).distinct()).all()
    category_counts: dict[str, int] = {}
    for category, count in db.execute(select(Product.category, func.count(Product.id)).group_by(Product.category)).all():
        label = display_category(category)
        category_counts[label] = category_counts.get(label, 0) + count
    categories = sorted(
        category_counts,
        key=lambda label: (
            CATEGORY_GROUP_ORDER.index(label) if label in CATEGORY_GROUP_ORDER else len(CATEGORY_GROUP_ORDER),
            label,
        ),
    )
    return {
        "stores": db.scalars(select(Product.store).distinct().order_by(Product.store)).all(),
        "categories": categories,
        "category_counts": category_counts,
        "raw_categories": raw_categories,
        "availability": db.scalars(select(Product.availability).distinct().order_by(Product.availability)).all(),
    }


def category_filter_values(db: Session, category: str) -> list[str]:
    raw_categories = db.scalars(select(Product.category).distinct()).all()
    grouped = [raw for raw in raw_categories if display_category(raw) == category]
    if grouped:
        return grouped
    return [category]


def product_model_key(product: Product) -> str:
    signature = model_signature(product.name, product.category)
    if signature:
        return f"{product.category.lower()}::{signature}"
    text_value = clean_name(product.name)
    replacements = [
        r"\bdesktop\b",
        r"\bprocessor(s)?\b",
        r"\bmotherboard(s)?\b",
        r"\bgraphic(s)?\b",
        r"\bcard(s)?\b",
        r"\bgpu(s)?\b",
        r"\bram\b",
        r"\bmemory\b",
        r"\bmonitor(s)?\b",
        r"\bcasing\b",
        r"\bcooler(s)?\b",
        r"\bpower\b",
        r"\bsupply\b",
        r"\bpsu\b",
        r"\b\d+\s*years?\b",
        r"\bwarranty\b",
        r"\bcores?\b",
        r"\bthreads?\b",
        r"\bcache\b",
        r"\bup\s*to\b",
        r"\bghz\b",
        r"\bmhz\b",
    ]
    for pattern in replacements:
        text_value = re.sub(pattern, " ", text_value)
    text_value = re.sub(r"\b\d+m\b", " ", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return f"{product.category.lower()}::{text_value}"


def model_signature(name: str, category: str) -> str:
    text_value = clean_name(name)
    category_value = (category or "").lower()
    condition = ""
    if re.search(r"\btray\b", text_value):
        condition = " tray"
    elif re.search(r"\bbox(ed)?\b", text_value) and not re.search(r"\bwithout box\b", text_value):
        condition = " boxed"

    if "processor" in category_value or "cpu" in category_value:
        amd = re.search(r"\b(amd\s+)?ryzen\s+(\d)\s+(\d{4}[a-z0-9]*)\b", text_value)
        if amd:
            return f"amd ryzen {amd.group(2)} {amd.group(3)}{condition}".strip()
        intel = re.search(r"\b(intel\s+)?(?:core\s+)?(i[3579])[-\s]*(\d{4,5}[a-z]*)\b", text_value)
        if intel:
            return f"intel {intel.group(2)} {intel.group(3)}{condition}".strip()
        ultra = re.search(r"\b(intel\s+)?core\s+ultra\s+(\d)\s+(?:processor\s+)?(\d{3}[a-z]*)\b", text_value)
        if ultra:
            return f"intel core ultra {ultra.group(2)} {ultra.group(3)}{condition}".strip()

    if "graphics" in category_value or "gpu" in category_value:
        brand = first_brand(text_value)
        nvidia = re.search(r"\b(rtx|gtx)\s*(\d{4})\s*(ti|super)?\b", text_value)
        amd = re.search(r"\brx\s*(\d{4})\s*(xt|gre)?\b", text_value)
        vram = re.search(r"\b(\d{1,2}\s*gb)\b", text_value)
        if nvidia:
            return " ".join(part for part in [brand, nvidia.group(1), nvidia.group(2), nvidia.group(3) or "", vram.group(1) if vram else ""] if part).strip()
        if amd:
            return " ".join(part for part in [brand, "rx", amd.group(1), amd.group(2) or "", vram.group(1) if vram else ""] if part).strip()

    storage = re.search(r"\b(9[89]0\s*(?:pro)?|sn\d{3,4}|nv\d+|p\d+)\b.*\b(\d+\s*tb|\d+\s*gb)\b", text_value)
    if ("ssd" in category_value or "hdd" in category_value or "storage" in category_value) and storage:
        return f"{first_brand(text_value)} {storage.group(1)} {storage.group(2)}".strip()
    return ""


def first_brand(text_value: str) -> str:
    brands = ["asus", "msi", "gigabyte", "zotac", "palit", "sapphire", "powercolor", "galax", "corsair", "samsung", "wd", "western digital", "kingston", "lexar", "crucial", "teamgroup", "gskill", "adata"]
    for brand in brands:
        if re.search(rf"\b{re.escape(brand)}\b", text_value):
            return brand
    return ""


def display_product_name(product: Product) -> str:
    name = re.sub(r"\([^)]*warranty[^)]*\)", " ", product.name, flags=re.I)
    name = re.sub(r"\b\d+\s*years?\s*warranty\b", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -/")
    return name


def unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join((value or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def build_card_details(
    display_offer: Product,
    best_offer: Product,
    offers: list[Product],
    category: str,
    stock_status: str,
    image_url: str,
) -> dict:
    notes = unique_text([offer.notes for offer in offers])
    warranties = unique_text([offer.warranty for offer in offers])
    discounts = unique_text([offer.discount_label for offer in offers if offer.discount_label])
    features = []
    if len(offers) > 1:
        features.append(f"{len(offers)} store offers available")
    if warranties:
        features.extend([f"Warranty: {value}" for value in warranties[:3]])
    if discounts:
        features.extend([f"Promotion: {value}" for value in discounts[:2]])
    description = notes[0] if notes else ""
    return {
        "name": display_offer.name or best_offer.name,
        "category": category,
        "stock_status": stock_status,
        "image_url": image_url,
        "description": description,
        "features": features,
        "notes": notes,
        "offer_ids": ",".join(str(offer.id) for offer in offers),
        "compare_query": display_product_name(display_offer),
        "favourite_id": best_offer.id,
        "offers": [
            {
                "id": offer.id,
                "store": offer.store,
                "price_lkr": offer.price_lkr,
                "previous_price_lkr": offer.previous_price_lkr,
                "discount_label": offer.discount_label,
                "availability": offer.availability or "Unknown",
                "warranty": offer.warranty,
                "notes": offer.notes,
                "product_url": offer.product_url,
                "best": offer.id == best_offer.id,
            }
            for offer in offers
        ],
    }


def build_catalogue_card(offers: list[Product]) -> dict:
    offers = sorted(offers, key=lambda p: (p.price_lkr is None, p.price_lkr or 10**12, p.store, p.name))
    best_offer = next((offer for offer in offers if offer.price_lkr is not None), offers[0])
    display_offer = min(offers, key=lambda p: (len(display_product_name(p)), p.store))
    image_offer = next((offer for offer in offers if offer.image_url and offer.image_url != PLACEHOLDER_IMAGE), best_offer)
    stock_status = "In Stock" if any("stock" in (offer.availability or "").lower() and "out" not in (offer.availability or "").lower() for offer in offers) else offers[0].availability
    return {
        "id": best_offer.id,
        "name": display_product_name(display_offer),
        "category": display_category(best_offer.category),
        "raw_category": best_offer.category,
        "image_url": image_offer.image_url,
        "stock_status": stock_status,
        "best_offer": best_offer,
        "offers": offers,
        "stores": sorted({offer.store for offer in offers}),
        "last_updated": max((offer.last_updated for offer in offers if offer.last_updated), default=None),
        "details": build_card_details(display_offer, best_offer, offers, display_category(best_offer.category), stock_status, image_offer.image_url),
    }


def catalogue_related_offers(db: Session, product: Product) -> list[Product]:
    related_ids = {
        candidate.id
        for candidate in db.scalars(select(Product).where(Product.category == product.category)).all()
        if product_model_key(candidate) == product_model_key(product)
    }
    if not related_ids:
        related_ids = {product.id}

    changed = True
    while changed:
        changed = False
        matches = db.scalars(
            select(ProductMatch).where(
                ProductMatch.manual == True,
                or_(ProductMatch.product_a_id.in_(related_ids), ProductMatch.product_b_id.in_(related_ids)),
            )
        ).all()
        for match in matches:
            for product_id in [match.product_a_id, match.product_b_id]:
                if product_id not in related_ids:
                    related_ids.add(product_id)
                    changed = True
    return db.scalars(select(Product).where(Product.id.in_(related_ids))).all()


def build_catalogue_cards(products: list[Product], manual_matches: list[ProductMatch] | None = None) -> list[dict]:
    parent: dict[int, int] = {product.id: product.id for product in products}
    product_ids = set(parent)

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        if left in parent and right in parent:
            parent[find(right)] = find(left)

    key_owner: dict[str, int] = {}
    for product in products:
        key = product_model_key(product)
        if key in key_owner:
            union(key_owner[key], product.id)
        else:
            key_owner[key] = product.id

    for match in manual_matches or []:
        if match.product_a_id in product_ids and match.product_b_id in product_ids:
            union(match.product_a_id, match.product_b_id)

    grouped: dict[int, list[Product]] = {}
    for product in products:
        grouped.setdefault(find(product.id), []).append(product)

    cards = []
    for offers in grouped.values():
        cards.append(build_catalogue_card(offers))
    return sorted(cards, key=lambda card: (card["best_offer"].price_lkr is None, card["best_offer"].price_lkr or 10**12, card["name"]))


def products_for_build_category(db: Session, category: str, limit: int = 300) -> list[Product]:
    categories = BUILD_CATEGORY_ALIASES.get(category, [category])
    return db.scalars(
        select(Product)
        .where(Product.category.in_(categories))
        .order_by(Product.price_lkr.asc().nullslast(), Product.store.asc(), Product.name.asc())
        .limit(limit)
    ).all()


def offers_for_same_product(db: Session, product: Product) -> list[Product]:
    key = product_model_key(product)
    category_names = BUILD_CATEGORY_ALIASES.get(build_slot_for_offer(product), [product.category])
    candidates = db.scalars(select(Product).where(Product.category.in_(category_names))).all()
    return sorted(
        [candidate for candidate in candidates if product_model_key(candidate) == key],
        key=lambda p: (p.price_lkr is None, p.price_lkr or 10**12, p.store),
    )


def build_summary(db: Session, build: Build) -> dict:
    store_totals: dict[str, int] = {}
    item_rows = []
    for item in build.items:
        selected_price = item.selected_price or item.product.price_lkr or 0
        selected_store = item.selected_store or item.product.store
        store_totals[selected_store] = store_totals.get(selected_store, 0) + selected_price
        other_offers = offers_for_same_product(db, item.product)
        cheaper = [offer for offer in other_offers if offer.price_lkr and selected_price and offer.price_lkr < selected_price and offer.id != (item.offer_id or item.product_id)]
        item_rows.append({"item": item, "offers": other_offers, "cheaper": cheaper[:1]})
    return {
        "rows": item_rows,
        "store_totals": store_totals,
        "stores_used": len(store_totals),
        "total": sum(store_totals.values()),
        "multi_store": len(store_totals) > 1,
    }


def build_slot_for_offer(offer: Product) -> str:
    for slot, aliases in BUILD_CATEGORY_ALIASES.items():
        if offer.category in aliases:
            return slot
    return offer.category


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    products = db.scalars(product_query(db, request)).all()
    manual_matches = db.scalars(select(ProductMatch).where(ProductMatch.manual == True)).all()
    product_cards = build_catalogue_cards(products, manual_matches)
    favourite_ids = set(db.scalars(select(Favourite.product_id)).all())
    total_cards = len(build_catalogue_cards(db.scalars(select(Product)).all(), manual_matches))
    stats = {
        "products": total_cards,
        "offers": db.scalar(select(func.count(Product.id))) or 0,
        "favourites": len(favourite_ids),
        "builds": db.scalar(select(func.count(Build.id))) or 0,
        "stores": db.scalar(select(func.count(func.distinct(Product.store)))) or 0,
    }
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "product_cards": product_cards, "favourite_ids": favourite_ids, "options": filter_options(db), "stats": stats},
    )


@app.post("/favourites/{product_id}")
def toggle_favourite(product_id: int, db: Annotated[Session, Depends(get_db)]):
    fav = db.get(Favourite, product_id)
    if fav:
        db.delete(fav)
        state = False
    else:
        if not db.get(Product, product_id):
            raise HTTPException(404)
        db.add(Favourite(product_id=product_id))
        state = True
    db.commit()
    return {"favourite": state}


@app.get("/products/{product_id}/details")
def product_details(product_id: int, db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404)
    offers = catalogue_related_offers(db, product)
    if not offers:
        raise HTTPException(404)
    return JSONResponse(build_catalogue_card(offers)["details"])


@app.get("/favourites", response_class=HTMLResponse)
def favourites(request: Request, db: Annotated[Session, Depends(get_db)]):
    products = db.scalars(select(Product).join(Favourite).order_by(Favourite.created_at.desc())).all()
    favourite_ids = {product.id for product in products}
    favourite_cards = [build_catalogue_card([product]) for product in products]
    return templates.TemplateResponse("favourites.html", {"request": request, "product_cards": favourite_cards, "favourite_ids": favourite_ids})


@app.get("/builds", response_class=HTMLResponse)
def builds(request: Request, db: Annotated[Session, Depends(get_db)]):
    all_builds = db.scalars(select(Build).order_by(Build.created_at.desc())).unique().all()
    categories = BUILD_CATEGORIES
    products_by_category = {category: products_for_build_category(db, category, limit=250) for category in categories}
    summaries = {build.id: build_summary(db, build) for build in all_builds}
    return templates.TemplateResponse("builds.html", {"request": request, "builds": all_builds, "summaries": summaries, "categories": categories, "products_by_category": products_by_category})


@app.post("/builds")
def create_build(db: Annotated[Session, Depends(get_db)], name: Annotated[str, Form()], budget_lkr: Annotated[str, Form()] = ""):
    build = Build(name=name, budget_lkr=parse_lkr_price(budget_lkr))
    db.add(build)
    db.flush()
    db.commit()
    return RedirectResponse(f"/builds/{build.id}/edit", status_code=303)


@app.get("/builds/add-offer", response_class=HTMLResponse)
def add_offer_page(request: Request, db: Annotated[Session, Depends(get_db)], offer_ids: str):
    ids = [int(value) for value in offer_ids.split(",") if value.isdigit()]
    offers = db.scalars(select(Product).where(Product.id.in_(ids)).order_by(Product.price_lkr.asc().nullslast(), Product.store.asc())).all()
    if not offers:
        raise HTTPException(404)
    builds = db.scalars(select(Build).order_by(Build.created_at.desc())).all()
    stores = sorted({offer.store for offer in offers})
    return templates.TemplateResponse("add_offer.html", {"request": request, "offers": offers, "offer_ids": offer_ids, "builds": builds, "stores": stores, "category": offers[0].category, "warning": ""})


@app.post("/builds/add-offer")
def add_offer_to_build(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    offer_ids: Annotated[str, Form()],
    selection_method: Annotated[str, Form()],
    offer_id: Annotated[str, Form()] = "",
    preferred_store: Annotated[str, Form()] = "",
    build_id: Annotated[str, Form()] = "",
    new_build_name: Annotated[str, Form()] = "",
):
    if selection_method not in VALID_SELECTION_METHODS:
        raise HTTPException(400, "Unsupported selection method")
    ids = [int(value) for value in offer_ids.split(",") if value.isdigit()]
    offers = db.scalars(select(Product).where(Product.id.in_(ids)).order_by(Product.store.asc())).all()
    if not offers:
        raise HTTPException(404)
    if selection_method == "preferred_store":
        offer = next((candidate for candidate in offers if candidate.store == preferred_store), None)
        if offer is None:
            builds = db.scalars(select(Build).order_by(Build.created_at.desc())).all()
            return templates.TemplateResponse(
                "add_offer.html",
                {
                    "request": request,
                    "offers": offers,
                    "offer_ids": offer_ids,
                    "builds": builds,
                    "stores": sorted({candidate.store for candidate in offers}),
                    "category": offers[0].category,
                    "warning": "This item is not available from your preferred store. Please choose another store or replace the part.",
                },
                status_code=400,
            )
    else:
        if not offer_id:
            builds = db.scalars(select(Build).order_by(Build.created_at.desc())).all()
            return templates.TemplateResponse(
                "add_offer.html",
                {"request": request, "offers": offers, "offer_ids": offer_ids, "builds": builds, "stores": sorted({candidate.store for candidate in offers}), "category": offers[0].category, "warning": "Please choose a store offer before adding this product."},
                status_code=400,
            )
        offer = db.get(Product, int(offer_id))
    if not offer:
        raise HTTPException(404)
    if build_id:
        build = db.get(Build, int(build_id))
    else:
        build = Build(name=new_build_name.strip() or f"{display_product_name(offer)} Build")
        db.add(build)
        db.flush()
    if not build:
        raise HTTPException(404)
    slot_category = build_slot_for_offer(offer)
    build.selection_mode = selection_method
    build.preferred_store = preferred_store if selection_method == "preferred_store" else ""
    db.execute(delete(BuildItem).where(BuildItem.build_id == build.id, BuildItem.category == slot_category))
    db.add(
        BuildItem(
            build_id=build.id,
            category=slot_category,
            product_id=offer.id,
            offer_id=offer.id,
            selected_store=offer.store,
            selected_price=offer.price_lkr,
            selected_at=datetime.now(timezone.utc),
            selection_method=selection_method,
        )
    )
    db.commit()
    return RedirectResponse(f"/builds/{build.id}/edit", status_code=303)


@app.get("/builds/{build_id}/edit", response_class=HTMLResponse)
def edit_build(build_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    build = db.get(Build, build_id)
    if not build:
        raise HTTPException(404)
    categories = BUILD_CATEGORIES
    products_by_category = {category: products_for_build_category(db, category, limit=300) for category in categories}
    selected = {item.category: (item.offer_id or item.product_id) for item in build.items}
    stores = db.scalars(select(Product.store).distinct().order_by(Product.store)).all()
    return templates.TemplateResponse("build_edit.html", {"request": request, "build": build, "categories": categories, "products_by_category": products_by_category, "selected": selected, "stores": stores})


@app.post("/builds/{build_id}/edit")
async def update_build(build_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    build = db.get(Build, build_id)
    if not build:
        raise HTTPException(404)
    form = await request.form()
    build.name = str(form.get("name") or build.name)
    build.budget_lkr = parse_lkr_price(form.get("budget_lkr"))
    requested_mode = str(form.get("selection_mode") or "manual")
    build.selection_mode = requested_mode if requested_mode in VALID_SELECTION_METHODS else "manual"
    build.preferred_store = str(form.get("preferred_store") or "")
    build.favourite = form.get("favourite") == "on"
    db.execute(delete(BuildItem).where(BuildItem.build_id == build.id))
    for key, value in form.items():
        if not key.startswith("cat__") or not value:
            continue
        category = key.removeprefix("cat__")
        offer = db.get(Product, int(value))
        if not offer:
            continue
        db.add(
            BuildItem(
                build_id=build.id,
                category=category,
                product_id=offer.id,
                offer_id=offer.id,
                selected_store=offer.store,
                selected_price=offer.price_lkr,
                selected_at=datetime.now(timezone.utc),
                selection_method=build.selection_mode,
            )
        )
    db.commit()
    return RedirectResponse("/builds", status_code=303)


@app.post("/builds/{build_id}/delete")
def delete_build(build_id: int, db: Annotated[Session, Depends(get_db)]):
    build = db.get(Build, build_id)
    if build:
        db.delete(build)
        db.commit()
    return RedirectResponse("/builds", status_code=303)


@app.get("/builds/{build_id}/export.{fmt}")
def export_build(build_id: int, fmt: str, db: Annotated[Session, Depends(get_db)]):
    build = db.get(Build, build_id)
    if not build:
        raise HTTPException(404)
    rows = [
        {
            "Category": item.category,
            "Product": item.product.name,
            "Selected Store": item.selected_store or item.product.store,
            "Selected Price LKR": item.selected_price or item.product.price_lkr or 0,
            "Selection Method": item.selection_method or "manual",
            "Current Price LKR": item.product.price_lkr or 0,
            "Previous Price LKR": item.product.previous_price_lkr or "",
            "Discount": item.product.discount_label or "",
            "Price Change LKR": (item.product.price_lkr or 0) - (item.selected_price or item.product.price_lkr or 0),
            "Availability": item.product.availability,
            "Warranty": item.product.warranty,
            "Link": item.product.product_url,
        }
        for item in build.items
    ]
    rows.append({"Category": "Total", "Product": "", "Selected Store": "", "Selected Price LKR": sum(row["Selected Price LKR"] for row in rows), "Selection Method": "", "Current Price LKR": sum(row["Current Price LKR"] for row in rows), "Previous Price LKR": "", "Discount": "", "Price Change LKR": sum(row["Price Change LKR"] for row in rows), "Availability": "", "Warranty": "", "Link": ""})
    frame = pd.DataFrame(rows)
    if fmt == "csv":
        stream = io.StringIO()
        frame.to_csv(stream, index=False)
        return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{build.name}.csv"'})
    if fmt == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="Build")
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{build.name}.xlsx"'})
    raise HTTPException(400)


@app.get("/compare", response_class=HTMLResponse)
def compare(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    store: str = "",
    category: str = "",
    availability: str = "",
    min_price: str = "",
    max_price: str = "",
):
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if category:
        stmt = stmt.where(Product.category.in_(category_filter_values(db, category)))
    if availability:
        stmt = stmt.where(Product.availability == availability)
    if parsed_min := parse_lkr_price(min_price):
        stmt = stmt.where(Product.price_lkr >= parsed_min)
    if parsed_max := parse_lkr_price(max_price):
        stmt = stmt.where(Product.price_lkr <= parsed_max)
    products = db.scalars(stmt.order_by(Product.price_lkr.asc().nullslast(), Product.store.asc()).limit(180 if q else 160)).all()
    pairs = []
    for i, left in enumerate(products):
        for right in products[i + 1 :]:
            if left.store == right.store or left.category != right.category:
                continue
            score = fuzz.token_set_ratio(clean_name(left.name), clean_name(right.name))
            manual = db.scalar(
                select(ProductMatch).where(
                    or_(
                        (ProductMatch.product_a_id == left.id) & (ProductMatch.product_b_id == right.id),
                        (ProductMatch.product_a_id == right.id) & (ProductMatch.product_b_id == left.id),
                    )
                )
            )
            if score >= 82 or manual:
                if store and store not in {left.store, right.store}:
                    continue
                cheaper = cheaper_id(left, right)
                price_diff = None
                cheaper_store = ""
                if left.price_lkr is not None and right.price_lkr is not None:
                    price_diff = abs(left.price_lkr - right.price_lkr)
                    if cheaper == left.id:
                        cheaper_store = left.store
                    elif cheaper == right.id:
                        cheaper_store = right.store
                rounded_score = int(round(score))
                if manual or rounded_score >= 92:
                    confidence = "High"
                elif rounded_score >= 86:
                    confidence = "Medium"
                else:
                    confidence = "Low"
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "score": rounded_score,
                        "manual": bool(manual),
                        "cheaper": cheaper,
                        "price_diff": price_diff,
                        "cheaper_store": cheaper_store,
                        "confidence": confidence,
                    }
                )
    pairs = sorted(pairs, key=lambda p: p["score"], reverse=True)[:80]
    groups = compare_groups(pairs)
    return templates.TemplateResponse(
        "compare.html",
        {"request": request, "pairs": pairs, "groups": groups, "q": q, "options": filter_options(db)},
    )


@app.post("/compare/manual")
def manual_match(product_a_id: Annotated[int, Form()], product_b_id: Annotated[int, Form()], db: Annotated[Session, Depends(get_db)]):
    if product_a_id == product_b_id:
        raise HTTPException(400)
    score = fuzz.token_set_ratio(clean_name(db.get(Product, product_a_id).name), clean_name(db.get(Product, product_b_id).name))
    db.add(ProductMatch(product_a_id=product_a_id, product_b_id=product_b_id, score=score, manual=True))
    db.commit()
    return RedirectResponse("/compare", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Annotated[Session, Depends(get_db)]):
    provider_names = list(PROVIDERS.keys())
    status_kind = request.query_params.get("kind", "")
    status_subject = request.query_params.get("subject", "")
    status_state = request.query_params.get("state", "")
    status_message = request.query_params.get("message", "")
    if status_kind not in VALID_ADMIN_STATUS_KINDS:
        status_kind = ""
    if status_state not in VALID_ADMIN_STATUS_STATES:
        status_state = ""
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "providers": provider_names,
            "duplicate_count": probable_duplicate_count(db),
            "status_kind": status_kind,
            "status_subject": status_subject,
            "status_state": status_state,
            "status_message": status_message,
        },
    )


@app.get("/admin/duplicates", response_class=HTMLResponse)
def duplicate_review(request: Request, db: Annotated[Session, Depends(get_db)], q: str = ""):
    stmt = select(Product).where(Product.name.ilike(f"%{q}%")).limit(180) if q else select(Product).limit(180)
    products = db.scalars(stmt).all()
    decided = {
        tuple(sorted((row.product_a_id, row.product_b_id)))
        for row in db.scalars(select(DuplicateDecision)).all()
    }
    candidates = []
    for i, left in enumerate(products):
        for right in products[i + 1 :]:
            if left.store == right.store or left.category != right.category:
                continue
            key = tuple(sorted((left.id, right.id)))
            if key in decided:
                continue
            if product_model_key(left) == product_model_key(right):
                continue
            score = fuzz.token_sort_ratio(clean_name(left.name), clean_name(right.name))
            if 82 <= score < 97:
                candidates.append({"left": left, "right": right, "score": round(score, 1)})
    candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:80]
    return templates.TemplateResponse("duplicate_review.html", {"request": request, "q": q, "candidates": candidates})


@app.post("/admin/duplicates")
def save_duplicate_decision(
    product_a_id: Annotated[int, Form()],
    product_b_id: Annotated[int, Form()],
    decision: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
):
    if decision not in {"group", "separate", "variation"}:
        raise HTTPException(400)
    db.add(DuplicateDecision(product_a_id=product_a_id, product_b_id=product_b_id, decision=decision))
    if decision == "group":
        score = fuzz.token_sort_ratio(clean_name(db.get(Product, product_a_id).name), clean_name(db.get(Product, product_b_id).name))
        db.add(ProductMatch(product_a_id=product_a_id, product_b_id=product_b_id, score=int(score), manual=True))
    db.commit()
    return RedirectResponse("/admin/duplicates", status_code=303)


@app.post("/admin/import")
async def import_products(request: Request, file: Annotated[UploadFile, File()], db: Annotated[Session, Depends(get_db)]):
    filename = file.filename or "upload"
    tmp_path: Path | None = None
    try:
        suffix = Path(filename).suffix or ".csv"
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        count = upsert_products(db, import_file(tmp_path))
        query = urlencode(
            {
                "kind": "import",
                "subject": filename,
                "state": "success",
                "message": f"Imported or updated {count} products.",
            }
        )
    except Exception as exc:
        db.rollback()
        query = urlencode(
            {
                "kind": "import",
                "subject": filename,
                "state": "failed",
                "message": f"Import failed: {exc}",
            }
        )
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
    return RedirectResponse(f"/admin?{query}", status_code=303)


@app.post("/admin/refresh/{provider_name}")
def refresh_provider(provider_name: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    provider_cls = PROVIDERS.get(provider_name)
    if not provider_cls:
        raise HTTPException(404)
    try:
        provider = provider_cls()
        existing = db.scalar(select(func.count(Product.id)).where(Product.store == provider.store_name)) or 0
        price_stock_only = existing > 0 and provider.store_name != "MDComputers"
        limit = None if provider.store_name == "MDComputers" else 300
        count = upsert_products(db, provider.iter_products(limit=limit), price_stock_only=price_stock_only)
        query = urlencode(
            {
                "kind": "refresh",
                "subject": provider_name,
                "state": "success",
                "message": (
                    f"Imported {count} products from {provider.store_name}."
                    if not price_stock_only
                    else f"Updated price and stock for {count} existing products from {provider.store_name}."
                ),
            }
        )
    except Exception as exc:
        db.rollback()
        query = urlencode(
            {
                "kind": "refresh",
                "subject": provider_name,
                "state": "failed",
                "message": f"Refresh failed for {provider_name}: {exc}",
            }
        )
    return RedirectResponse(f"/admin?{query}", status_code=303)


@app.get("/suggestions", response_class=HTMLResponse)
def suggestions(request: Request, db: Annotated[Session, Depends(get_db)]):
    best_value = []
    for category in BUILD_CATEGORIES:
        category_names = BUILD_CATEGORY_ALIASES.get(category, [category])
        item = db.scalar(
            select(Product)
            .where(Product.category.in_(category_names), Product.price_lkr.is_not(None), Product.availability.ilike("%stock%"))
            .order_by(Product.price_lkr.asc())
        )
        if item:
            best_value.append(item)
    return templates.TemplateResponse(
        "suggestions.html",
        {
            "request": request,
            "best_value": best_value,
            "market_news": market_news(),
        },
    )


def clean_name(name: str) -> str:
    return re.sub(r"\b(without box|warranty|desktop processor|gaming|rgb|argb)\b|[^a-z0-9]+", " ", name.lower()).strip()


def cheaper_id(left: Product, right: Product) -> int | None:
    if left.price_lkr is None or right.price_lkr is None:
        return None
    return left.id if left.price_lkr <= right.price_lkr else right.id


def compare_groups(pairs: list[dict]) -> list[dict]:
    parent: dict[int, int] = {}
    products: dict[int, Product] = {}
    scores: dict[tuple[int, int], int] = {}
    manual_ids: set[tuple[int, int]] = set()

    def find(product_id: int) -> int:
        parent.setdefault(product_id, product_id)
        while parent[product_id] != product_id:
            parent[product_id] = parent[parent[product_id]]
            product_id = parent[product_id]
        return product_id

    def union(left_id: int, right_id: int) -> None:
        parent[find(right_id)] = find(left_id)

    for pair in pairs:
        left = pair["left"]
        right = pair["right"]
        products[left.id] = left
        products[right.id] = right
        key = tuple(sorted((left.id, right.id)))
        scores[key] = max(scores.get(key, 0), int(pair["score"]))
        if pair["manual"]:
            manual_ids.add(key)
        union(left.id, right.id)

    grouped: dict[int, list[Product]] = {}
    for product in products.values():
        grouped.setdefault(find(product.id), []).append(product)

    results = []
    for offers in grouped.values():
        offers = sorted(offers, key=lambda item: (item.price_lkr is None, item.price_lkr or 10**12, item.store, item.name))
        priced = [offer.price_lkr for offer in offers if offer.price_lkr is not None]
        best_price = min(priced) if priced else None
        best_id = next((offer.id for offer in offers if offer.price_lkr == best_price), None)
        group_scores = [
            score
            for key, score in scores.items()
            if key[0] in {offer.id for offer in offers} and key[1] in {offer.id for offer in offers}
        ]
        rows = []
        for offer in offers:
            rows.append(
                {
                    "product": offer,
                    "is_best": offer.id == best_id,
                    "diff": None if best_price is None or offer.price_lkr is None else offer.price_lkr - best_price,
                }
            )
        results.append(
            {
                "name": display_product_name(offers[0]),
                "category": offers[0].category,
                "rows": rows,
                "score": max(group_scores or [0]),
                "manual": any(
                    key[0] in {offer.id for offer in offers} and key[1] in {offer.id for offer in offers}
                    for key in manual_ids
                ),
                "best_price": best_price,
            }
        )
    return sorted(results, key=lambda group: (group["best_price"] is None, group["best_price"] or 10**12, group["name"]))[:40]


def discount_label(previous_price: int | None, current_price: int | None) -> str:
    if previous_price and current_price and previous_price > current_price:
        percent = round((previous_price - current_price) / previous_price * 100)
        return f"{percent}% off"
    return ""


def cheapest_build(db: Session, budget: int) -> dict:
    categories = ["Processors / CPUs", "Motherboards", "RAM", "Graphics Cards / GPUs", "SSDs / HDDs", "Power Supplies", "Casing", "Monitors", "Keyboards", "Mice", "Headsets"]
    items = []
    for category in categories:
        category_names = BUILD_CATEGORY_ALIASES.get(category, [category])
        product = db.scalar(
            select(Product)
            .where(Product.category.in_(category_names), Product.price_lkr.is_not(None), Product.availability.ilike("%stock%"))
            .order_by(Product.price_lkr.asc())
        )
        if product:
            items.append(product)
    total = sum(product.price_lkr or 0 for product in items)
    warnings = compatibility_warnings(items)
    return {"parts": items, "total": total, "within_budget": total <= budget, "warnings": warnings}


def compatibility_warnings(products: list[Product]) -> list[str]:
    text = " ".join(product.name for product in products).lower()
    warnings = []
    if "ddr5" in text and "ddr4" in text:
        warnings.append("DDR4 and DDR5 terms both appear. Confirm motherboard and RAM generation.")
    if "am5" in text and re.search(r"ryzen\s+[345]\s+[0-5]\d{3}", text):
        warnings.append("Possible older AM4 Ryzen CPU with AM5 motherboard. Confirm CPU socket.")
    if "lga1700" in text and re.search(r"ryzen", text):
        warnings.append("Intel LGA1700 motherboard with AMD Ryzen CPU terms detected.")
    gpu_price = sum(p.price_lkr or 0 for p in products if p.category == "Graphics Cards / GPUs")
    psu_text = " ".join(p.name.lower() for p in products if p.category == "Power Supplies")
    watts = max([int(x) for x in re.findall(r"(\d{3,4})\s*w", psu_text)] or [0])
    if gpu_price > 150000 and watts and watts < 650:
        warnings.append("High-end GPU with PSU under 650W. Check vendor wattage recommendation.")
    return warnings or ["No obvious compatibility warnings from available listing text. Manual confirmation still recommended."]


def market_news() -> list[dict]:
    return [
        {
            "category": "RAM",
            "headline": "DDR5 spot prices eased, but RAM is still not normal",
            "summary": "DDR5 spot pricing reportedly fell nearly 30% after the big 2025-2026 spike, but contract memory pricing is still expected to rise sharply in Q2. Treat small dips as relief, not a full crash.",
            "tone": "warn",
            "date": "April 2026",
            "sources": [
                {"label": "TechSpot", "url": "https://www.techspot.com/news/112030-memory-prices-finally-falling-but-ram-remain-unaffordable.html"},
            ],
        },
        {
            "category": "Motherboards",
            "headline": "Motherboard demand is getting hit by the memory crisis",
            "summary": "Reports say motherboard shipments have fallen hard because expensive RAM is discouraging new PC builds. If RAM suddenly becomes affordable again, board demand could bounce and create new shortages.",
            "tone": "warn",
            "date": "May 2026",
            "sources": [
                {"label": "Tom's Hardware", "url": "https://www.tomshardware.com/pc-components/motherboards/motherboard-sales-collapse-by-more-than-25-percent-as-chipmakers-strangle-enthusiast-pc-market-to-build-more-ai-chips-asus-projected-to-sell-5-million-fewer-boards-in-2025-gigabyte-msi-and-asrock-also-expected-to-see-reduced-sales-numbers"},
            ],
        },
        {
            "category": "GPU",
            "headline": "Several RTX 50 cards are still above sensible pricing",
            "summary": "Current price tracking shows RTX 5060 Ti 16GB, RTX 5070, RTX 5070 Ti, and RTX 5080 prices have moved up, while RTX 5090 stock is scarce and heavily marked up.",
            "tone": "danger",
            "date": "May 2026",
            "sources": [
                {"label": "PC Gamer", "url": "https://www.pcgamer.com/hardware/graphics-cards/graphics-card-price-watch-deals/"},
            ],
        },
        {
            "category": "Nvidia",
            "headline": "No major new desktop RTX launch signal yet",
            "summary": "Recent coverage points to no broad new RTX desktop GPU family or Super refresh in 2026. Nvidia's only fresh consumer-GPU note appears to be a minor RTX 5070 laptop variant.",
            "tone": "neutral",
            "date": "May 2026",
            "sources": [
                {"label": "PCWorld", "url": "https://www.pcworld.com/article/3125546/nvidias-new-rtx-gpu-reveal-was-a-paragraph-in-a-driver-release.html"},
                {"label": "Tom's Hardware", "url": "https://www.tomshardware.com/pc-components/gpus/report-claims-nvidia-will-not-be-releasing-any-new-rtx-gaming-gpus-in-2026-rtx-60-series-likely-debuting-in-2028"},
            ],
        },
        {
            "category": "AMD",
            "headline": "AMD warns component costs may rise later this year",
            "summary": "AMD's latest comments point to higher memory and component costs later in 2026, which could pressure Radeon pricing and availability in Q3 and Q4.",
            "tone": "warn",
            "date": "May 2026",
            "sources": [
                {"label": "TechRadar", "url": "https://www.techradar.com/computing/computing-components/amds-ceo-predicts-higher-memory-and-component-costs-later-this-year-so-brace-yourself-for-radeon-gpu-price-hikes"},
            ],
        },
    ]


def probable_duplicate_count(db: Session, limit: int = 180) -> int:
    products = db.scalars(select(Product).limit(limit)).all()
    decided = {
        tuple(sorted((row.product_a_id, row.product_b_id)))
        for row in db.scalars(select(DuplicateDecision)).all()
    }
    count = 0
    for i, left in enumerate(products):
        for right in products[i + 1 :]:
            if left.store == right.store or left.category != right.category:
                continue
            key = tuple(sorted((left.id, right.id)))
            if key in decided:
                continue
            if product_model_key(left) == product_model_key(right):
                continue
            score = fuzz.token_sort_ratio(clean_name(left.name), clean_name(right.name))
            if 82 <= score < 97:
                count += 1
    return count


init_db()
