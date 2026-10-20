const productGrid = document.querySelector("#product-grid");
const catalogStatus = document.querySelector("#catalog-status");
const orderList = document.querySelector("#order-list");
const notificationList = document.querySelector("#notification-list");
const notificationStatus = document.querySelector("#notification-status");
const orderResult = document.querySelector("#order-result");
const cartLines = document.querySelector("#cart-lines");
const cartTotal = document.querySelector("#cart-total");
const cartCount = document.querySelector("#cart-count");
const checkoutButton = document.querySelector("#checkout-button");
const productDialog = document.querySelector("#product-dialog");

let products = [];
let stockBySku = {};
let cartItems = [];
let nextCartItemId = 1;
let isCheckingOut = false;

const bagSizes = ["12 oz", "2 lb"];
const grindOptions = ["Whole bean", "Espresso", "Drip", "French press"];

const bagPalettes = {
  "ETHIOPIA-YIRGACHEFFE": ["#c98d55", "#f1d6ad", "#8f5034"],
  "COLOMBIA-HUILA": ["#58745f", "#d7dfbd", "#354b3e"],
  "HOUSE-ESPRESSO": ["#714337", "#e8c09a", "#38241f"],
  "DECAF-COLOMBIA": ["#8a7057", "#e5d6b9", "#584536"],
  "SUMATRA-MANDELING": ["#59634c", "#d6c69f", "#343c30"],
  "GUATEMALA-ANTIGUA": ["#b37342", "#f0d49f", "#79442b"],
  "KENYA-AA": ["#a34e3e", "#f0c6a0", "#653229"],
};

function makeBag(product, size = "12 oz") {
  const bag = document.createElement("div");
  bag.className = "bag-model";
  bag.setAttribute("aria-hidden", "true");
  const [color, label, shade] = bagPalettes[product.sku] || ["#80543b", "#ead3b4", "#492f24"];
  bag.style.setProperty("--bag-color", color);
  bag.style.setProperty("--bag-label", label);
  bag.style.setProperty("--bag-shade", shade);
  bag.style.setProperty("--bag-scale", size === "2 lb" ? "1.08" : "1");

  for (const faceName of ["front", "back", "left", "right", "top", "bottom"]) {
    const face = document.createElement("div");
    face.className = `bag-face bag-${faceName}`;
    if (faceName === "front") {
      const seal = document.createElement("span");
      seal.className = "bag-seal";
      seal.textContent = `ROASTED FRESH · ${size.toUpperCase()}`;
      const mark = document.createElement("span");
      mark.className = "bag-mark";
      mark.textContent = "R";
      const brand = document.createElement("span");
      brand.className = "bag-brand";
      brand.textContent = "ROAST & RELAY";
      const name = document.createElement("span");
      name.className = "bag-coffee";
      name.textContent = product.name;
      const origin = document.createElement("span");
      origin.className = "bag-origin";
      origin.textContent = product.origin;
      const bottom = document.createElement("span");
      bottom.className = "bag-bottom-label";
      bottom.textContent = `${product.roast.toUpperCase()} ROAST · WHOLE BEAN`;
      const valve = document.createElement("span");
      valve.className = "bag-valve";
      face.append(seal, mark, brand, name, origin, bottom, valve);
    }
    bag.append(face);
  }
  return bag;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.message || `Request failed (${response.status})`);
  }
  return body;
}

function showCatalogError(message) {
  catalogStatus.textContent = message;
  productGrid.replaceChildren();
}

