import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");
const dbPath = path.join(rootDir, "data", "pc_builder.sqlite3");
const placeholderImage = "/static/img/placeholder.svg";

const app = express();
const db = new DatabaseSync(dbPath);
const port = Number(process.env.PORT || 3001);
const execFileAsync = promisify(execFile);

app.use(express.json({ limit: "2mb" }));
app.use("/static", express.static(path.join(rootDir, "static")));

const componentCategories = [
  "Processors / CPUs",
  "Motherboards",
  "RAM",
  "Graphics Cards / GPUs",
  "SSDs / HDDs",
  "Power Supplies",
  "Casing",
  "Coolers"
];

const categoryAliases = {
  "Processors / CPUs": ["processor", "cpu", "ryzen", "core i3", "core i5", "core i7", "core i9"],
  Motherboards: ["motherboard", "mainboard", "b650", "b760", "z790", "x670", "a620", "h610"],
  RAM: ["ram", "memory", "ddr4", "ddr5", "sodimm"],
  "Graphics Cards / GPUs": ["graphics card", "gpu", "geforce", "rtx", "gtx", "radeon", "rx "],
  "SSDs / HDDs": ["ssd", "hdd", "nvme", "m.2", "hard disk", "storage"],
  "Power Supplies": ["power supply", "psu", "80 plus", "watt"],
  Casing: ["casing", "pc case", "gaming case", "chassis", "cabinet", "tower", "atx case"],
  Coolers: ["cooler", "aio", "liquid cooling", "heatsink", "thermalright"]
};

const hardExclusions = [
  "poster", "holder", "bracket", "mount", "stand", "cable", "adapter", "accessory", "accessories",
  "keycap", "switch puller", "lube", "mouse pad", "mat", "bag", "backpack", "cover", "skin",
  "protector", "dock", "chair", "desk", "microphone", "speaker", "headset", "keyboard", "mouse",
  "monitor arm", "controller", "gamepad", "console", "playstation", "xbox", "nintendo", "printer",
  "projector", "router", "webcam", "gift card", "figurine", "collectible", "mug", "shirt",
  "airpods", "airpod", "iphone", "phone", "hdd box", "external storage", "enclosure", "usb hub"
];

const buildSlots = [
  { category: "Processors / CPUs", required: true, weight: 0.2 },
  { category: "Motherboards", required: true, weight: 0.15 },
  { category: "RAM", required: true, weight: 0.1 },
  { category: "Graphics Cards / GPUs", required: true, weight: 0.32 },
  { category: "SSDs / HDDs", required: true, weight: 0.1 },
  { category: "Power Supplies", required: true, weight: 0.08 },
  { category: "Casing", required: true, weight: 0.05 },
  { category: "Coolers", required: false, weight: 0.05 }
];

const categoryOrder = [
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
  "Speakers & Headsets",
  "Prebuilt PCs",
  "Networking",
  "Laptops",
  "Gaming & Console",
  "Accessories",
  "Furniture",
  "Software",
  "Other"
];

function filterCategory(category) {
  const normalized = normalizeCategory(category);
  if (categoryOrder.includes(normalized)) return normalized;
  const text = String(category || "").toLowerCase();
  if (/\b(monitors?|display)\b/.test(text)) return "Monitors";
  if (/\bkeyboards?\b/.test(text)) return "Keyboards";
  if (/\b(mice|mouse)\b/.test(text)) return "Mice";
  if (/\b(headsets?|headphones?|speakers?|audio|microphones?)\b/.test(text)) return "Speakers & Headsets";
  if (/\b(routers?|network|networking|wifi|wi-fi)\b/.test(text)) return "Networking";
  if (/\b(laptops?|notebooks?)\b/.test(text)) return "Laptops";
  if (/\b(playstation|xbox|nintendo|switch|steam deck|console|video games?|controllers?|gamepad|simulation|rpg|sports|fps)\b/.test(text)) return "Gaming & Console";
  if (/\b(chairs?|seats?|desks?|floor mats?|cockpits?)\b/.test(text)) return "Furniture";
  if (/\b(os|software|licenses?)\b/.test(text)) return "Software";
  if (/\b(accessor|adapter|cables?|charging|dock|mounts?|stands?|covers?|skins?|bags?|batteries|lights?|webcams?|camera|printer|projector|phone|tablet|gift cards?|figurines?|merchandise|posters?|collectibles?)\b/.test(text)) return "Accessories";
  return "Other";
}

const storeProviders = [
  { id: "gamestreet", name: "GameStreet" },
  { id: "nanotek", name: "Nanotek" },
  { id: "tecroot", name: "TecRoot" },
  { id: "disrupt", name: "Disrupt" }
];

