import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Box,
  CheckCircle2,
  Cpu,
  Download,
  ExternalLink,
  Filter,
  Gauge,
  HardDrive,
  Heart,
  Layers3,
  MemoryStick,
  Newspaper,
  PackageSearch,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Settings,
  ShoppingCart,
  Sparkles,
  Star,
  Store,
  Table2,
  Zap
} from "lucide-react";
import "./styles.css";

const money = new Intl.NumberFormat("en-LK", {
  style: "currency",
  currency: "LKR",
  maximumFractionDigits: 0
});

const categoryIcons = {
  "Processors / CPUs": Cpu,
  Motherboards: Layers3,
  RAM: MemoryStick,
  "Graphics Cards / GPUs": Zap,
  "SSDs / HDDs": HardDrive,
  "Power Supplies": Zap,
  Casing: Box,
  Coolers: Sparkles
};

const tabs = [
  { id: "parts", label: "Parts", icon: PackageSearch },
  { id: "build", label: "Builder", icon: ShoppingCart },
  { id: "favourites", label: "Favourites", icon: Heart },
  { id: "builds", label: "Builds", icon: Star },
  { id: "news", label: "News", icon: Newspaper },
  { id: "admin", label: "Admin", icon: Settings }
];

function formatPrice(value) {
  return value ? money.format(value).replace("LKR", "Rs.") : "Price unavailable";
}

function xmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function excelColumnName(index) {
  let name = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function crc32(bytes) {
  let crc = -1;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ -1) >>> 0;
}

function writeUint16(target, offset, value) {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
}

function writeUint32(target, offset, value) {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
  target[offset + 2] = (value >>> 16) & 0xff;
  target[offset + 3] = (value >>> 24) & 0xff;
}

function createZip(files) {
  const encoder = new TextEncoder();
  const chunks = [];
  const centralDirectory = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const data = encoder.encode(file.content);
    const checksum = crc32(data);
    const localHeader = new Uint8Array(30 + nameBytes.length);
    writeUint32(localHeader, 0, 0x04034b50);
    writeUint16(localHeader, 4, 20);
    writeUint16(localHeader, 6, 0);
    writeUint16(localHeader, 8, 0);
    writeUint16(localHeader, 10, 0);
    writeUint16(localHeader, 12, 0);
    writeUint32(localHeader, 14, checksum);
    writeUint32(localHeader, 18, data.length);
    writeUint32(localHeader, 22, data.length);
    writeUint16(localHeader, 26, nameBytes.length);
    localHeader.set(nameBytes, 30);
    chunks.push(localHeader, data);

    const directoryHeader = new Uint8Array(46 + nameBytes.length);
    writeUint32(directoryHeader, 0, 0x02014b50);
    writeUint16(directoryHeader, 4, 20);
    writeUint16(directoryHeader, 6, 20);
    writeUint16(directoryHeader, 8, 0);
    writeUint16(directoryHeader, 10, 0);
    writeUint16(directoryHeader, 12, 0);
    writeUint16(directoryHeader, 14, 0);
    writeUint32(directoryHeader, 16, checksum);
    writeUint32(directoryHeader, 20, data.length);
    writeUint32(directoryHeader, 24, data.length);
    writeUint16(directoryHeader, 28, nameBytes.length);
    writeUint32(directoryHeader, 42, offset);
    directoryHeader.set(nameBytes, 46);
    centralDirectory.push(directoryHeader);
    offset += localHeader.length + data.length;
  }

  const centralOffset = offset;
  const centralSize = centralDirectory.reduce((sum, item) => sum + item.length, 0);
  const endRecord = new Uint8Array(22);
  writeUint32(endRecord, 0, 0x06054b50);
  writeUint16(endRecord, 8, files.length);
  writeUint16(endRecord, 10, files.length);
  writeUint32(endRecord, 12, centralSize);
  writeUint32(endRecord, 16, centralOffset);
  return new Blob([...chunks, ...centralDirectory, endRecord], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  });
}

