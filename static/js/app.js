function stockClass(value) {
  const text = (value || "").toLowerCase();
  if (text.includes("out")) return "stock-out";
  if (text.includes("pre")) return "stock-pre";
  if (text.includes("stock") || text.includes("available")) return "stock-in";
  return "stock-unknown";
}

function categoryShort(value) {
  const text = (value || "").toLowerCase();
  if (text.includes("processor") || text.includes("cpu")) return "CPU";
  if (text.includes("graphics") || text.includes("gpu")) return "GPU";
  if (text.includes("ram") || text.includes("memory")) return "RAM";
  if (text.includes("ssd") || text.includes("hdd") || text.includes("storage")) return "SSD";
  if (text.includes("power") || text.includes("psu")) return "PSU";
  if (text.includes("monitor")) return "LCD";
  return "PC";
}

function formatPrice(value) {
  if (!value) return "Ask store";
  return `LKR ${Number(value).toLocaleString()}`;
}

function createProductImageMarkup(imageUrl, name, category) {
  const hasImage = imageUrl && imageUrl !== "/static/img/placeholder.svg";
  return `
    <div class="product-image-shell">
      <div class="product-image-frame ${hasImage ? "" : "no-image"}" data-image-frame>
        ${hasImage ? `<img src="${imageUrl}" alt="${name}" data-product-image>` : ""}
        <div class="product-image-placeholder">
          <span>${categoryShort(category)}</span>
          <small>Image unavailable</small>
        </div>
      </div>
    </div>
  `;
}

function createPriceListMarkup(offers) {
  const rows = offers.map((offer) => `
    <div class="price-row ${offer.best ? "best-price-row" : ""}">
      <div class="price-row-main">
        <span class="price-store">${offer.store}</span>
        <span class="price-value">${formatPrice(offer.price_lkr)}</span>
      </div>
      <div class="price-row-meta">
        <span class="price-stock ${stockClass(offer.availability)}">${offer.availability || "Unknown"}</span>
        ${offer.best && offer.price_lkr ? '<span class="price-flag">Best price</span>' : ""}
      </div>
    </div>
  `).join("");
  return `
    <div class="price-list expanded">
      <div class="price-list-head">
        <strong>Available prices</strong>
        <span>${offers.length} store${offers.length === 1 ? "" : "s"}</span>
      </div>
      <div class="price-list-rows">${rows}</div>
    </div>
  `;
}

function syncFavouriteButtons(productId, isActive) {
  document.querySelectorAll(`[data-fav="${productId}"]`).forEach((button) => {
    button.classList.toggle("active", isActive);
  });
  const modalFav = document.querySelector("[data-modal-fav]");
  if (modalFav && modalFav.dataset.fav === String(productId)) {
    modalFav.classList.toggle("active", isActive);
    modalFav.textContent = isActive ? "Favourited" : "Favourite";
  }
}

const detailsCache = new Map();