db.exec(`
  CREATE TABLE IF NOT EXISTS favourites (
    product_id INTEGER PRIMARY KEY REFERENCES products(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

function rows(sql, params = {}) {
  return db.prepare(sql).all(params);
}

function run(sql, params = {}) {
  return db.prepare(sql).run(params);
}

function scalar(sql, params = {}) {
  const row = db.prepare(sql).get(params);
  return row ? Object.values(row)[0] : null;
}

function formatProduct(row) {
  return {
    id: row.id,
    name: row.name,
    store: row.store,
    category: filterCategory(row.category),
    rawCategory: row.category,
    price: row.price_lkr,
    previousPrice: row.previous_price_lkr,
    discountLabel: row.discount_label || "",
    stock: row.availability || "Unknown",
    warranty: row.warranty || "",
    imageUrl: row.image_url || placeholderImage,
    productUrl: row.product_url || "",
    lastUpdated: row.last_updated || "",
    notes: row.notes || "",
    dedupeKey: row.dedupe_key || ""
  };
}

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9+.\s/-]/g, " ")
    .replace(/\b(with|fan|warranty|desktop|processor|gaming|graphics|card)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function compactToken(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, "");
}

function titleToken(value) {
  return String(value || "").toUpperCase().replace(/\s+/g, "");
}

function firstBrand(text) {
  const brands = [
    "asus", "msi", "gigabyte", "zotac", "palit", "sapphire", "powercolor", "galax",
    "corsair", "samsung", "wd", "western digital", "kingston", "lexar", "crucial", "teamgroup",
    "g.skill", "gskill", "adata", "seagate", "thermaltake", "cooler master", "antec", "fsp", "seasonic"
  ];
  return brands.find((brand) => new RegExp(`\\b${brand.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(text)) || "";
}

function productCondition(text) {
  if (/\btray\b|\bwithout\s+box\b/.test(text)) return "tray";
  if (/\bbox(?:ed)?\b/.test(text) && !/\bwithout\s+box\b/.test(text)) return "boxed";
  return "";
}

