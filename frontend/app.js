const productGrid = document.querySelector("#product-grid");
const catalogStatus = document.querySelector("#catalog-status");
const coffeeChoice = document.querySelector("#coffee-choice");
const orderList = document.querySelector("#order-list");
const notificationList = document.querySelector("#notification-list");
const notificationStatus = document.querySelector("#notification-status");
const orderResult = document.querySelector("#order-result");

let products = [];
let stockBySku = {};

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
  coffeeChoice.replaceChildren();

  for (const product of products) {
    const card = document.createElement("article");
    card.className = "product-card";
    const art = document.createElement("div");
    art.className = "coffee-art";
    const roast = document.createElement("span");
    roast.className = "roast-tag";
    roast.textContent = `${product.roast} roast`;
    const name = document.createElement("h3");
    name.textContent = product.name;
    const description = document.createElement("p");
    description.textContent = product.description;
    const meta = document.createElement("div");
    meta.className = "product-meta";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = `$${product.price.toFixed(2)}`;
    const stock = document.createElement("span");
    stock.className = "stock";
    stock.textContent = stockBySku[product.sku] === undefined
      ? "Stock unavailable"
      : `${stockBySku[product.sku]} bags available`;
    meta.append(price, stock);
    card.append(art, roast, name, description, meta);
    productGrid.append(card);

    const option = document.createElement("option");
    option.value = product.sku;
    option.textContent = `${product.name} — $${product.price.toFixed(2)}`;
    coffeeChoice.append(option);
  }
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
      details.textContent = `${order.product_name} × ${order.quantity} · ${order.customer_name}`;
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
  orderResult.textContent = "Submitting your order…";
  const form = new FormData(orderForm);
  const payload = {
    customer_name: form.get("customer_name").trim(),
    sku: form.get("sku"),
    quantity: Number(form.get("quantity")),
  };

  try {
    const order = await getJson("/api/orders", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    orderResult.textContent = `Order placed: ${order.product_name} × ${order.quantity}. Total $${order.total.toFixed(2)}. Order ${order.order_id.slice(0, 8)}.`;
    orderForm.reset();
    document.querySelector("#quantity").value = "1";
    await Promise.all([loadOrders(), loadNotifications(), loadInventory()]);
  } catch (error) {
    orderResult.textContent = `Order not placed: ${error.message}`;
  }
});

document.querySelector("#refresh-orders").addEventListener("click", loadOrders);

loadCatalog();
loadInventory();
loadOrders();
loadNotifications();