function createXlsxBlob(rows, headers) {
  const cell = (value, rowIndex, columnIndex) => {
    const ref = `${excelColumnName(columnIndex)}${rowIndex + 1}`;
    if (typeof value === "number" && Number.isFinite(value)) {
      return `<c r="${ref}"><v>${value}</v></c>`;
    }
    return `<c r="${ref}" t="inlineStr"><is><t>${xmlEscape(value)}</t></is></c>`;
  };
  const sheetRows = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))]
    .map((row, rowIndex) => `<row r="${rowIndex + 1}">${row.map((value, columnIndex) => cell(value, rowIndex, columnIndex)).join("")}</row>`)
    .join("");
  const lastColumn = excelColumnName(Math.max(headers.length - 1, 0));
  const dimension = headers.length ? `A1:${lastColumn}${rows.length + 1}` : "A1";

  return createZip([
    {
      name: "[Content_Types].xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`
    },
    {
      name: "_rels/.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`
    },
    {
      name: "xl/workbook.xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="PC Build" sheetId="1" r:id="rId1"/></sheets></workbook>`
    },
    {
      name: "xl/_rels/workbook.xml.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`
    },
    {
      name: "xl/worksheets/sheet1.xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="${dimension}"/><sheetData>${sheetRows}</sheetData></worksheet>`
    },
    {
      name: "xl/styles.xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>`
    }
  ]);
}

function api(path, options) {
  return fetch(path, options).then((response) => {
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  });
}