function canonicalProduct(product) {
  const text = normalizeText(product.name);
  const category = normalizeCategory(product.rawCategory || product.category, product.name);
  const condition = productCondition(text);
  const brand = firstBrand(text);
  const suffix = condition ? `:${condition}` : "";
  const suffixLabel = condition ? ` ${condition}` : "";

  if (category === "Processors / CPUs") {
    const amd = text.match(/\b(?:amd\s+)?ryzen\s+([3579])\s+(\d{4})\s*(x3d|xt|x|ge|gt|g|f)?\b/);
    if (amd) {
      const model = `${amd[2]}${amd[3] || ""}`;
      return {
        key: `${category}:amd-ryzen-${amd[1]}-${model}${suffix}`,
        label: `AMD Ryzen ${amd[1]} ${titleToken(model)}${suffixLabel}`
      };
    }
    const intel = text.match(/\b(?:intel\s+)?(?:core\s+)?(i[3579])[-\s]*(\d{4,5})\s*(ks|kf|k|f|t)?\b/);
    if (intel) {
      const model = `${intel[2]}${intel[3] || ""}`;
      return {
        key: `${category}:intel-${intel[1]}-${model}${suffix}`,
        label: `Intel Core ${intel[1].toUpperCase()} ${titleToken(model)}${suffixLabel}`
      };
    }
    const ultra = text.match(/\b(?:intel\s+)?core\s+ultra\s+([579])\s+(?:processor\s+)?(\d{3})\s*(k|h|hx|u|v)?\b/);
    if (ultra) {
      const model = `${ultra[2]}${ultra[3] || ""}`;
      return {
        key: `${category}:intel-core-ultra-${ultra[1]}-${model}${suffix}`,
        label: `Intel Core Ultra ${ultra[1]} ${titleToken(model)}${suffixLabel}`
      };
    }
  }

  if (category === "Graphics Cards / GPUs") {
    const nvidia = text.match(/\b(rtx|gtx)\s*(\d{4})\s*(ti\s*super|super\s*ti|ti|super)?\b/);
    const amd = text.match(/\b(?:radeon\s+)?rx\s*(\d{4})\s*(xtx|xt|gre)?\b/);
    const intel = text.match(/\barc\s+([ab])\s*-?\s*(\d{3,4})\b/);
    const vram = text.match(/\b(\d{1,2})\s*gb\b/);
    const oc = /\boc\b|overclock/.test(text) ? "oc" : "";
    if (nvidia) {
      const chip = `${nvidia[1]}-${nvidia[2]}-${compactToken(nvidia[3] || "")}`;
      return {
        key: `${category}:${brand}:${chip}:${vram?.[1] || ""}gb:${oc}`,
        label: [brand.toUpperCase(), nvidia[1].toUpperCase(), nvidia[2], titleToken(nvidia[3] || ""), vram ? `${vram[1]}GB` : "", oc.toUpperCase()].filter(Boolean).join(" ")
      };
    }
    if (amd) {
      const chip = `rx-${amd[1]}-${compactToken(amd[2] || "")}`;
      return {
        key: `${category}:${brand}:${chip}:${vram?.[1] || ""}gb:${oc}`,
        label: [brand.toUpperCase(), "RX", amd[1], titleToken(amd[2] || ""), vram ? `${vram[1]}GB` : "", oc.toUpperCase()].filter(Boolean).join(" ")
      };
    }
    if (intel) {
      const chip = `arc-${intel[1]}${intel[2]}`;
      return {
        key: `${category}:${brand}:${chip}:${vram?.[1] || ""}gb:${oc}`,
        label: [brand.toUpperCase(), "Arc", `${intel[1].toUpperCase()}${intel[2]}`, vram ? `${vram[1]}GB` : "", oc.toUpperCase()].filter(Boolean).join(" ")
      };
    }
  }

  if (category === "RAM") {
    const capacity = text.match(/\b(\d+)\s*gb\b/);
    const kit = text.match(/\b(?:x|\*)\s*(\d)\b|\b(\d)\s*x\s*\d+\s*gb\b/);
    const generation = text.match(/\bddr\s*([45])\b/);
    const speed = text.match(/\b(\d{4,5})\s*(?:mhz|mt\/s)?\b/);
    if (capacity && generation) {
      return {
        key: `${category}:${brand}:${capacity[1]}gb:ddr${generation[1]}:${speed?.[1] || ""}:${kit?.[1] || kit?.[2] || ""}`,
        label: [brand.toUpperCase(), `${capacity[1]}GB`, `DDR${generation[1]}`, speed?.[1], kit ? `Kit x${kit[1] || kit[2]}` : ""].filter(Boolean).join(" ")
      };
    }
  }

  if (category === "SSDs / HDDs") {
    const capacity = text.match(/\b(\d+(?:\.\d+)?)\s*(tb|gb)\b/);
    const model = text.match(/\b(9[89]0\s*(?:pro|evo)?|sn\d{3,4}[a-z]*|nv\d+|p\d+\s*plus?|kc\d+|mp\d+|mx\d+|bx\d+)\b/);
    const type = /\bnvme|m\.2\b/.test(text) ? "nvme" : /\bssd\b/.test(text) ? "ssd" : /\bhdd|hard\s*disk\b/.test(text) ? "hdd" : "";
    if (capacity && (model || type)) {
      return {
        key: `${category}:${brand}:${compactToken(model?.[1] || "")}:${capacity[1]}${capacity[2]}:${type}`,
        label: [brand.toUpperCase(), titleToken(model?.[1] || type), `${capacity[1]}${capacity[2].toUpperCase()}`, type.toUpperCase()].filter(Boolean).join(" ")
      };
    }
  }

  if (category === "Motherboards") {
    const chipset = text.match(/\b(a\d{3}|b\d{3}|h\d{3}|z\d{3}|x\d{3})\b/);
    const wifi = /\bwi-?fi|wifi\b/.test(text) ? "wifi" : "";
    const form = text.match(/\b(e-?atx|micro\s*atx|m-?atx|mini\s*itx|itx|atx)\b/);
    if (chipset) {
      return {
        key: `${category}:${brand}:${chipset[1]}:${wifi}:${compactToken(form?.[1] || "")}`,
        label: [brand.toUpperCase(), chipset[1].toUpperCase(), wifi.toUpperCase(), form ? titleToken(form[1]) : ""].filter(Boolean).join(" ")
      };
    }
  }

  const psu = text.match(/\b(\d{3,4})\s*w\b/);
  if (category === "Power Supplies" && psu) {
    const rating = text.match(/\b(80\s*plus\s*(bronze|silver|gold|platinum|titanium)|bronze|silver|gold|platinum|titanium)\b/);
    const modular = /\bfully\s*modular\b/.test(text) ? "fully-modular" : /\bsemi\s*modular\b/.test(text) ? "semi-modular" : "";
    return {
      key: `${category}:${brand}:${psu[1]}w:${compactToken(rating?.[0] || "")}:${modular}`,
      label: [brand.toUpperCase(), `${psu[1]}W`, rating ? titleToken(rating[0]) : "", modular].filter(Boolean).join(" ")
    };
  }

  const fallback = text.split(" ").slice(0, 10).join("-");
  return { key: `${category}:${fallback}`, label: product.name };
}

function productSignature(product) {
  return canonicalProduct(product).key;
}

