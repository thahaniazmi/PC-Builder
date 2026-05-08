# PC Builder

Local FastAPI + SQLite app for comparing PC parts and planning builds from Sri Lankan stores. It includes Nanotek, Game Street, TecRoot, and Disrupt, and the provider structure is ready for more stores.

## Start

Double-click `start_app.bat`.

The script creates `.venv`, installs `requirements.txt`, initializes `data/pc_builder.sqlite3`, imports the provided workbook if found at `C:\Users\study\Downloads\PC Build\pc_components_vendor_pricing.xlsx`, then opens `http://localhost:8000`.

## Import Products

Use **Admin -> Import CSV/Excel** in the app. Accepted columns are flexible, but these are preferred:

`Vendor, Category, Product Name, Current Price (LKR), Stock Availability, Warranty, Product URL, Image URL, Specs / Notes`

A sample file is included at `sample_import.csv`.

## Refresh Store Data

Use **Admin -> Refresh** for any configured store or run:

```powershell
.venv\Scripts\python.exe scripts\refresh_products.py
```

The scrapers are modular and conservative. Store sites change often, so selectors in `stores/nanotek.py` and `stores/gamestreet.py` may need small adjustments. Disrupt uses its Shopify product endpoints. TecRoot currently blocks direct local scraping, so `stores/tecroot.py` uses 37Left's public indexed TecRoot listings while preserving original TecRoot product URLs. The scraper keeps product source URLs and uses delays to avoid aggressive requests.

## Add A New Store

1. Create `stores/new_store.py`.
2. Subclass `BaseStoreProvider`.
3. Return `ProductRecord` objects from `iter_products`.
4. Add the provider to `stores/__init__.py`.

All providers normalize to:

```python
name, store, category, price_lkr, availability, warranty, image_url, product_url, last_updated
```

## Favourites And Builds

Favourites, notes, saved builds, manual matches, and build favourite status are stored in SQLite and persist after app restarts. Product refreshes update product rows by store + product URL/name and do not delete saved user data.

## Multi-Vendor Items

The app keeps each vendor listing as its own product row. If Nanotek and Game Street sell the same CPU, both records remain visible with their own price, availability, warranty, image URL, source URL, notes, and update time. The comparison and manual match features link similar listings without merging or deleting either vendor record.

## Images

Imports preserve `Image URL` when available. Scrapers prefer store page images. If an image is missing or fails a lightweight URL check, the app uses `static/img/placeholder.svg`. You can edit image URLs manually from a product note/manual import workflow.

## Troubleshooting

- If the app does not start, run `start_app.bat` from a Command Prompt so the error remains visible.
- If imports fail, check that the workbook has a header row and a recognizable product name column.
- If scraping returns few products, inspect the store pages and update selectors in the provider file.
- If images do not load, the remote store may block hotlinking; import a reliable manufacturer image URL or leave the placeholder.