function App() {
  const [page, setPage] = useState("parts");
  const [meta, setMeta] = useState(null);
  const [products, setProducts] = useState([]);
  const [favourites, setFavourites] = useState([]);
  const [favouriteIds, setFavouriteIds] = useState(new Set());
  const [builds, setBuilds] = useState([]);
  const [news, setNews] = useState([]);
  const [providers, setProviders] = useState([]);
  const [suggestion, setSuggestion] = useState(null);
  const [manualSelections, setManualSelections] = useState({});
  const [removedCategories, setRemovedCategories] = useState(new Set());
  const [quantities, setQuantities] = useState({});
  const [loading, setLoading] = useState(true);
  const [budget, setBudget] = useState(450000);
  const [preferredStore, setPreferredStore] = useState("");
  const [buildName, setBuildName] = useState("");
  const [savingBuild, setSavingBuild] = useState(false);
  const [deletingBuildIds, setDeletingBuildIds] = useState(new Set());
  const [filters, setFilters] = useState({ search: "", category: "", store: "", stock: "", sort: "price-asc" });
  const [toast, setToast] = useState("");

  useEffect(() => {
    Promise.all([
      api("/api/meta"),
      api("/api/products"),
      api("/api/suggestions?budget=450000"),
      api("/api/favourites"),
      api("/api/builds"),
      api("/api/admin")
    ])
      .then(([metaData, productData, suggestionData, favouriteData, buildData, adminData]) => {
        setMeta(metaData);
        setProducts(productData.groups);
        setSuggestion(suggestionData);
        setFavourites(favouriteData.groups || []);
        setFavouriteIds(new Set(favouriteData.ids || []));
        setBuilds(buildData.builds || []);
        setProviders(adminData.providers || []);
      })
      .finally(() => setLoading(false));
    api("/api/news").then((newsData) => setNews(newsData.items || [])).catch(console.error);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    fetch(`/api/products?${params.toString()}`, { signal: controller.signal })
      .then((response) => response.json())
      .then((data) => setProducts(data.groups || []))
      .catch((error) => {
        if (error.name !== "AbortError") console.error(error);
      });
    return () => controller.abort();
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ budget: String(budget) });
      if (preferredStore) params.set("store", preferredStore);
      api(`/api/suggestions?${params.toString()}`).then(setSuggestion).catch(console.error);
    }, 250);
    return () => clearTimeout(timer);
  }, [budget, preferredStore]);

  const categories = useMemo(() => {
    return meta?.categories || [];
  }, [meta]);

  const buildRows = useMemo(() => {
    const byCategory = new Map((suggestion?.selected || []).filter((item) => !removedCategories.has(item.category)).map((item) => [item.category, item]));
    Object.values(manualSelections).forEach((product) => {
      byCategory.set(product.category, {
        category: product.category,
        product,
        groupId: product.dedupeKey || String(product.id),
        otherOffers: []
      });
    });
    const ordered = Object.keys(categoryIcons)
      .map((category) => byCategory.get(category))
      .filter(Boolean);
    const extras = [...byCategory.values()].filter((item) => !categoryIcons[item.category]);
    return [...ordered, ...extras].map((item) => ({
      ...item,
      quantity: quantities[item.category] || item.quantity || 1
    }));
  }, [suggestion, manualSelections, removedCategories, quantities]);

  const sortedProducts = useMemo(() => {
    const categoryRank = new Map((meta?.categories || []).map((category, index) => [category.name, index]));
    const hasFavourite = (group) => group.offers?.some((offer) => favouriteIds.has(offer.id));
    const sorted = [...products];
    sorted.sort((a, b) => {
      if (filters.sort === "price-desc") return (b.minPrice ?? -1) - (a.minPrice ?? -1);
      if (filters.sort === "category-az") return a.category.localeCompare(b.category) || (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999);
      if (filters.sort === "category-order") {
        return (categoryRank.get(a.category) ?? 999) - (categoryRank.get(b.category) ?? 999) || (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999);
      }
      if (filters.sort === "favourites") return Number(hasFavourite(b)) - Number(hasFavourite(a)) || (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999);
      if (filters.sort === "store") return (a.bestOffer?.store || "").localeCompare(b.bestOffer?.store || "") || (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999);
      return (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999);
    });
    return sorted;
  }, [products, filters.sort, favouriteIds, meta]);

  function showToast(message) {
    setToast(message);
    setTimeout(() => setToast(""), 2600);
  }

  async function refreshFavourites() {
    const data = await api("/api/favourites");
    setFavourites(data.groups || []);
    setFavouriteIds(new Set(data.ids || []));
  }

  async function refreshBuilds() {
    const buildData = await api("/api/builds");
    setBuilds(buildData.builds || []);
  }

  async function toggleFavourite(productId) {
    const data = await api(`/api/favourites/${productId}`, { method: "POST" });
    setFavouriteIds((current) => {
      const next = new Set(current);
      if (data.favourite) next.add(productId);
      else next.delete(productId);
      return next;
    });
    await refreshFavourites();
    showToast(data.favourite ? "Added to favourites" : "Removed from favourites");
  }

  function addToBuild(product) {
    setManualSelections((current) => ({ ...current, [product.category]: product }));
    setRemovedCategories((current) => {
      const next = new Set(current);
      next.delete(product.category);
      return next;
    });
    setQuantities((current) => ({ ...current, [product.category]: current[product.category] || 1 }));
    setPage("build");
    showToast(`${product.category} added to build`);
  }

  function updateQuantity(category, quantity) {
    setQuantities((current) => ({ ...current, [category]: Math.max(1, Math.min(99, Number(quantity) || 1)) }));
  }

  function removeBuildItem(category) {
    setManualSelections((current) => {
      const next = { ...current };
      delete next[category];
      return next;
    });
    setRemovedCategories((current) => new Set(current).add(category));
    showToast(`${category} removed from build`);
  }

  function exportRows() {
    return buildRows.map((item) => ({
      Category: item.category,
      Product: item.product.name,
      Store: item.product.store,
      Quantity: item.quantity || 1,
      Price: item.product.price || "",
      Total: (item.product.price || 0) * (item.quantity || 1),
      Stock: item.product.stock,
      URL: item.product.productUrl
    }));
  }

  function exportCsv() {
    const rows = exportRows();
    const header = Object.keys(rows[0] || { Category: "", Product: "", Store: "", Price: "", Stock: "", URL: "" });
    const csv = [
      header.join(","),
      ...rows.map((row) => header.map((key) => `"${String(row[key] ?? "").replaceAll('"', '""')}"`).join(","))
    ].join("\n");
    downloadBlob(csv, "pc-build.csv", "text/csv;charset=utf-8");
  }

  function exportExcel() {
    const rows = exportRows();
    const headers = Object.keys(rows[0] || { Category: "", Product: "", Store: "", Price: "", Stock: "", URL: "" });
    downloadBlob(createXlsxBlob(rows, headers), "pc-build.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  }

  function downloadBlob(content, filename, type) {
    const blob = content instanceof Blob ? content : new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function saveBuild() {
    try {
      setSavingBuild(true);
      const response = await fetch("/api/builds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: buildName.trim() || `Saved build ${new Date().toLocaleDateString()}`,
          budget,
          preferredStore,
          items: buildRows
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
      await refreshBuilds();
      showToast(`Saved build #${data.id}`);
    } catch (error) {
      showToast(error.message || "Failed to save build");
    } finally {
      setSavingBuild(false);
    }
  }

  async function deleteBuild(buildId) {
    try {
      setDeletingBuildIds((current) => new Set(current).add(buildId));
      await api(`/api/builds/${buildId}`, { method: "DELETE" });
      await refreshBuilds();
      showToast(`Deleted build #${buildId}`);
    } catch (error) {
      showToast(error.message || `Failed to delete build #${buildId}`);
    } finally {
      setDeletingBuildIds((current) => {
        const next = new Set(current);
        next.delete(buildId);
        return next;
      });
    }
  }

  function renderPage() {
    if (loading) return <div className="grid min-h-[50vh] place-items-center text-slate-400">Loading PC parts...</div>;
    if (page === "parts") {
      return <BrowseParts filters={filters} setFilters={setFilters} categories={categories} stores={meta?.stores || []} products={sortedProducts} favouriteIds={favouriteIds} toggleFavourite={toggleFavourite} addToBuild={addToBuild} />;
    }
    if (page === "build") {
      return <BestValueBuild buildName={buildName} setBuildName={setBuildName} savingBuild={savingBuild} budget={budget} setBudget={setBudget} preferredStore={preferredStore} setPreferredStore={setPreferredStore} stores={meta?.stores || []} rows={buildRows} suggestion={suggestion} manualSelections={manualSelections} updateQuantity={updateQuantity} removeBuildItem={removeBuildItem} saveBuild={saveBuild} exportCsv={exportCsv} exportExcel={exportExcel} />;
    }
    if (page === "favourites") {
      return <Favourites groups={favourites} favouriteIds={favouriteIds} toggleFavourite={toggleFavourite} addToBuild={addToBuild} />;
    }
    if (page === "builds") return <SavedBuilds builds={builds} deleteBuild={deleteBuild} deletingBuildIds={deletingBuildIds} />;
    if (page === "news") return <NewsPanel news={news} reloadNews={() => api("/api/news").then((data) => setNews(data.items || []))} />;
    return <AdminPanel providers={providers} showToast={showToast} reloadMeta={() => api("/api/meta").then(setMeta)} />;
  }

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100 tech-grid">
      <Navigation page={page} setPage={setPage} stats={meta?.stats} />
      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{renderPage()}</main>
      {toast ? <div className="fixed bottom-6 right-6 z-50 rounded-xl border border-cyan-300/30 bg-slate-950 px-4 py-3 text-sm font-bold text-cyan-100 shadow-2xl shadow-cyan-950/50">{toast}</div> : null}
    </div>
  );
}

function Navigation({ page, setPage, stats }) {
  return (
    <header className="sticky top-0 z-20 border-b border-cyan-300/10 bg-slate-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:px-8 xl:flex-row xl:items-center xl:justify-between">
        <button className="flex items-center gap-3 text-left" onClick={() => setPage("parts")}>
          <span className="grid h-11 w-11 place-items-center rounded-xl border border-cyan-300/30 bg-cyan-300/10 text-cyan-200 shadow-lg shadow-cyan-950/50">
            <Cpu size={23} />
          </span>
          <span>
            <span className="block text-lg font-black tracking-tight">PC Builder</span>
            <span className="block text-xs font-semibold text-slate-400">
              {stats?.products || 0} parts · {stats?.stores || 0} stores · {stats?.favourites || 0} favourites
            </span>
          </span>
        </button>
        <nav className="flex overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.04] p-1 text-sm font-bold">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`nav-pill ${page === id ? "nav-pill-active" : ""}`} onClick={() => setPage(id)}>
              <Icon size={16} /> {label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}

function PageTitle({ eyebrow, title, children, action }) {
  return (
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-cyan-300">{eyebrow}</p>
        <h1 className="mt-1 text-3xl font-black tracking-tight text-white sm:text-4xl">{title}</h1>
        {children ? <p className="mt-2 max-w-2xl text-sm font-medium leading-6 text-slate-400">{children}</p> : null}
      </div>
      {action}
    </div>
  );
}

function BrowseParts({ filters, setFilters, categories, stores, products, favouriteIds, toggleFavourite, addToBuild }) {
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Parts catalogue" title="Shop matched PC parts" action={<MetricPill icon={Gauge} label={`${products.length} matched groups`} />} />
      <div className="panel p-4">
        <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <label className="filter-field">
            <Search size={17} />
            <input value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} placeholder="Search CPUs, GPUs, stores..." />
          </label>
          <SelectField icon={Filter} value={filters.category} onChange={(category) => setFilters((current) => ({ ...current, category }))}>
            <option value="">All categories</option>
            {categories.map((category) => <option key={category.name} value={category.name}>{category.name} ({category.count})</option>)}
          </SelectField>
          <SelectField icon={Store} value={filters.store} onChange={(store) => setFilters((current) => ({ ...current, store }))}>
            <option value="">All stores</option>
            {stores.map((store) => <option key={store.name} value={store.name}>{store.name}</option>)}
          </SelectField>
          <SelectField icon={CheckCircle2} value={filters.stock} onChange={(stock) => setFilters((current) => ({ ...current, stock }))}>
            <option value="">Any stock</option>
            <option value="in">In stock</option>
            <option value="out">Out / unknown</option>
          </SelectField>
          <SelectField icon={Table2} value={filters.sort} onChange={(sort) => setFilters((current) => ({ ...current, sort }))}>
            <option value="price-asc">Price: low to high</option>
            <option value="price-desc">Price: high to low</option>
            <option value="category-order">Category order</option>
            <option value="category-az">Category A-Z</option>
            <option value="favourites">Favourites first</option>
            <option value="store">Store A-Z</option>
          </SelectField>
        </div>
      </div>
      <ProductGrid products={products} favouriteIds={favouriteIds} toggleFavourite={toggleFavourite} addToBuild={addToBuild} />
    </section>
  );
}

function ProductGrid({ products, favouriteIds, toggleFavourite, addToBuild }) {
  if (!products.length) return <EmptyState title="No matching parts" copy="Try clearing filters or refreshing store listings from Admin." />;
  return <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{products.map((group) => <ProductCard key={group.id} group={group} favouriteIds={favouriteIds} toggleFavourite={toggleFavourite} addToBuild={addToBuild} />)}</div>;
}

function SelectField({ icon: Icon, value, onChange, children }) {
  return (
    <label className="filter-field">
      <Icon size={17} />
      <select value={value} onChange={(event) => onChange(event.target.value)}>{children}</select>
    </label>
  );
}

function ProductCard({ group, favouriteIds, toggleFavourite, addToBuild }) {
  const offer = group.bestOffer;
  const isFavourite = favouriteIds.has(offer.id);
  return (
    <article className="card overflow-hidden transition hover:-translate-y-0.5 hover:border-cyan-300/40 hover:shadow-xl hover:shadow-cyan-950/30">
      <div className="relative aspect-square bg-slate-950/70 p-5">
        <button className={`icon-btn absolute right-3 top-3 ${isFavourite ? "icon-btn-on" : ""}`} onClick={() => toggleFavourite(offer.id)} title={isFavourite ? "Remove favourite" : "Add favourite"}>
          <Heart size={17} fill={isFavourite ? "currentColor" : "none"} />
        </button>
        <img className="h-full w-full object-contain" src={group.imageUrl || "/static/img/placeholder.svg"} alt={group.name} loading="lazy" />
      </div>
      <div className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <StoreBadge store={offer.store} />
          <StockBadge stock={offer.stock} />
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{group.category}</p>
          <h2 className="mt-1 line-clamp-2 min-h-12 text-base font-black leading-6 text-white">{group.name}</h2>
        </div>
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-slate-500">From</p>
            <p className="text-2xl font-black tracking-tight text-cyan-100">{formatPrice(group.minPrice)}</p>
          </div>
          <p className="rounded-full bg-cyan-300/10 px-3 py-1 text-xs font-bold text-cyan-200">{group.offers.length} offers</p>
        </div>
        <div className="space-y-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
          {group.storePrices.slice(0, 4).map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-2 text-sm">
              <span className="font-semibold text-slate-400">{item.store}</span>
              <span className="font-black text-slate-100">{formatPrice(item.price)}</span>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <a className="btn-secondary" href={offer.productUrl || "#"} target="_blank" rel="noreferrer"><ExternalLink size={16} /> View</a>
          <button className="btn-primary" onClick={() => addToBuild(offer)}><ShoppingCart size={16} /> Add to Build</button>
        </div>
      </div>
    </article>
  );
}

function BestValueBuild({ buildName, setBuildName, savingBuild, budget, setBudget, preferredStore, setPreferredStore, stores, rows, suggestion, manualSelections, updateQuantity, removeBuildItem, saveBuild, exportCsv, exportExcel }) {
  const total = rows.reduce((sum, item) => sum + ((item.product.price || 0) * (item.quantity || 1)), 0);
  const remaining = (suggestion?.budget || budget) - total;
  const manualCount = Object.keys(manualSelections).length;
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Build workspace" title="Selected component build" action={<div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={exportCsv}><Download size={16} /> CSV</button><button className="btn-secondary" onClick={exportExcel}><Table2 size={16} /> Excel</button><button className="btn-primary" disabled={savingBuild} onClick={saveBuild}><Save size={16} /> {savingBuild ? "Saving..." : "Save"}</button></div>}>{manualCount ? `${manualCount} slot${manualCount === 1 ? "" : "s"} manually selected from the catalogue.` : "Start from the suggested build, or add parts from Parts and Favourites to replace slots."}</PageTitle>
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr_1fr_1fr]">
        <div className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-sm font-bold text-slate-400">Budget</p><p className="text-3xl font-black tracking-tight text-white">{formatPrice(budget)}</p></div>
            <ShoppingCart className="text-cyan-300" size={26} />
          </div>
          <input className="mt-5 w-full accent-cyan-300" type="range" min="150000" max="10000000" step="50000" value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
        </div>
        <SummaryCard label="Selected parts" value={rows.length} />
        <SummaryCard label="Estimated total" value={formatPrice(total)} />
        <SummaryCard label={remaining >= 0 ? "Remaining" : "Over budget"} value={formatPrice(Math.abs(remaining))} tone={remaining >= 0 ? "good" : "bad"} />
      </div>
      <div className="panel p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_2fr] md:items-center">
          <div>
            <p className="text-sm font-bold text-slate-400">Build name</p>
            <p className="mt-1 text-sm font-semibold text-slate-300">Choose the name that will appear in saved builds.</p>
          </div>
          <label className="filter-field">
            <Save size={17} />
            <input value={buildName} onChange={(event) => setBuildName(event.target.value)} placeholder="Example: 7800X3D gaming build" />
          </label>
        </div>
      </div>
      <div className="panel p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_2fr] md:items-center">
          <div>
            <p className="text-sm font-bold text-slate-400">Store mode</p>
            <p className="mt-1 text-sm font-semibold text-slate-300">{preferredStore ? `Suggestions are limited to ${preferredStore}.` : "Suggestions can use the best offers across all stores."}</p>
          </div>
          <SelectField icon={Store} value={preferredStore} onChange={setPreferredStore}>
            <option value="">Best offer from any store</option>
            {stores.map((store) => <option key={store.name} value={store.name}>{store.name}</option>)}
          </SelectField>
        </div>
      </div>
      <BuildTable rows={rows} updateQuantity={updateQuantity} removeBuildItem={removeBuildItem} />
    </section>
  );
}