function normalizeCategory(category, name = "") {
  const value = String(category || "").toLowerCase();
  const text = `${value} ${String(name || "").toLowerCase()}`;
  if (value.includes("cooler")) return "Coolers";
  if (value.includes("processor") || value === "cpu" || value.includes("processors / cpus")) return "Processors / CPUs";
  if (value.includes("motherboard")) return "Motherboards";
  if (value === "ram" || value === "memory" || value.includes("desktop ram") || value.includes("laptop ram")) return "RAM";
  if (value.includes("graphics") || value.includes("gpu")) return "Graphics Cards / GPUs";
  if (value.includes("ssd") || value.includes("hdd")) return "SSDs / HDDs";
  if (value.includes("power supplies") || value === "psu") return "Power Supplies";
  if (value === "casing" || value.includes("pc casing") || value.includes("computer casing")) return "Casing";
  if (/\b(ryzen\s+[3579]|core\s+i[3579]\s*-?\s*\d{4,5})\b/.test(text)) return "Processors / CPUs";
  if (/\b(motherboard|mainboard)\b/.test(text)) return "Motherboards";
  if (/\b(ddr4|ddr5|sodimm)\b/.test(text)) return "RAM";
  if (/\b(rtx|gtx|radeon|rx\s*\d{4})\b/.test(text)) return "Graphics Cards / GPUs";
  if (/\b(ssd|nvme|m\.2)\b/.test(text) && !/\b(external|enclosure|hdd box|usb)\b/.test(text)) return "SSDs / HDDs";
  if (/\b(psu|power supply)\b/.test(text)) return "Power Supplies";
  if (/\b(pc case|gaming case|chassis|cabinet|atx case)\b/.test(text)) return "Casing";
  if (/\b(aio|cpu cooler|liquid cooling|heatsink)\b/.test(text)) return "Coolers";
  return category || "Other";
}

function isInStock(stock) {
  const value = String(stock || "").toLowerCase();
  return value.includes("in stock") || value.includes("available") || value === "yes";
}

function isValidComponent(product) {
  const category = normalizeCategory(product.rawCategory || product.category, product.name);
  if (!componentCategories.includes(category)) return false;
  const text = `${product.name} ${product.rawCategory || ""} ${product.notes || ""}`.toLowerCase();
  if (hardExclusions.some((term) => text.includes(term))) return false;
  if (category === "Processors / CPUs" && /\b(cooler|fan|heatsink|thermal)\b/.test(text)) return false;
  if (category === "SSDs / HDDs" && /\b(external|hdd box|enclosure|adapter|usb)\b/.test(text)) return false;
  if (category === "Casing" && !/\b(pc case|gaming case|casing|chassis|cabinet|tower|atx)\b/.test(text)) return false;
  const aliases = categoryAliases[category] || [];
  return aliases.some((term) => text.includes(term));
}

function groupProducts(products) {
  const groups = new Map();
  for (const product of products) {
    const canonical = canonicalProduct(product);
    const key = canonical.key;
    if (!groups.has(key)) {
      groups.set(key, {
        id: key,
        name: canonical.label,
        category: product.category,
        imageUrl: product.imageUrl,
        canonicalName: canonical.label,
        offers: [],
        minPrice: product.price ?? null,
        maxPrice: product.price ?? null,
        inStockCount: 0,
        stores: []
      });
    }
    const group = groups.get(key);
    group.offers.push(product);
    if (!group.imageUrl || group.imageUrl === placeholderImage) group.imageUrl = product.imageUrl;
    if (product.price != null) {
      group.minPrice = group.minPrice == null ? product.price : Math.min(group.minPrice, product.price);
      group.maxPrice = group.maxPrice == null ? product.price : Math.max(group.maxPrice, product.price);
    }
    if (isInStock(product.stock)) group.inStockCount += 1;
    if (!group.stores.includes(product.store)) group.stores.push(product.store);
  }
  return [...groups.values()]
    .map((group) => {
      group.offers.sort((a, b) => (isInStock(b.stock) - isInStock(a.stock)) || ((a.price ?? 999999999) - (b.price ?? 999999999)));
      group.bestOffer = group.offers[0];
      group.name = group.canonicalName || group.bestOffer.name;
      group.storePrices = group.offers.map((offer) => ({ store: offer.store, price: offer.price, stock: offer.stock, id: offer.id }));
      return group;
    })
    .sort((a, b) => (a.minPrice ?? 999999999) - (b.minPrice ?? 999999999));
}

function allProducts(whereSql = "", params = {}, limit = 1200) {
  const limitSql = limit ? `LIMIT ${Number(limit)}` : "";
  return rows(
    `SELECT * FROM products ${whereSql} ORDER BY COALESCE(price_lkr, 999999999), name ${limitSql}`,
    params
  ).map(formatProduct);
}

