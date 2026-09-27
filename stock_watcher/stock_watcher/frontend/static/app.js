// app.js -- talks to the Stock Watcher API and renders the dashboard.
// No build step, no framework: fetch + DOM updates, kept deliberately simple.

const money = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

let allProducts = [];

async function getJSON(url, options) {
  const res = await fetch(url, options);
  return res.json();
}

function productOption(p) {
  const opt = document.createElement("option");
  opt.value = p.product_id;
  opt.textContent = `${p.name} (${p.current_stock} in stock)`;
  return opt;
}

function statusLabel(status) {
  return { ok: "OK", low: "Low", out_of_stock: "Out of stock" }[status] || status;
}

// ---- inventory table -----------------------------------------------------

function renderInventory(products, filter = "") {
  const tbody = document.querySelector("#inventory-table tbody");
  tbody.innerHTML = "";
  const term = filter.trim().toLowerCase();
  const rows = term
    ? products.filter((p) => p.name.toLowerCase().includes(term) || p.category.toLowerCase().includes(term))
    : products;

  for (const p of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.category}</td>
      <td>${p.current_stock}</td>
      <td>${p.reorder_threshold}</td>
      <td><span class="status-badge status-${p.status}">${statusLabel(p.status)}</span></td>
    `;
    tbody.appendChild(tr);
  }
}

// ---- alerts ---------------------------------------------------------------

function renderAlertList(el, items, emptyText, render) {
  el.innerHTML = "";
  if (items.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = emptyText;
    el.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.innerHTML = render(item);
    el.appendChild(li);
  }
}

async function loadAlerts() {
  const { low_stock, overstocked } = await getJSON("/api/alerts");
  renderAlertList(
    document.getElementById("low-stock-list"),
    low_stock,
    "Nothing is running low right now.",
    (p) => `<span>${p.name}</span><span class="alert-qty">${p.current_stock} left (reorder at ${p.reorder_threshold})</span>`
  );
  renderAlertList(
    document.getElementById("overstock-list"),
    overstocked,
    "Nothing looks overstocked right now.",
    (p) => `<span>${p.name}</span><span class="alert-qty">${p.current_stock} on hand${p.days_of_stock_remaining ? ` (~${p.days_of_stock_remaining}d)` : ""}</span>`
  );
}

// ---- top sellers / dead stock ---------------------------------------------

async function loadTopSellers() {
  const days = document.getElementById("top-sellers-days").value;
  const url = days ? `/api/top-sellers?days=${days}&n=10` : "/api/top-sellers?n=10";
  const rows = await getJSON(url);
  const tbody = document.querySelector("#top-sellers-table tbody");
  tbody.innerHTML = rows.length
    ? rows.map((r) => `<tr><td>${r.name}</td><td>${r.category}</td><td>${r.quantity_sold}</td><td>${money(r.revenue)}</td></tr>`).join("")
    : `<tr><td colspan="4">No sales recorded in this window.</td></tr>`;
}

async function loadDeadStock() {
  const days = document.getElementById("dead-stock-days").value;
  const rows = await getJSON(`/api/dead-stock?days=${days}`);
  const tbody = document.querySelector("#dead-stock-table tbody");
  tbody.innerHTML = rows.length
    ? rows.map((r) => `<tr><td>${r.name}</td><td>${r.category}</td><td>${r.current_stock}</td></tr>`).join("")
    : `<tr><td colspan="3">Nothing qualifies as dead stock in this window.</td></tr>`;
}

// ---- simulators -------------------------------------------------------------

function showResult(el, text, cls) {
  el.textContent = text;
  el.className = `result show ${cls}`;
}

async function handlePurchaseCheck(e) {
  e.preventDefault();
  const product_id = document.getElementById("purchase-product").value;
  const quantity = parseInt(document.getElementById("purchase-qty").value, 10);
  const result = await getJSON("/api/purchase-check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id, quantity }),
  });
  const el = document.getElementById("purchase-result");
  if (result.error) return showResult(el, result.error, "flag");
  showResult(el, result.message, result.overstocked ? "flag" : "ok");
}

async function handleSale(e) {
  e.preventDefault();
  const product_id = document.getElementById("sale-product").value;
  const quantity = parseInt(document.getElementById("sale-qty").value, 10);
  const result = await getJSON("/api/sale", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id, quantity }),
  });
  const el = document.getElementById("sale-result");
  if (result.error) return showResult(el, result.error, "flag");
  showResult(el, result.message, result.low_stock ? "flag" : "ok");
  // refresh everything that could have changed
  await refreshAll();
}

// ---- boot -------------------------------------------------------------------

async function refreshAll() {
  allProducts = await getJSON("/api/products");
  renderInventory(allProducts, document.getElementById("inventory-search").value);

  const purchaseSelect = document.getElementById("purchase-product");
  const saleSelect = document.getElementById("sale-product");
  const prevPurchase = purchaseSelect.value;
  const prevSale = saleSelect.value;
  purchaseSelect.innerHTML = "";
  saleSelect.innerHTML = "";
  for (const p of allProducts) {
    purchaseSelect.appendChild(productOption(p));
    saleSelect.appendChild(productOption(p));
  }
  if (prevPurchase) purchaseSelect.value = prevPurchase;
  if (prevSale) saleSelect.value = prevSale;

  await Promise.all([loadAlerts(), loadTopSellers(), loadDeadStock()]);
}

document.getElementById("purchase-form").addEventListener("submit", handlePurchaseCheck);
document.getElementById("sale-form").addEventListener("submit", handleSale);
document.getElementById("top-sellers-days").addEventListener("change", loadTopSellers);
document.getElementById("dead-stock-days").addEventListener("change", loadDeadStock);
document.getElementById("inventory-search").addEventListener("input", (e) => renderInventory(allProducts, e.target.value));

refreshAll();