function BuildTable({ rows, updateQuantity, removeBuildItem }) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-white/10 px-5 py-4"><h2 className="text-lg font-black text-white">Build components</h2></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left">
          <thead className="bg-white/[0.04] text-xs font-black uppercase tracking-[0.12em] text-slate-400">
            <tr><th className="w-52 px-5 py-4">Category</th><th className="px-5 py-4">Part</th><th className="w-36 px-5 py-4">Store</th><th className="w-32 px-5 py-4">Price</th><th className="w-28 px-5 py-4">Qty</th><th className="w-40 px-5 py-4">Stock</th><th className="w-44 px-5 py-4 text-right">Action</th></tr>
          </thead>
          <tbody className="divide-y divide-white/10">{rows.map((item) => <BuildRow key={item.category} item={item} updateQuantity={updateQuantity} removeBuildItem={removeBuildItem} />)}</tbody>
        </table>
      </div>
    </div>
  );
}

function BuildRow({ item, updateQuantity, removeBuildItem }) {
  const Icon = categoryIcons[item.category] || Box;
  return (
    <tr className="align-middle">
      <td className="px-5 py-4"><div className="flex items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan-300/10 text-cyan-200"><Icon size={19} /></span><span className="font-black text-white">{item.category}</span></div></td>
      <td className="px-5 py-4"><div className="flex items-center gap-3"><img className="h-14 w-14 rounded-xl border border-white/10 bg-slate-950 object-contain" src={item.product.imageUrl || "/static/img/placeholder.svg"} alt="" /><span className="max-w-md font-semibold leading-5 text-slate-200">{item.product.name}</span></div></td>
      <td className="px-5 py-4"><StoreBadge store={item.product.store} /></td>
      <td className="px-5 py-4 text-base font-black text-cyan-100 whitespace-nowrap">{formatPrice(item.product.price)}</td>
      <td className="px-5 py-4">
        <input className="qty-input" type="number" min="1" max="99" value={item.quantity || 1} onChange={(event) => updateQuantity(item.category, event.target.value)} />
      </td>
      <td className="px-5 py-4"><StockBadge stock={item.product.stock} /></td>
      <td className="px-5 py-4 text-right">
        <div className="flex justify-end gap-2">
          <a className="btn-secondary inline-flex" href={item.product.productUrl || "#"} target="_blank" rel="noreferrer">View <ExternalLink size={16} /></a>
          <button className="icon-btn" onClick={() => removeBuildItem(item.category)} title="Remove item"><Trash2 size={16} /></button>
        </div>
      </td>
    </tr>
  );
}