app.get("/api/meta", (_req, res) => {
  const categoryRows = rows("SELECT category, COUNT(*) as count FROM products GROUP BY category ORDER BY category");
  const categoryCounts = new Map();
  for (const row of categoryRows) {
    const name = filterCategory(row.category);
    categoryCounts.set(name, (categoryCounts.get(name) || 0) + row.count);
  }
  const categories = [...categoryCounts.entries()]
    .map(([name, count]) => ({ name, raw: name, count }))
    .sort((a, b) => {
      const aIndex = categoryOrder.includes(a.name) ? categoryOrder.indexOf(a.name) : categoryOrder.length;
      const bIndex = categoryOrder.includes(b.name) ? categoryOrder.indexOf(b.name) : categoryOrder.length;
      return aIndex - bIndex || a.name.localeCompare(b.name);
    });
  const stores = rows("SELECT store as name, COUNT(*) as count FROM products GROUP BY store ORDER BY store");
  res.json({
    categories,
    stores,
    buildCategories: componentCategories,
    stats: {
      products: scalar("SELECT COUNT(*) FROM products") || 0,
      stores: scalar("SELECT COUNT(DISTINCT store) FROM products") || 0,
      builds: scalar("SELECT COUNT(*) FROM builds") || 0,
      favourites: scalar("SELECT COUNT(*) FROM favourites") || 0
    }
  });
});

app.get("/api/products", (req, res) => {
  const filters = [];
  const params = {};
  if (req.query.search) {
    filters.push("(LOWER(name) LIKE $search OR LOWER(store) LIKE $search)");
    params.$search = `%${String(req.query.search).toLowerCase()}%`;
  }
  if (req.query.store) {
    filters.push("store = $store");
    params.$store = String(req.query.store);
  }
  if (req.query.category) {
    const selectedCategory = String(req.query.category);
    const rawCategories = rows("SELECT DISTINCT category FROM products")
      .map((row) => row.category)
      .filter((category) => filterCategory(category) === selectedCategory);
    if (rawCategories.length) {
      const placeholders = rawCategories.map((_, index) => `$category${index}`);
      filters.push(`category IN (${placeholders.join(", ")})`);
      rawCategories.forEach((category, index) => {
        params[`$category${index}`] = category;
      });
    } else {
      filters.push("category = $category");
      params.$category = selectedCategory;
    }
  }
  if (req.query.stock === "in") {
    filters.push("(LOWER(availability) LIKE '%in stock%' OR LOWER(availability) LIKE '%available%')");
  } else if (req.query.stock === "out") {
    filters.push("NOT (LOWER(availability) LIKE '%in stock%' OR LOWER(availability) LIKE '%available%')");
  }
  const products = allProducts(filters.length ? `WHERE ${filters.join(" AND ")}` : "", params);
  res.json({ groups: groupProducts(products), count: products.length });
});

app.get("/api/suggestions", (req, res) => {
  const budget = Math.max(Number(req.query.budget || 450000), 100000);
  const candidates = groupProducts(allProducts("", {}, 0)).filter((group) => group.offers.some(isValidComponent));
  const selected = [];
  let total = 0;

  for (const slot of buildSlots) {
    const categoryGroups = candidates.filter((group) => group.category === slot.category);
    if (!categoryGroups.length) continue;
    const target = Math.floor(budget * slot.weight);
    const validOffers = categoryGroups
      .flatMap((group) => group.offers.map((offer) => ({ group, offer })))
      .filter(({ offer }) => isValidComponent(offer) && offer.price && (slot.required || total + offer.price <= budget))
      .sort((a, b) => {
        const aStock = isInStock(a.offer.stock) ? 0 : 1;
        const bStock = isInStock(b.offer.stock) ? 0 : 1;
        const aDistance = Math.abs((a.offer.price || 0) - target);
        const bDistance = Math.abs((b.offer.price || 0) - target);
        return aStock - bStock || aDistance - bDistance || a.offer.price - b.offer.price;
      });
    const pick = validOffers.find(({ offer }) => total + offer.price <= budget * 1.08) || validOffers[0];
    if (!pick) continue;
    total += pick.offer.price || 0;
    selected.push({
      category: slot.category,
      product: pick.offer,
      groupId: pick.group.id,
      otherOffers: pick.group.offers.filter((offer) => offer.id !== pick.offer.id)
    });
  }

  res.json({
    budget,
    total,
    remaining: budget - total,
    selected,
    grouped: selected.reduce((acc, item) => {
      acc[item.category] = item;
      return acc;
    }, {})
  });
});