function renderProducts() {
  productGrid.replaceChildren();

  for (const product of products) {
    const card = document.createElement("article");
    card.className = "product-card";
    const art = document.createElement("div");
    art.className = "coffee-art";
    const bagShadow = document.createElement("span");
    bagShadow.className = "bag-shadow";
    bagShadow.setAttribute("aria-hidden", "true");
    const bag = makeBag(product);
    const viewButton = document.createElement("button");
    viewButton.className = "bag-view-trigger";
    viewButton.type = "button";
    viewButton.setAttribute("aria-label", `View ${product.name} bag details`);
    viewButton.textContent = "View bag ↗";
    art.append(bagShadow, bag, viewButton);
    const roast = document.createElement("span");
    roast.className = "roast-tag";
    roast.textContent = `${product.roast} roast`;
    const origin = document.createElement("p");
    origin.className = "product-origin";
    origin.textContent = `Origin · ${product.origin}`;
    const name = document.createElement("h3");
    name.textContent = product.name;
    const description = document.createElement("p");
    description.textContent = product.description;
    const tasting = document.createElement("p");
    tasting.className = "tasting-notes";
    const tastingLabel = document.createElement("strong");
    tastingLabel.textContent = "Tasting notes";
    const tastingValue = document.createElement("span");
    tastingValue.textContent = product.tasting_notes.join(" · ");
    tasting.append(tastingLabel, tastingValue);
    const brew = document.createElement("p");
    brew.className = "brew-tip";
    const brewLabel = document.createElement("strong");
    brewLabel.textContent = "Best for";
    const brewValue = document.createElement("span");
    brewValue.textContent = product.recommended_brew;
    brew.append(brewLabel, brewValue);

    const variants = document.createElement("div");
    variants.className = "product-variants";
    const sizeLabel = document.createElement("label");
    sizeLabel.textContent = "Bag size";
    const sizeSelect = document.createElement("select");
    sizeSelect.setAttribute("aria-label", `${product.name} bag size`);
    sizeLabel.append(sizeSelect);
    for (const size of bagSizes) {
      const option = document.createElement("option");
      option.value = size;
      option.textContent = `${size} · $${(product.size_prices[size] ?? product.price).toFixed(2)}`;
      sizeSelect.append(option);
    }
    const grindLabel = document.createElement("label");
    grindLabel.textContent = "Grind";
    const grindSelect = document.createElement("select");
    grindSelect.setAttribute("aria-label", `${product.name} grind`);
    grindLabel.append(grindSelect);
    for (const grind of grindOptions) {
      const option = document.createElement("option");
      option.value = grind;
      option.textContent = grind;
      grindSelect.append(option);
    }
    variants.append(sizeLabel, grindLabel);

    const meta = document.createElement("div");
    meta.className = "product-meta";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = `$${(product.size_prices["12 oz"] ?? product.price).toFixed(2)}`;
    const stock = document.createElement("span");
    stock.className = "stock";
    stock.textContent = stockBySku[product.sku] === undefined
      ? "Stock unavailable"
      : `${stockBySku[product.sku]} bags available`;
    meta.append(price, stock);
    const addButton = document.createElement("button");
    addButton.className = "button button-dark add-to-cart";
    addButton.type = "button";
    addButton.textContent = "Add to cart";
    sizeSelect.addEventListener("change", () => {
      const size = sizeSelect.value;
      price.textContent = `$${(product.size_prices[size] ?? product.price).toFixed(2)}`;
      bag.style.setProperty("--bag-scale", size === "2 lb" ? "1.08" : "1");
      bag.querySelector(".bag-seal").textContent = `ROASTED FRESH · ${size.toUpperCase()}`;
    });
    viewButton.addEventListener("click", () => openProductDialog(product, sizeSelect.value));
    addButton.addEventListener("click", () => {
      addCartItem(product, sizeSelect.value, grindSelect.value);
      renderCart();
    });
    card.append(art, roast, origin, name, description, tasting, brew, variants, meta, addButton);
    productGrid.append(card);
  }
}

function addCartItem(product, size, grind) {
  const existing = cartItems.find((item) => item.sku === product.sku && item.size === size && item.grind === grind);
  if (existing) {
    existing.quantity = Math.min(20, existing.quantity + 1);
    return;
  }
  cartItems.push({
    id: nextCartItemId++,
    sku: product.sku,
    name: product.name,
    size,
    grind,
    quantity: 1,
    unitPrice: product.size_prices[size] ?? product.price,
  });
}