function Favourites({ groups, favouriteIds, toggleFavourite, addToBuild }) {
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Shortlist" title="Favourite parts">Parts you marked for later comparison.</PageTitle>
      <ProductGrid products={groups} favouriteIds={favouriteIds} toggleFavourite={toggleFavourite} addToBuild={addToBuild} />
    </section>
  );
}

function SavedBuilds({ builds, deleteBuild, deletingBuildIds }) {
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Saved configs" title="Builds">{builds.length ? "Saved suggested builds and their selected parts." : "Save a suggested build from the Builder tab to see it here."}</PageTitle>
      {builds.length ? <div className="grid gap-4 lg:grid-cols-2">{builds.map((build) => <BuildCard key={build.id} build={build} deleteBuild={deleteBuild} deleting={deletingBuildIds.has(build.id)} />)}</div> : <EmptyState title="No saved builds yet" copy="Use the Builder tab to generate and save a parts list." />}
    </section>
  );
}

function BuildCard({ build, deleteBuild, deleting }) {
  return (
    <article className="card p-5">
      <div className="flex items-start justify-between gap-4">
        <div><p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-300">Build #{build.id}</p><h2 className="mt-1 text-xl font-black text-white">{build.name}</h2><p className="mt-1 text-sm font-semibold text-slate-400">{new Date(build.created_at).toLocaleString()}</p>{build.preferred_store ? <p className="mt-2 text-xs font-black uppercase tracking-[0.14em] text-emerald-300">{build.preferred_store} only</p> : null}</div>
        <div className="flex shrink-0 items-center gap-2">
          <p className="rounded-xl bg-cyan-300/10 px-3 py-2 text-sm font-black text-cyan-100">{formatPrice(build.total)}</p>
          <button className="icon-btn" type="button" disabled={deleting} onClick={() => deleteBuild(build.id)} title="Delete build"><Trash2 size={16} /></button>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {build.items.map((item) => (
          <a key={item.id} href={item.product_url || "#"} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm">
            <span className="line-clamp-2 font-semibold text-slate-200">{item.category}: {item.name}</span>
            <span className="shrink-0 font-black text-cyan-100">{item.quantity > 1 ? `${item.quantity} x ` : ""}{formatPrice(item.selected_price)}</span>
          </a>
        ))}
      </div>
    </article>
  );
}