app.post("/api/builds", (req, res) => {
  const name = String(req.body.name || "Saved build").slice(0, 250);
  const budget = Number(req.body.budget || 0) || null;
  const items = Array.isArray(req.body.items) ? req.body.items : [];
  const now = new Date().toISOString();
  const result = run(
    "INSERT INTO builds (name, budget_lkr, favourite, created_at, selection_mode, preferred_store) VALUES ($name, $budget, 0, $now, 'suggested', '')",
    { $name: name, $budget: budget, $now: now }
  );
  for (const item of items) {
    if (!item?.product?.id || !componentCategories.includes(item.category)) continue;
    run(
      "INSERT INTO build_items (build_id, category, product_id, offer_id, selected_store, selected_price, selected_at, selection_method) VALUES ($build, $category, $product, $offer, $store, $price, $now, 'suggested')",
      {
        $build: result.lastInsertRowid,
        $category: item.category,
        $product: item.product.id,
        $offer: item.product.id,
        $store: item.product.store || "",
        $price: item.product.price || null,
        $now: now
      }
    );
  }
  res.status(201).json({ id: Number(result.lastInsertRowid), name });
});

app.get("/api/builds", (_req, res) => {
  const builds = rows("SELECT * FROM builds ORDER BY created_at DESC LIMIT 50").map((build) => ({
    ...build,
    total: scalar("SELECT SUM(COALESCE(selected_price, p.price_lkr, 0)) FROM build_items bi JOIN products p ON p.id = bi.product_id WHERE bi.build_id = $id", { $id: build.id }) || 0,
    items: rows(
      "SELECT bi.*, p.name, p.store, p.image_url, p.availability, p.product_url FROM build_items bi JOIN products p ON p.id = bi.product_id WHERE bi.build_id = $id ORDER BY bi.id",
      { $id: build.id }
    )
  }));
  res.json({ builds });
});

app.get("/api/favourites", (_req, res) => {
  const products = rows(
    `SELECT p.* FROM products p
     JOIN favourites f ON f.product_id = p.id
     ORDER BY f.created_at DESC, p.name`
  ).map(formatProduct);
  res.json({ groups: groupProducts(products), ids: products.map((product) => product.id) });
});

app.post("/api/favourites/:productId", (req, res) => {
  const productId = Number(req.params.productId);
  const exists = scalar("SELECT id FROM products WHERE id = $id", { $id: productId });
  if (!exists) return res.status(404).json({ error: "Product not found" });
  const favourite = scalar("SELECT product_id FROM favourites WHERE product_id = $id", { $id: productId });
  if (favourite) {
    run("DELETE FROM favourites WHERE product_id = $id", { $id: productId });
    return res.json({ favourite: false });
  }
  run("INSERT INTO favourites (product_id, created_at) VALUES ($id, $now)", { $id: productId, $now: new Date().toISOString() });
  res.json({ favourite: true });
});

app.get("/api/admin", (_req, res) => {
  res.json({ providers: storeProviders });
});

app.post("/api/admin/refresh/:provider", async (req, res) => {
  const provider = String(req.params.provider || "");
  if (!storeProviders.some((item) => item.id === provider)) {
    return res.status(404).json({ error: "Unknown provider" });
  }

  const pythonPath = path.join(rootDir, ".venv", "Scripts", "python.exe");
  const code = [
    "import sys",
    "from pathlib import Path",
    "root = Path(sys.argv[2])",
    "sys.path.insert(0, str(root))",
    "from app import SessionLocal, upsert_products",
    "from stores import PROVIDERS",
    "name = sys.argv[1]",
    "provider_cls = PROVIDERS[name]",
    "with SessionLocal() as db:",
    "    count = upsert_products(db, provider_cls().iter_products(limit=300))",
    "    print(count)"
  ].join("\n");

  try {
    const { stdout } = await execFileAsync(pythonPath, ["-c", code, provider, rootDir], {
      cwd: rootDir,
      timeout: 180000,
      maxBuffer: 1024 * 1024
    });
    const count = Number(String(stdout).trim().split(/\s+/).pop()) || 0;
    res.json({ provider, status: "success", count, message: `Updated ${count} listings.` });
  } catch (error) {
    res.status(500).json({
      provider,
      status: "failed",
      message: error.stderr || error.stdout || error.message || "Refresh failed"
    });
  }
});

const fallbackNews = [
  {
    title: "GPU pricing and availability remain volatile",
    source: "PC hardware market",
    url: "https://www.pcgamer.com/hardware/graphics-cards/graphics-card-price-watch-deals/",
    published: "Market watch",
    summary: "Check current GPU launch, stock, and pricing coverage before locking a high-end graphics card purchase.",
    overview: "GPU pricing can change faster than the rest of a build list. Treat headline MSRP as a reference point and compare current in-stock offers before choosing a card.",
    imageUrl: "",
    category: "GPU"
  },
  {
    title: "Memory pricing is still a major build-cost risk",
    source: "Memory market",
    url: "https://www.techspot.com/news/112030-memory-prices-finally-falling-but-ram-remain-unaffordable.html",
    published: "Market watch",
    summary: "RAM prices can move quickly when supply shifts, so compare DDR5 kits shortly before buying.",
    overview: "RAM is one of the most volatile inputs for current PC builds. Watch DDR5 speed and kit capacity, not just the cheapest listing.",
    imageUrl: "",
    category: "RAM"
  }
];