function renderCart() {
  cartLines.replaceChildren();
  cartCount.textContent = String(cartItems.reduce((total, item) => total + item.quantity, 0));
  const total = cartItems.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
  cartTotal.textContent = `$${total.toFixed(2)}`;
  checkoutButton.disabled = cartItems.length === 0 || isCheckingOut;

  if (cartItems.length === 0) {
    const empty = document.createElement("p");
    empty.className = "cart-empty";
    empty.textContent = "Your cart is empty. Add a coffee to get started.";
    cartLines.append(empty);
    return;
  }

  for (const item of cartItems) {
    const line = document.createElement("div");
    line.className = "cart-line";
    const copy = document.createElement("div");
    copy.className = "cart-line-copy";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const detail = document.createElement("span");
    detail.textContent = `${item.size} · ${item.grind}`;
    const unitPrice = document.createElement("span");
    unitPrice.textContent = `$${item.unitPrice.toFixed(2)} each`;
    copy.append(name, detail, unitPrice);

    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = "20";
    quantity.value = String(item.quantity);
    quantity.setAttribute("aria-label", `${item.name} quantity`);
    quantity.addEventListener("change", () => {
      item.quantity = Math.max(1, Math.min(20, Number(quantity.value) || 1));
      renderCart();
    });

    const remove = document.createElement("button");
    remove.className = "remove-cart-item";
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${item.name} from cart`);
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      cartItems = cartItems.filter((cartItem) => cartItem.id !== item.id);
      renderCart();
    });

    const lineTotal = document.createElement("strong");
    lineTotal.textContent = `$${(item.unitPrice * item.quantity).toFixed(2)}`;
    line.append(copy, quantity, lineTotal, remove);
    cartLines.append(line);
  }
}

function openProductDialog(product, size = "12 oz") {
  const previewArt = document.querySelector("#quick-view-art");
  const shadow = document.createElement("span");
  shadow.className = "bag-shadow";
  shadow.setAttribute("aria-hidden", "true");
  previewArt.replaceChildren(shadow, makeBag(product, size));
  document.querySelector("#quick-view-roast").textContent = `${product.roast} roast · ${size}`;
  document.querySelector("#quick-view-name").textContent = product.name;
  document.querySelector("#quick-view-origin").textContent = `Origin · ${product.origin}`;
  document.querySelector("#quick-view-description").textContent = product.description;
  document.querySelector("#quick-view-tasting").textContent = product.tasting_notes.join(" · ");
  document.querySelector("#quick-view-brew").textContent = product.recommended_brew;
  document.querySelector("#quick-view-price").textContent = `$${(product.size_prices[size] ?? product.price).toFixed(2)}`;
  if (!productDialog.open) productDialog.showModal();
}

async function loadCatalog() {
  try {
    products = await getJson("/api/catalog");
    catalogStatus.textContent = "Catalog service online";
    renderProducts();
  } catch (error) {
    showCatalogError(`Catalog unavailable: ${error.message}`);
  }
}

function enableBagTilt() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  let activeBag = null;
  const resetTilt = () => {
    if (activeBag) {
      activeBag.style.removeProperty("--bag-rotate-x");
      activeBag.style.removeProperty("--bag-rotate-y");
      activeBag = null;
    }
  };
  const updateTilt = (event) => {
    if (event.pointerType !== "mouse") return;
    const art = event.target.closest(".coffee-art");
    if (!art) {
      resetTilt();
      return;
    }
    const bag = art.querySelector(".bag-model");
    if (!bag) return;
    if (activeBag && activeBag !== bag) resetTilt();
    activeBag = bag;
    const bounds = art.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    bag.style.setProperty("--bag-rotate-y", `${-22 + x * 52}deg`);
    bag.style.setProperty("--bag-rotate-x", `${5 + y * -18}deg`);
  };

  productGrid.addEventListener("pointermove", updateTilt);
  productDialog.addEventListener("pointermove", updateTilt);
  productGrid.addEventListener("pointerleave", resetTilt);
  productDialog.addEventListener("pointerleave", resetTilt);
}

async function loadInventory() {
  try {
    const inventory = await getJson("/api/inventory");
    stockBySku = Object.fromEntries(inventory.map((item) => [item.sku, item.quantity]));
    if (products.length) renderProducts();
  } catch {
    catalogStatus.textContent = "Catalog online · inventory temporarily unavailable";
  }
}

async function loadOrders() {
  try {
    const orders = await getJson("/api/orders");
    orderList.replaceChildren();
    if (!orders.length) {
      orderList.innerHTML = '<p class="muted">No orders yet. Your first coffee order can go here.</p>';
      return;
    }
    for (const order of orders) {
      const row = document.createElement("div");
      row.className = "record-row";
      const details = document.createElement("strong");
      details.textContent = `${order.product_name} · ${order.bag_size || "12 oz"} · ${order.grind || "Whole bean"} × ${order.quantity} · ${order.customer_name}`;
      const state = document.createElement("span");
      state.textContent = `${order.status} · $${order.total.toFixed(2)}`;
      row.append(details, state);
      orderList.append(row);
    }
  } catch (error) {
    orderList.innerHTML = `<p class="muted">Order service unavailable: ${error.message}</p>`;
  }
}

async function loadNotifications() {
  try {
    const notifications = await getJson("/api/notifications");
    notificationStatus.textContent = "Notification service online";
    notificationList.replaceChildren();
    if (!notifications.length) {
      notificationList.innerHTML = '<p class="muted">No order updates yet.</p>';
      return;
    }
    for (const notification of notifications) {
      const row = document.createElement("div");
      row.className = "record-row";
      const message = document.createElement("strong");
      message.textContent = notification.message;
      const orderId = document.createElement("span");
      orderId.textContent = `Order ${notification.order_id.slice(0, 8)}`;
      row.append(message, orderId);
      notificationList.append(row);
    }
  } catch {
    notificationStatus.textContent = "Notification service unavailable";
    notificationList.innerHTML = '<p class="muted">Coffee ordering can continue while notifications recover.</p>';
  }
}

document.querySelector("#order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const orderForm = event.currentTarget;
  const customerName = document.querySelector("#customer-name").value.trim();
  if (!cartItems.length || !customerName || isCheckingOut) return;
  isCheckingOut = true;
  checkoutButton.textContent = "Placing orders…";
  orderResult.textContent = "Submitting your coffee selections…";
  renderCart();

  const completedIds = new Set();
  const failures = [];
  let placedTotal = 0;
  for (const item of [...cartItems]) {
    try {
      const order = await getJson("/api/orders", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          customer_name: customerName,
          sku: item.sku,
          quantity: item.quantity,
          bag_size: item.size,
          grind: item.grind,
        }),
      });
      completedIds.add(item.id);
      placedTotal += order.total;
    } catch (error) {
      failures.push(`${item.name}: ${error.message}`);
    }
  }

  cartItems = cartItems.filter((item) => !completedIds.has(item.id));
  isCheckingOut = false;
  checkoutButton.textContent = "Place order";
  orderResult.textContent = failures.length
    ? `${completedIds.size} item(s) placed for $${placedTotal.toFixed(2)}. Still in cart: ${failures.join("; ")}`
    : `Order placed for $${placedTotal.toFixed(2)} across ${completedIds.size} selection(s).`;
  if (completedIds.size) await Promise.all([loadOrders(), loadNotifications(), loadInventory()]);
  renderCart();
});

document.querySelector("#refresh-orders").addEventListener("click", loadOrders);
document.querySelector("#close-product-dialog").addEventListener("click", () => productDialog.close());
productDialog.addEventListener("click", (event) => {
  if (event.target === productDialog) productDialog.close();
});

loadCatalog();
enableBagTilt();
renderCart();
loadInventory();
loadOrders();
loadNotifications();