function NewsPanel({ news, reloadNews }) {
  const [refreshing, setRefreshing] = useState(false);
  const featured = news[0];
  const rest = news.slice(1);
  async function refresh() {
    setRefreshing(true);
    await reloadNews().finally(() => setRefreshing(false));
  }
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Market radar" title="PC parts news" action={<button className="btn-secondary" onClick={refresh}><RefreshCw className={refreshing ? "animate-spin" : ""} size={16} /> Refresh</button>}>Live hardware headlines with quick build impact notes for GPU launches, RAM pricing, CPU releases, and storage trends.</PageTitle>
      {featured ? <FeaturedNews item={featured} /> : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {rest.map((item, index) => <NewsCard key={`${item.url}-${index}`} item={item} />)}
      </div>
    </section>
  );
}

function FeaturedNews({ item }) {
  const published = item.published && !Number.isNaN(Date.parse(item.published)) ? new Date(item.published).toLocaleDateString() : item.published || "Recent";
  return (
    <article className="card overflow-hidden lg:grid lg:grid-cols-[1.1fr_1fr]">
      <NewsImage item={item} className="min-h-72 lg:min-h-full" />
      <div className="flex flex-col justify-between gap-6 p-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-cyan-300/10 px-3 py-1 text-xs font-black text-cyan-200">{item.category}</span>
            <span className="rounded-full border border-white/10 px-3 py-1 text-xs font-bold text-slate-400">{item.source}</span>
            <span className="text-xs font-bold text-slate-500">{published}</span>
          </div>
          <h2 className="mt-4 text-2xl font-black leading-tight text-white sm:text-3xl">{item.title}</h2>
          <p className="mt-4 text-sm font-semibold leading-7 text-slate-300">{item.overview || item.summary || "Open the story for details."}</p>
        </div>
        <a className="btn-primary w-fit" href={item.url} target="_blank" rel="noreferrer">Read full story <ExternalLink size={16} /></a>
      </div>
    </article>
  );
}