const hardwareFeeds = [
  { source: "PC Gamer", url: "https://www.pcgamer.com/rss/" },
  { source: "Tom's Hardware", url: "https://www.tomshardware.com/feeds/all" },
  { source: "TechSpot", url: "https://www.techspot.com/backend.xml" },
  { source: "PCWorld", url: "https://www.pcworld.com/feed" },
  { source: "TechRadar", url: "https://www.techradar.com/rss" }
];

const newsKeywordGroups = [
  { category: "GPU", terms: ["gpu", "graphics card", "graphics cards", "geforce", "rtx", "radeon", "rx 9", "rx 8", "arc b"] },
  { category: "RAM", terms: ["ram", "ddr5", "ddr4", "memory price", "dram"] },
  { category: "CPUs", terms: ["cpu", "processor", "ryzen", "intel core", "core ultra", "arrow lake", "zen"] },
  { category: "Storage", terms: ["ssd", "nvme", "storage", "hard drive", "nand"] },
  { category: "Motherboards", terms: ["motherboard", "chipset", "am5", "lga", "b850", "x870", "z890"] }
];

const excludedNewsTerms = [
  "password", "malware", "ransomware", "programmer", "developer", "coding", "crypto mining",
  "data center", "datacenter", "ai partnership", "american manufacturing", "stock market",
  "windows 11", "microsoft", "usb-c", "cable", "standing desk", "desk pc"
];

function decodeHtml(value) {
  return String(value || "")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", "\"")
    .replaceAll("&apos;", "'")
    .replaceAll("&#39;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replace(/&#(\d+);/g, (_match, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_match, code) => String.fromCharCode(parseInt(code, 16)));
}

function stripTags(value) {
  return decodeHtml(String(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\bRead Entire Article\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim());
}

function xmlTag(item, tagName) {
  const escaped = tagName.replace(":", "\\:");
  return decodeHtml(
    item.match(new RegExp(`<${escaped}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]><\\/${escaped}>`, "i"))?.[1] ||
    item.match(new RegExp(`<${escaped}[^>]*>([\\s\\S]*?)<\\/${escaped}>`, "i"))?.[1] ||
    ""
  );
}

function attrValue(value, attr) {
  return decodeHtml(value.match(new RegExp(`${attr}=["']([^"']+)["']`, "i"))?.[1] || "");
}

function absoluteUrl(url, baseUrl) {
  if (!url) return "";
  try {
    return new URL(url, baseUrl).toString();
  } catch (_error) {
    return "";
  }
}

function imageFromItem(item, baseUrl) {
  const media = item.match(/<(?:media:content|media:thumbnail|enclosure)[^>]+>/i)?.[0] || "";
  const mediaUrl = attrValue(media, "url");
  if (mediaUrl && !/\.mp4|\.webm|\.mp3/i.test(mediaUrl)) return absoluteUrl(mediaUrl, baseUrl);
  const html = xmlTag(item, "content:encoded") || xmlTag(item, "description");
  const image = html.match(/<img[^>]+src=["']([^"']+)["']/i)?.[1] || "";
  return absoluteUrl(image, baseUrl);
}

function categorizeNews(title, summary = "") {
  const text = `${title} ${summary}`.toLowerCase();
  if (excludedNewsTerms.some((term) => text.includes(term))) return "";
  let best = { category: "", score: 0 };
  for (const group of newsKeywordGroups) {
    const score = group.terms.reduce((count, term) => {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
      return count + (new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "i").test(text) ? 1 : 0);
    }, 0);
    if (score > best.score) best = { category: group.category, score };
  }
  return best.score ? best.category : "";
}

function newsOverview(item) {
  const summary = stripTags(item.summary || "");
  const categoryNote = {
    GPU: "Why it matters: GPU launches and price movement can swing the total build cost more than any other part.",
    RAM: "Why it matters: DDR5 and DRAM pricing affects both budget builds and high-end platforms.",
    CPUs: "Why it matters: CPU releases can change motherboard, cooling, and platform value decisions.",
    Storage: "Why it matters: SSD and NAND pricing often determines whether a build should step up in capacity.",
    Motherboards: "Why it matters: motherboard availability and chipset pricing shape the platform upgrade path."
  }[item.category] || "Why it matters: this can affect timing, compatibility, or price choices for a new PC build.";
  return [summary, categoryNote].filter(Boolean).join(" ");
}