async function openDetailsModal(detailsId) {
  const modal = document.querySelector("[data-details-modal]");
  if (!modal) return;

  if (!detailsCache.has(detailsId)) {
    const response = await fetch(`/products/${detailsId}/details`);
    if (!response.ok) return;
    detailsCache.set(detailsId, await response.json());
  }

  const details = detailsCache.get(detailsId);
  const modalName = modal.querySelector("[data-modal-name]");
  const modalCategory = modal.querySelector("[data-modal-category]");
  const modalStock = modal.querySelector("[data-modal-stock]");
  const modalPrices = modal.querySelector("[data-modal-prices]");
  const modalFeatures = modal.querySelector("[data-modal-features]");
  const modalFeaturesSection = modal.querySelector("[data-modal-features-section]");
  const modalDescription = modal.querySelector("[data-modal-description]");
  const modalDescriptionSection = modal.querySelector("[data-modal-description-section]");
  const modalNotes = modal.querySelector("[data-modal-notes]");
  const modalNotesSection = modal.querySelector("[data-modal-notes-section]");
  const modalBuild = modal.querySelector("[data-modal-build]");
  const modalCompare = modal.querySelector("[data-modal-compare]");
  const modalFav = modal.querySelector("[data-modal-fav]");
  const modalImage = modal.querySelector("[data-modal-image]");

  modalName.textContent = details.name || "Product details";
  modalCategory.textContent = `${details.category}`;
  modalStock.textContent = details.stock_status || "Unknown";
  modalStock.className = `stock-badge ${stockClass(details.stock_status)}`;
  modalPrices.innerHTML = createPriceListMarkup(details.offers || []);
  modalImage.innerHTML = createProductImageMarkup(details.image_url, details.name || "Product image", details.category || "PC");
  modalImage.querySelectorAll("[data-product-image]").forEach((img) => {
    img.addEventListener("error", () => {
      img.closest("[data-image-frame]")?.classList.add("image-failed");
      img.remove();
    }, { once: true });
  });

  const features = details.features || [];
  modalFeatures.innerHTML = features.map((feature) => `<li>${feature}</li>`).join("");
  modalFeaturesSection.hidden = features.length === 0;

  modalDescription.textContent = details.description || "";
  modalDescriptionSection.hidden = !details.description;

  const notes = details.notes || [];
  modalNotes.innerHTML = notes.map((note) => `<p>${note}</p>`).join("");
  modalNotesSection.hidden = notes.length === 0;

  modalBuild.href = `/builds/add-offer?offer_ids=${details.offer_ids}`;
  modalCompare.href = `/compare?q=${encodeURIComponent(details.compare_query || details.name || "")}`;
  modalFav.dataset.fav = details.favourite_id;
  const isActive = document.querySelector(`[data-fav="${details.favourite_id}"]`)?.classList.contains("active");
  modalFav.classList.toggle("active", isActive);
  modalFav.textContent = isActive ? "Favourited" : "Favourite";

  if (typeof modal.showModal === "function") {
    modal.showModal();
  } else {
    modal.setAttribute("open", "open");
  }
}

document.addEventListener("click", async (event) => {
  const fav = event.target.closest("[data-fav]");
  if (fav) {
    event.preventDefault();
    const response = await fetch(`/favourites/${fav.dataset.fav}`, { method: "POST" });
    if (response.ok) {
      const data = await response.json();
      syncFavouriteButtons(fav.dataset.fav, data.favourite);
    }
    return;
  }

  const openModal = event.target.closest("[data-modal-open]");
  if (openModal) {
    event.preventDefault();
    openDetailsModal(openModal.dataset.detailsId);
    return;
  }

  const closeModal = event.target.closest("[data-modal-close]");
  if (closeModal) {
    event.preventDefault();
    closeModal.closest("dialog")?.close();
    return;
  }

  const toggle = event.target.closest("[data-view-toggle]");
  if (toggle) {
    const products = document.querySelector("[data-products]");
    products?.classList.toggle("table");
    const label = toggle.querySelector("[data-view-label]");
    if (label) {
      label.textContent = products?.classList.contains("table") ? "List" : "Grid";
    }
    return;
  }

  const navToggle = event.target.closest("[data-nav-toggle]");
  if (navToggle) {
    document.querySelector("[data-nav]")?.classList.toggle("open");
    navToggle.classList.toggle("open");
  }
});

document.addEventListener("change", (event) => {
  const mode = event.target.closest("[data-selection-method]");
  if (!mode) return;
  const form = mode.closest("form");
  const manual = form?.querySelector("[data-manual-offer]");
  const preferred = form?.querySelector("[data-preferred-store]");
  if (manual) manual.style.display = mode.value === "manual" ? "" : "none";
  if (preferred) preferred.style.display = mode.value === "preferred_store" ? "" : "none";
});

document.addEventListener("click", (event) => {
  const modal = document.querySelector("[data-details-modal]");
  if (!modal || !modal.open) return;
  if (event.target === modal) {
    modal.close();
  }
});

document.querySelectorAll("[data-selection-method]").forEach((select) => {
  select.dispatchEvent(new Event("change", { bubbles: true }));
});