function NewsCard({ item }) {
  const published = item.published && !Number.isNaN(Date.parse(item.published)) ? new Date(item.published).toLocaleDateString() : item.published || "Recent";
  return (
    <article className="card overflow-hidden">
      <NewsImage item={item} className="h-44" />
      <div className="p-5">
        <div className="flex items-center justify-between gap-3"><span className="rounded-full bg-cyan-300/10 px-3 py-1 text-xs font-black text-cyan-200">{item.category}</span><span className="text-xs font-bold text-slate-500">{item.source}</span></div>
        <h2 className="mt-4 line-clamp-2 min-h-14 text-lg font-black leading-7 text-white">{item.title}</h2>
        <p className="mt-3 line-clamp-4 text-sm font-medium leading-6 text-slate-400">{item.overview || item.summary || "Open the story for details."}</p>
        <div className="mt-5 flex items-center justify-between gap-3">
          <span className="text-xs font-bold text-slate-500">{published}</span>
          <a className="btn-secondary" href={item.url} target="_blank" rel="noreferrer">Read <ExternalLink size={16} /></a>
        </div>
      </div>
    </article>
  );
}

function NewsImage({ item, className = "" }) {
  if (item.imageUrl) {
    return (
      <div className={`bg-slate-950 ${className}`}>
        <img className="h-full w-full object-cover" src={item.imageUrl} alt="" loading="lazy" referrerPolicy="no-referrer" />
      </div>
    );
  }
  return (
    <div className={`grid place-items-center bg-[radial-gradient(circle_at_30%_20%,rgba(103,232,249,0.22),transparent_35%),linear-gradient(135deg,rgba(15,23,42,0.9),rgba(8,47,73,0.7))] ${className}`}>
      <div className="grid h-16 w-16 place-items-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200">
        <Newspaper size={30} />
      </div>
    </div>
  );
}