function parseFeedItems(xml, feed) {
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, 18).map((match) => {
    const item = match[1];
    const title = xmlTag(item, "title");
    const link = xmlTag(item, "link") || attrValue(item.match(/<link[^>]+href=["'][^"']+["'][^>]*>/i)?.[0] || "", "href");
    const pubDate = xmlTag(item, "pubDate") || xmlTag(item, "updated") || xmlTag(item, "dc:date");
    const rawSummary = xmlTag(item, "description") || xmlTag(item, "content:encoded");
    const summary = stripTags(rawSummary);
    const category = categorizeNews(title, summary);
    const imageUrl = imageFromItem(item, link || feed.url);
    return {
      title,
      url: absoluteUrl(link, feed.url),
      source: feed.source,
      published: pubDate,
      summary,
      overview: "",
      imageUrl,
      category
    };
  }).filter((item) => item.title && item.url && item.category);
}

async function enrichNewsItem(item) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch(item.url, {
      signal: controller.signal,
      headers: { "User-Agent": "Mozilla/5.0 PCBuilderLocalApp/2.0" }
    });
    if (!response.ok) return { ...item, overview: newsOverview(item) };
    const html = await response.text();
    const meta = (property) => {
      const escaped = property.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const tag = html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]*>`, "i"))?.[0] || "";
      return attrValue(tag, "content");
    };
    const imageUrl = item.imageUrl || absoluteUrl(meta("og:image") || meta("twitter:image"), item.url);
    const description = meta("og:description") || meta("description") || item.summary;
    return {
      ...item,
      imageUrl,
      summary: stripTags(item.summary || description),
      overview: newsOverview({ ...item, summary: description })
    };
  } catch (_error) {
    return { ...item, overview: newsOverview(item) };
  } finally {
    clearTimeout(timeout);
  }
}

function parseNewsItems(xml, category) {
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, 4).map((match) => {
    const item = match[1];
    const title = decodeHtml(item.match(/<title><!\[CDATA\[([\s\S]*?)\]\]><\/title>|<title>([\s\S]*?)<\/title>/)?.[1] || item.match(/<title>([\s\S]*?)<\/title>/)?.[1] || "");
    const link = decodeHtml(item.match(/<link>([\s\S]*?)<\/link>/)?.[1] || "");
    const pubDate = decodeHtml(item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1] || "");
    const source = decodeHtml(item.match(/<source[^>]*>([\s\S]*?)<\/source>/)?.[1] || "Google News");
    const description = stripTags(item.match(/<description><!\[CDATA\[([\s\S]*?)\]\]><\/description>|<description>([\s\S]*?)<\/description>/)?.[1] || "");
    return { title, url: link, source, published: pubDate, summary: description, overview: "", imageUrl: "", category };
  }).filter((item) => item.title && item.url);
}

app.get("/api/news", async (_req, res) => {
  const feeds = [
    ["GPU", "new GPU release RTX Radeon graphics card PC hardware"],
    ["RAM", "DDR5 RAM prices PC memory market"],
    ["CPUs", "new desktop CPU Ryzen Intel Core PC hardware"],
    ["Storage", "SSD prices NVMe PC parts"]
  ];
  try {
    const sourceFeedResults = await Promise.allSettled(hardwareFeeds.map(async (feed) => {
      const response = await fetch(feed.url, { headers: { "User-Agent": "PCBuilderLocalApp/2.0" } });
      if (!response.ok) throw new Error(`Source feed failed: ${response.status}`);
      return parseFeedItems(await response.text(), feed);
    }));
    const sourceItems = sourceFeedResults.flatMap((result) => result.status === "fulfilled" ? result.value : []);

    const googleResults = await Promise.all(feeds.map(async ([category, query]) => {
      const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
      const response = await fetch(url, { headers: { "User-Agent": "PCBuilderLocalApp/2.0" } });
      if (!response.ok) throw new Error(`News feed failed: ${response.status}`);
      return parseNewsItems(await response.text(), category);
    }));

    const seen = new Set();
    const merged = [...googleResults.flat(), ...sourceItems]
      .filter((item) => {
        const key = item.url.replace(/[?#].*$/, "") || item.title.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => (Date.parse(b.published) || 0) - (Date.parse(a.published) || 0))
      .slice(0, 12);
    const items = await Promise.all(merged.map(enrichNewsItem));
    res.json({ items: items.length ? items : fallbackNews, updatedAt: new Date().toISOString() });
  } catch (_error) {
    res.json({ items: fallbackNews, updatedAt: new Date().toISOString(), fallback: true });
  }
});

app.use(express.static(path.join(rootDir, "dist")));
app.get(/.*/, (_req, res) => {
  res.sendFile(path.join(rootDir, "dist", "index.html"));
});

app.listen(port, "127.0.0.1", () => {
  console.log(`PC Builder API running at http://127.0.0.1:${port}`);
});