function AdminPanel({ providers, showToast, reloadMeta }) {
  const [statuses, setStatuses] = useState({});
  async function refreshProvider(provider) {
    setStatuses((current) => ({ ...current, [provider.id]: { status: "running", message: "Updating listings..." } }));
    try {
      const result = await api(`/api/admin/refresh/${provider.id}`, { method: "POST" });
      setStatuses((current) => ({ ...current, [provider.id]: result }));
      await reloadMeta();
      showToast(`${provider.name}: ${result.message}`);
    } catch (error) {
      setStatuses((current) => ({ ...current, [provider.id]: { status: "failed", message: error.message } }));
      showToast(`${provider.name}: refresh failed`);
    }
  }
  return (
    <section className="space-y-5">
      <PageTitle eyebrow="Data operations" title="Admin refresh">Manually pull fresh listings per store. Each button runs that store's existing provider scraper.</PageTitle>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {providers.map((provider) => {
          const state = statuses[provider.id] || { status: "idle", message: "Ready to update." };
          return (
            <article key={provider.id} className="card p-5">
              <div className="flex items-start justify-between gap-3">
                <div><p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-300">Store</p><h2 className="mt-1 text-xl font-black text-white">{provider.name}</h2></div>
                <span className={`status-dot status-${state.status}`} />
              </div>
              <p className="mt-4 min-h-12 text-sm font-medium leading-6 text-slate-400">{state.message}</p>
              <button className="btn-primary mt-5 w-full" disabled={state.status === "running"} onClick={() => refreshProvider(provider)}>
                <RefreshCw className={state.status === "running" ? "animate-spin" : ""} size={16} /> Update listings
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function SummaryCard({ label, value, tone = "neutral" }) {
  const toneClass = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-cyan-100";
  return <div className="panel p-5"><p className="text-sm font-bold text-slate-400">{label}</p><p className={`mt-2 text-2xl font-black tracking-tight ${toneClass}`}>{value}</p></div>;
}

function MetricPill({ icon: Icon, label }) {
  return <div className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-4 text-sm font-black text-slate-200"><Icon size={17} className="text-cyan-300" />{label}</div>;
}

function StoreBadge({ store }) {
  return <span className="inline-flex max-w-full items-center rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-black text-cyan-100 whitespace-nowrap">{store || "Store"}</span>;
}

function StockBadge({ stock }) {
  const inStock = String(stock || "").toLowerCase().includes("in stock") || String(stock || "").toLowerCase().includes("available");
  return <span className={`inline-flex max-w-full items-center rounded-full px-3 py-1 text-xs font-black leading-5 whitespace-nowrap ${inStock ? "bg-emerald-300/10 text-emerald-200" : "bg-amber-300/10 text-amber-200"}`}>{stock || "Unknown"}</span>;
}

function EmptyState({ title, copy }) {
  return <div className="panel grid min-h-64 place-items-center p-8 text-center"><div><p className="text-xl font-black text-white">{title}</p><p className="mt-2 text-sm font-medium text-slate-400">{copy}</p></div></div>;
}

createRoot(document.getElementById("root")).render(<App />);
