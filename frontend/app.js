/* ═══════════════════════════════════════════
   Warehouse Automation · app.js
   Full application logic — separated from HTML/CSS
═══════════════════════════════════════════ */

'use strict';

/* ════════════════════════════════════════════
   GLOBALS
════════════════════════════════════════════ */
const API = '';

// Check authentication
if (!localStorage.getItem('access_token')) {
  window.location.href = 'auth.html';
}

function logout() {
  localStorage.removeItem('access_token');
  window.location.href = 'auth.html';
}

// Global fetch wrapper to attach token
const originalFetch = window.fetch;
window.fetch = async function() {
  let [resource, config] = arguments;
  if (!config) config = {};
  if (!config.headers) config.headers = {};
  
  const token = localStorage.getItem('access_token');
  if (token) {
    if (config.headers instanceof Headers) {
      config.headers.set('Authorization', `Bearer ${token}`);
    } else {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
  }
  
  const response = await originalFetch(resource, config);
  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('access_token');
    window.location.href = 'auth.html';
  }
  return response;
};
let allProducts    = [];
let billingProducts = [];
let cart           = [];
let salesChart     = null;
let categoryChart  = null;
let forecastChart  = null;
let editingProductId = null;
let currentBillId    = null;
let currentBillNumber = null;
let currentAvgSales = 0; // For stock feedback
let _forecastAnimTimer = null;

/* ════════════════════════════════════════════
   SIDEBAR — MOBILE TOGGLE
════════════════════════════════════════════ */
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebarOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
  document.body.style.overflow = '';
}

/* ════════════════════════════════════════════
   ROUTING
════════════════════════════════════════════ */
const pageMeta = {
  dashboard: { title: 'Dashboard',        sub: 'Real-time inventory overview' },
  products:  { title: 'Products',          sub: 'Manage your product catalog' },
  billing:   { title: 'Billing Desk',      sub: 'Live POS — create bills & deduct stock' },
  bills:     { title: 'Bill History',      sub: 'All transactions' },
  forecast:  { title: 'AI Demand Forecast',sub: 'Machine-learning powered demand predictions' },
  reorder:   { title: 'Reorder Plan',      sub: 'EOQ-based reorder recommendations' },
  upload:    { title: 'Upload CSV',        sub: 'Import historical sales data' },
  manual:    { title: 'Manual Sales Entry',sub: 'Add daily sales without CSV' },
  alerts:    { title: 'Stock Alerts',      sub: 'Low-stock and reorder notifications' },
  reports:   { title: 'Reports & Exports', sub: 'Download Excel reports and manage AI models' },
  settings:  { title: 'Settings',          sub: 'Manage your profile and application preferences' },
};

function goTo(page) {
  // Close mobile sidebar on nav
  closeSidebar();

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  if (!pageEl) return;
  pageEl.classList.add('active');
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');

  const meta = pageMeta[page] || {};
  document.getElementById('pageTitle').textContent = meta.title || page;
  document.getElementById('pageSub').textContent   = meta.sub   || '';

  const loaders = {
    dashboard: loadDashboard,
    products:  loadProducts,
    billing:   loadBillingProducts,
    bills:     loadBills,
    forecast:  loadForecastProducts,
    reorder:   () => { loadReorderProducts(); loadReorderPlan(); },
    upload:    loadUploadStatus,
    alerts:    loadAlerts,
    reports:   loadReportProducts,
    settings:  loadSettings,
    manual:    () => { loadManualProducts(); loadManualSales(); },
  };
  if (loaders[page]) loaders[page]();
  
  // Persist current page across refreshes
  localStorage.setItem('active_page', page);
}

function refreshPage() {
  const active = document.querySelector('.page.active');
  if (!active) return;
  const id = active.id.replace('page-', '');
  goTo(id);
}

/* ════════════════════════════════════════════
   CLOCK
════════════════════════════════════════════ */
function updateClock() {
  const el = document.getElementById('currentDateTime');
  if (el) el.textContent = new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

/* ════════════════════════════════════════════
   API HEALTH CHECK
════════════════════════════════════════════ */
async function checkAPI() {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  try {
    const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      dot.className = 'status-dot online';
      txt.textContent = 'API Online';
    } else throw new Error();
  } catch {
    dot.className = 'status-dot offline';
    txt.textContent = 'API Offline';
  }
}

/* ════════════════════════════════════════════
   TOAST
════════════════════════════════════════════ */
function toast(msg, type = 'info') {
  const c = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

/* ════════════════════════════════════════════
   MODAL
════════════════════════════════════════════ */
function openModal(id)  { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

/* ════════════════════════════════════════════
   FORMAT HELPERS
════════════════════════════════════════════ */
function fmt(n)    { return typeof n === 'number' ? n.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : (n ?? '—'); }
function fmtCur(n) { return 'Rs. ' + (n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

/* ════════════════════════════════════════════
   FORECAST LOADING ANIMATION
════════════════════════════════════════════ */
const _forecastSteps = [
  { id: 'fstep1', msg: 'Loading historical sales data…' },
  { id: 'fstep2', msg: 'Preprocessing & feature engineering…' },
  { id: 'fstep3', msg: 'Training AI models — this takes a moment…' },
  { id: 'fstep4', msg: 'Almost done — selecting best model…' },
];
const _stepDelays = [0, 3000, 7000, 18000];

function startForecastLoadingAnimation() {
  _forecastSteps.forEach((s, i) => {
    const el = document.getElementById(s.id);
    if (!el) return;
    el.style.opacity = i === 0 ? '1' : '0.35';
    el.querySelector('.fstep-icon').textContent = '⏳';
    el.style.color = 'var(--text3)';
  });
  const msgEl = document.getElementById('forecastLoadingMsg');
  if (msgEl) msgEl.textContent = _forecastSteps[0].msg;
  clearTimeout(_forecastAnimTimer);

  function advance(idx) {
    if (idx >= _forecastSteps.length) return;
    const s = _forecastSteps[idx];
    const el = document.getElementById(s.id);
    if (el) {
      for (let i = 0; i < idx; i++) {
        const prev = document.getElementById(_forecastSteps[i].id);
        if (prev) { prev.querySelector('.fstep-icon').textContent = '✅'; prev.style.opacity = '0.7'; }
      }
      el.style.opacity = '1';
      el.querySelector('.fstep-icon').textContent = '🔄';
      el.style.color = 'var(--text2)';
    }
    const m = document.getElementById('forecastLoadingMsg');
    if (m) m.textContent = s.msg;
    if (idx + 1 < _forecastSteps.length) {
      _forecastAnimTimer = setTimeout(() => advance(idx + 1), _stepDelays[idx + 1] - _stepDelays[idx]);
    }
  }
  advance(0);
}

function stopForecastLoadingAnimation() {
  clearTimeout(_forecastAnimTimer);
  _forecastAnimTimer = null;
}

/* ════════════════════════════════════════════
   DASHBOARD
════════════════════════════════════════════ */
async function loadDashboard() {
  try {
    const [summary, billing] = await Promise.all([
      fetch(`${API}/products/dashboard/summary`).then(r => r.json()),
      fetch(`${API}/billing/stats`).then(r => r.json()),
    ]);

    document.getElementById('kpiProducts').textContent    = fmt(summary.total_products);
    document.getElementById('kpiValue').textContent       = fmtCur(summary.inventory_value);
    document.getElementById('kpiLow').textContent         = fmt(summary.low_stock);
    document.getElementById('kpiOut').textContent         = fmt(summary.out_of_stock);
    document.getElementById('kpiTodayRevenue').textContent = fmtCur(billing.today_revenue);
    document.getElementById('kpiTodayBills').textContent  = `${billing.today_bills} bills today`;
    document.getElementById('kpiTotalRevenue').textContent = fmtCur(billing.total_revenue);
    document.getElementById('kpiTotalBills').textContent  = `${billing.total_bills} total bills`;

    // Alert badge
    const alertCount = summary.unread_alerts;
    const badge = document.getElementById('alertBadge');
    if (alertCount > 0) { badge.textContent = alertCount; badge.style.display = ''; }
    else badge.style.display = 'none';

    // Sales chart
    const labels   = summary.daily_sales.map(d => d.date.slice(5));
    const values   = summary.daily_sales.map(d => d.units);
    const revenues = summary.daily_sales.map(d => d.revenue);
    if (salesChart) { try { salesChart.destroy(); } catch (_) {} }
    salesChart = new Chart(document.getElementById('salesChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Units Sold', data: values, backgroundColor: 'rgba(79,110,247,.7)', borderRadius: 5, yAxisID: 'y' },
          { label: 'Revenue ₹', data: revenues, type: 'line', borderColor: '#06d6a0', backgroundColor: 'rgba(6,214,160,.1)', fill: true, tension: .4, pointRadius: 2, yAxisID: 'y1' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#a0a3c4', font: { size: 11 } } } },
        scales: {
          x:  { ticks: { color: '#5e6189' }, grid: { color: 'rgba(255,255,255,.04)' } },
          y:  { ticks: { color: '#5e6189' }, grid: { color: 'rgba(255,255,255,.04)' }, position: 'left' },
          y1: { ticks: { color: '#5e6189' }, grid: { display: false }, position: 'right' },
        },
      },
    });

    // Category chart
    if (categoryChart) { try { categoryChart.destroy(); } catch (_) {} }
    const cats = summary.category_breakdown;
    categoryChart = new Chart(document.getElementById('categoryChart'), {
      type: 'doughnut',
      data: {
        labels: cats.map(c => c.category),
        datasets: [{ data: cats.map(c => c.count), backgroundColor: ['#4f6ef7','#06d6a0','#f59e0b','#f43f5e','#38bdf8','#7c3aed','#10b981'], borderWidth: 0 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { color: '#a0a3c4', font: { size: 11 }, boxWidth: 12, padding: 8 } } },
      },
    });

    // Top products
    const topList = document.getElementById('topProductsList');
    const medals = ['🥇','🥈','🥉','4️⃣','5️⃣'];
    topList.innerHTML = summary.top_products.map((p, i) => `
      <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid rgba(37,39,66,.5)">
        <span style="font-size:16px">${medals[i] || ''}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.product_name}</div>
          <div style="font-size:11px;color:var(--text3)">${p.total_sold} units / 30d</div>
        </div>
      </div>`).join('') || '<div class="empty-state"><p>No sales data yet</p></div>';

  } catch (e) {
    console.error('Dashboard load failed:', e);
    toast('Failed to load dashboard data', 'error');
  }
}

/* ════════════════════════════════════════════
   PRODUCTS
════════════════════════════════════════════ */
async function loadProducts() {
  try {
    const data = await fetch(`${API}/products/`).then(r => r.json());
    allProducts = data.products || [];
    renderProductTable(allProducts);
  } catch { toast('Failed to load products', 'error'); }
}

function filterProducts() {
  const q = document.getElementById('productSearch').value.toLowerCase();
  const statusVal = document.getElementById('statusFilter').value;
  const filtered = allProducts.filter(p => {
    const pStatus = p.current_stock === 0 ? 'out' : (p.reorder_point && p.current_stock <= p.reorder_point) ? 'low' : 'ok';
    const matchesQuery = !q || p.product_name.toLowerCase().includes(q) || p.product_id.toLowerCase().includes(q);
    const matchesStatus = !statusVal || pStatus === statusVal;
    return matchesQuery && matchesStatus;
  });
  renderProductTable(filtered);
}

function renderProductTable(products) {
  const tbody = document.getElementById('productTableBody');
  if (!products.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="icon">📦</div><p>No products found</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = products.map(p => {
    const status = p.current_stock === 0 ? 'out' : (p.reorder_point && p.current_stock <= p.reorder_point) ? 'low' : 'ok';
    const tagClass = { ok: 'tag-ok', low: 'tag-low', out: 'tag-out' }[status];
    const tagText  = { ok: '✓ In Stock', low: '⚠ Low Stock', out: '✗ Out of Stock' }[status];
    return `<tr>
      <td>
        <div style="font-weight:500">${p.product_name}</div>
        <div class="mono" style="font-size:11px;color:var(--text3)">${p.product_id}</div>
      </td>
      <td><span class="tag tag-purple">${p.category}</span></td>
      <td>
        <div style="font-weight:600">${fmt(p.current_stock)} <span style="font-size:11px;color:var(--text3)">${p.unit || 'pcs'}</span></div>
        ${p.reorder_point ? `<div style="font-size:11px;color:var(--text3)">Reorder at ${p.reorder_point}</div>` : ''}
      </td>
      <td>
        <div style="font-weight:600">${p.daily_sales || 0} <span style="font-size:11px;color:var(--text3)">${p.unit || 'pcs'}/day</span></div>
      </td>
      <td>${fmtCur(p.selling_price)}</td>
      <td><span class="tag ${tagClass}">${tagText}</span></td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" onclick="openEditProduct('${p.product_id}')">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct('${p.product_id}','${p.product_name}')">Del</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function openProductModal() {
  editingProductId = null;
  document.getElementById('productModalTitle').textContent = 'Add New Product';
  ['fProductId','fProductName','fCategory','fStock','fReorderPoint','fSellingPrice','fCostPrice','fDescription'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  document.getElementById('fLeadTime').value = '5';
  document.getElementById('fUnit').value = 'pcs';
  document.getElementById('fProductId').disabled = false;
  currentAvgSales = 0;
  if(document.getElementById('stockFeedback')) document.getElementById('stockFeedback').textContent = '';
  openModal('productModal');
}

function openEditProduct(productId) {
  const p = allProducts.find(x => x.product_id === productId);
  if (!p) return;
  editingProductId = productId;
  document.getElementById('productModalTitle').textContent = 'Edit Product';
  document.getElementById('fProductId').value = p.product_id;
  document.getElementById('fProductId').disabled = true;
  document.getElementById('fProductName').value = p.product_name;
  document.getElementById('fCategory').value = p.category;
  document.getElementById('fStock').value = p.current_stock;
  document.getElementById('fReorderPoint').value = p.reorder_point || '';
  document.getElementById('fSellingPrice').value = p.selling_price;
  document.getElementById('fCostPrice').value = p.cost_price || '';
  document.getElementById('fLeadTime').value = p.supplier_lead_time;
  document.getElementById('fUnit').value = p.unit || 'pcs';
  document.getElementById('fDescription').value = p.description || '';
  
  // Reset feedback
  document.getElementById('stockFeedback').textContent = 'Loading sales data…';
  currentAvgSales = 0;

  // Fetch avg sales for feedback
  fetch(`${API}/reorder/${encodeURIComponent(p.product_name)}`)
    .then(r => r.json())
    .then(data => {
      currentAvgSales = data.average_daily_demand || 0;
      updateStockFeedback();
    })
    .catch(() => {
      document.getElementById('stockFeedback').textContent = '';
    });

  openModal('productModal');
}

function updateStockFeedback() {
  const stock = parseInt(document.getElementById('fStock').value) || 0;
  const el = document.getElementById('stockFeedback');
  if (currentAvgSales > 0) {
    const days = Math.floor(stock / currentAvgSales);
    if (days <= 0) {
      el.textContent = '🚨 Out of stock soon!';
      el.style.color = 'var(--rose)';
    } else {
      el.textContent = `⏱️ Estimated to last approx. ${days} days`;
      el.style.color = days <= 7 ? 'var(--amber)' : 'var(--text3)';
    }
  } else {
    el.textContent = '';
  }
}

async function saveProduct() {
  const get = id => document.getElementById(id).value.trim();
  if (!get('fProductName') || !get('fCategory') || !get('fSellingPrice') || !get('fStock')) {
    toast('Please fill all required fields', 'error'); return;
  }
  const payload = {
    product_name:       get('fProductName'),
    category:           get('fCategory'),
    current_stock:      parseInt(get('fStock')) || 0,
    selling_price:      parseFloat(get('fSellingPrice')) || 0,
    cost_price:         parseFloat(get('fCostPrice'))    || null,
    supplier_lead_time: parseInt(get('fLeadTime'))       || 5,
    unit:               document.getElementById('fUnit').value,
    description:        get('fDescription') || null,
    reorder_point:      parseInt(get('fReorderPoint')) || null,
  };
  try {
    if (editingProductId) {
      await fetch(`${API}/products/${editingProductId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      toast('Product updated successfully', 'success');
    } else {
      payload.product_id = get('fProductId');
      if (!payload.product_id) { toast('Product ID is required', 'error'); return; }
      await fetch(`${API}/products/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      toast('Product created successfully', 'success');
    }
    document.getElementById('fProductId').disabled = false;
    closeModal('productModal');
    loadProducts();
  } catch { toast('Failed to save product', 'error'); }
}

async function deleteProduct(id, name) {
  if (!confirm(`Deactivate "${name}"?`)) return;
  try {
    await fetch(`${API}/products/${id}`, { method: 'DELETE' });
    toast(`${name} deactivated`, 'success');
    loadProducts();
  } catch { toast('Failed to delete product', 'error'); }
}

/* ════════════════════════════════════════════
   BILLING DESK
════════════════════════════════════════════ */
async function loadBillingProducts() {
  try {
    const data = await fetch(`${API}/products/`).then(r => r.json());
    billingProducts = data.products || [];
    renderBillingGrid(billingProducts);
  } catch { toast('Failed to load products', 'error'); }
}

function filterBillingProducts() {
  const q = document.getElementById('billingSearch').value.toLowerCase();
  renderBillingGrid(billingProducts.filter(p => p.product_name.toLowerCase().includes(q)));
}

function renderBillingGrid(products) {
  const grid = document.getElementById('billingProductGrid');
  if (!products.length) { grid.innerHTML = '<div class="empty-state"><p>No products found</p></div>'; return; }
  grid.innerHTML = products.map(p => `
    <div class="product-tile" onclick="addToCart('${p.product_id}')">
      <div class="product-tile-name">${p.product_name}</div>
      <div class="product-tile-info">${p.category} · Stock: ${p.current_stock}</div>
      <div class="product-tile-price">${fmtCur(p.selling_price)}</div>
    </div>`).join('');
}

function addToCart(productId) {
  const p = billingProducts.find(x => x.product_id === productId);
  if (!p) return;
  if (p.current_stock <= 0) { toast(`${p.product_name} is out of stock`, 'error'); return; }
  const existing = cart.find(c => c.product_id === productId);
  if (existing) {
    if (existing.qty >= p.current_stock) { toast('Not enough stock', 'error'); return; }
    existing.qty++;
  } else {
    cart.push({ product_id: productId, name: p.product_name, price: p.selling_price, qty: 1, stock: p.current_stock });
  }
  renderCart();
}

function updateQty(productId, delta) {
  const item = cart.find(c => c.product_id === productId);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) cart = cart.filter(c => c.product_id !== productId);
  renderCart();
}

function renderCart() {
  const body = document.getElementById('cartBody');
  document.getElementById('cartCount').textContent = `${cart.length} item${cart.length !== 1 ? 's' : ''}`;
  if (!cart.length) {
    body.innerHTML = '<div class="cart-empty"><div class="icon">🛒</div><p>Add products to start a bill</p></div>';
    updateCartSummary(); return;
  }
  body.innerHTML = cart.map(item => `
    <div class="cart-item">
      <div class="cart-item-info">
        <div class="cart-item-name">${item.name}</div>
        <div class="cart-item-price">${fmtCur(item.price)} × ${item.qty} = ${fmtCur(item.price * item.qty)}</div>
      </div>
      <div class="qty-control">
        <button class="qty-btn" onclick="updateQty('${item.product_id}',-1)">−</button>
        <span class="qty-val">${item.qty}</span>
        <button class="qty-btn" onclick="updateQty('${item.product_id}',1)">+</button>
      </div>
    </div>`).join('');
  updateCartSummary();
}

function updateCartSummary() {
  const subtotal = cart.reduce((s, i) => s + i.price * i.qty, 0);
  const discPct  = parseFloat(document.getElementById('discountPct').value) || 0;
  const gstPct   = parseFloat(document.getElementById('gstRate').value)    || 0;
  const discAmt  = subtotal * discPct / 100;
  const taxable  = subtotal - discAmt;
  const gstAmt   = taxable * gstPct / 100;
  const total    = taxable + gstAmt;
  document.getElementById('summarySubtotal').textContent = fmtCur(subtotal);
  document.getElementById('summaryDiscount').textContent = `-${fmtCur(discAmt)}`;
  document.getElementById('summaryGst').textContent      = fmtCur(gstAmt);
  document.getElementById('summaryTotal').textContent    = fmtCur(total);
}

/* ── PAYMENT METHOD TOGGLE ──────────────────── */
function selectPayment(method) {
  document.getElementById('paymentMethod').value = method;
  document.querySelectorAll('.pay-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.value === method);
  });
}

function clearCart() { cart = []; renderCart(); }

async function submitBill() {
  if (!cart.length) { toast('Cart is empty', 'error'); return; }
  const payload = {
    customer_name:  document.getElementById('customerName').value  || null,
    customer_phone: document.getElementById('customerPhone').value || null,
    items:          cart.map(i => ({ product_id: i.product_id, quantity: i.qty })),
    discount:       parseFloat(document.getElementById('discountPct').value) || 0,
    gst_rate:       parseFloat(document.getElementById('gstRate').value)    || 18,
    payment_method: document.getElementById('paymentMethod').value,
  };
  const btn = document.querySelector('.generate-bill-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span style="font-size:18px">⏳</span> Generating…'; }
  try {
    const res = await fetch(`${API}/billing/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
    const bill = await res.json();
    toast(`Bill ${bill.bill_number} generated — Total: ${fmtCur(bill.total)}`, 'success');

    // Auto-download the PDF
    try {
      if (bill.id) {
        await downloadBillPDF(bill.id, bill.bill_number);
      }
    } catch (pdfErr) {
      console.warn('Auto PDF download failed:', pdfErr);
    }

    clearCart();
    document.getElementById('customerName').value  = '';
    document.getElementById('customerPhone').value = '';
    loadBillingProducts();
  } catch (e) { toast(e.message || 'Failed to create bill', 'error'); }
  finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<span style="font-size:18px">🧾</span> Generate Bill & Download PDF'; }
  }
}

/* ════════════════════════════════════════════
   BILL HISTORY
════════════════════════════════════════════ */
async function loadBills() {
  try {
    const [bills, stats] = await Promise.all([
      fetch(`${API}/billing/`).then(r => r.json()),
      fetch(`${API}/billing/stats`).then(r => r.json()),
    ]);
    document.getElementById('bHistToday').textContent = fmtCur(stats.today_revenue);
    document.getElementById('bHistTotal').textContent = fmtCur(stats.total_revenue);
    const tbody = document.getElementById('billTableBody');
    if (!bills.bills.length) {
      tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="icon">🧾</div><p>No bills yet</p></div></td></tr>`;
      return;
    }
    tbody.innerHTML = bills.bills.map(b => `<tr>
      <td class="mono" style="font-size:12px">${b.bill_number}</td>
      <td>${b.customer_name || '<span style="color:var(--text3)">—</span>'}</td>
      <td>${b.items_count}</td>
      <td style="font-weight:600">${fmtCur(b.total)}</td>
      <td><span class="tag tag-blue">${b.payment_method}</span></td>
      <td><span class="tag tag-ok">${b.status}</span></td>
      <td style="font-size:12px;color:var(--text3)">${fmtDate(b.created_at)}</td>
      <td>
        <div style="display:flex;gap:5px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" onclick="viewBill(${b.id})">View</button>
          <button class="btn btn-ghost btn-sm" onclick="downloadBillPDF(${b.id},'${b.bill_number}')">⬇ PDF</button>
        </div>
      </td>
    </tr>`).join('');
  } catch { toast('Failed to load bills', 'error'); }
}

/* ════════════════════════════════════════════
   VIEW BILL MODAL
════════════════════════════════════════════ */
async function viewBill(id) {
  try {
    const b = await fetch(`${API}/billing/${id}`).then(r => r.json());
    currentBillId     = b.id;
    currentBillNumber = b.bill_number;

    document.getElementById('billModalContent').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        <div><div style="font-size:11px;color:var(--text3)">Bill Number</div><div class="mono" style="font-weight:600">${b.bill_number}</div></div>
        <div><div style="font-size:11px;color:var(--text3)">Date</div><div>${fmtDate(b.created_at)}</div></div>
        <div><div style="font-size:11px;color:var(--text3)">Customer</div><div>${b.customer_name || '—'}</div></div>
        <div><div style="font-size:11px;color:var(--text3)">Payment</div><div><span class="tag tag-blue">${b.payment_method}</span></div></div>
      </div>
      <div class="table-responsive">
        <table style="margin-bottom:16px">
          <thead><tr><th>Product</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead>
          <tbody>${b.items.map(i => `<tr>
            <td>${i.product_name}</td>
            <td>${i.quantity}</td>
            <td>${fmtCur(i.unit_price)}</td>
            <td>${fmtCur(i.line_total)}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="bill-preview">
        <div class="summary-row"><span>Subtotal</span><span>${fmtCur(b.subtotal)}</span></div>
        <div class="summary-row"><span>Discount</span><span>-${fmtCur(b.discount)}</span></div>
        <div class="summary-row"><span>GST (${b.gst_rate}%)</span><span>${fmtCur(b.gst_amount)}</span></div>
        <div class="summary-row total"><span>TOTAL</span><span>${fmtCur(b.total)}</span></div>
      </div>`;

    document.getElementById('modalDownloadBtn').style.display = 'inline-flex';
    openModal('billModal');
  } catch { toast('Failed to load bill', 'error'); }
}

function downloadBillFromModal() {
  if (currentBillId && currentBillNumber) downloadBillPDF(currentBillId, currentBillNumber);
}

/* ════════════════════════════════════════════
   PDF BILL GENERATION  (jsPDF)
════════════════════════════════════════════ */
async function downloadBillPDF(billId, billNumber) {
  try {
    const b = await fetch(`${API}/billing/${billId}`).then(r => r.json());
    generatePDF(b);
    toast('PDF downloaded!', 'success');
  } catch (e) {
    console.error('PDF error:', e);
    toast('Failed to generate PDF', 'error');
  }
}

function generatePDF(b) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const W = doc.internal.pageSize.getWidth();   // 210mm
  const H = doc.internal.pageSize.getHeight();   // 297mm
  const M = 18;       // margin
  const CW = W - M*2; // content width
  let y = 0;

  // ═══════════════════════════════════════════
  // HEADER BAND
  // ═══════════════════════════════════════════
  doc.setFillColor(20, 24, 45);
  doc.rect(0, 0, W, 36, 'F');
  // Accent stripe
  doc.setFillColor(6, 214, 160);
  doc.rect(0, 36, W, 1.5, 'F');

  // Brand name
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(20);
  doc.setTextColor(255, 255, 255);
  doc.text('Warehouse Automation', M, 16);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(160, 170, 200);
  doc.text('Retail Intelligence Platform', M, 23);

  // Invoice label (right)
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(6, 214, 160);
  doc.text('TAX INVOICE', W - M, 14, { align: 'right' });
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(200, 210, 240);
  doc.text(b.bill_number, W - M, 22, { align: 'right' });
  doc.setFontSize(8);
  doc.text(new Date(b.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' }), W - M, 29, { align: 'right' });

  y = 46;

  // ═══════════════════════════════════════════
  // BILL TO / BILL DETAILS (two-column info box)
  // ═══════════════════════════════════════════
  const boxH = 28;
  doc.setFillColor(245, 247, 255);
  doc.roundedRect(M, y, CW, boxH, 3, 3, 'F');
  doc.setDrawColor(220, 225, 245);
  doc.setLineWidth(0.3);
  doc.roundedRect(M, y, CW, boxH, 3, 3, 'S');

  // Vertical divider
  const midX = W / 2;
  doc.setDrawColor(210, 215, 240);
  doc.line(midX, y + 4, midX, y + boxH - 4);

  // Left: Bill To
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.setTextColor(100, 110, 180);
  doc.text('BILL TO', M + 6, y + 8);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(30, 35, 60);
  doc.text(b.customer_name || 'Walk-in Customer', M + 6, y + 15);
  if (b.customer_phone) {
    doc.setFontSize(8);
    doc.setTextColor(90, 95, 130);
    doc.text('Ph: ' + b.customer_phone, M + 6, y + 21);
  }

  // Right: Details
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.setTextColor(100, 110, 180);
  doc.text('PAYMENT DETAILS', midX + 6, y + 8);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(30, 35, 60);

  const payIcons = { cash: 'Cash', card: 'Card', upi: 'UPI', credit: 'Credit' };
  doc.text('Method:  ' + (payIcons[b.payment_method] || b.payment_method).toUpperCase(), midX + 6, y + 15);
  doc.text('Status:   ' + (b.status || 'Paid').toUpperCase(), midX + 6, y + 21);

  y += boxH + 10;

  // ═══════════════════════════════════════════
  // ITEMS TABLE
  // ═══════════════════════════════════════════
  const colX = {
    num:   M + 3,
    item:  M + 12,
    qty:   M + CW * 0.58,   // 58% of content width
    price: M + CW * 0.78,   // 78% of content width
    total: M + CW - 4       // End of content width minus padding
  };
  const thH = 10;

  // Table header
  doc.setFillColor(20, 24, 45);
  doc.roundedRect(M, y, CW, thH, 2, 2, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8);
  doc.setTextColor(255, 255, 255);
  doc.text('#',     colX.num,   y + 6.5);
  doc.text('ITEM',  colX.item,  y + 6.5);
  doc.text('QTY',   colX.qty,   y + 6.5, { align: 'center' });
  doc.text('PRICE', colX.price, y + 6.5, { align: 'right' });
  doc.text('TOTAL', colX.total, y + 6.5, { align: 'right' });
  y += thH + 2;

  // Table rows
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8.5);
  const rowH = 8.5;

  b.items.forEach((item, idx) => {
    // Zebra stripe
    if (idx % 2 === 0) {
      doc.setFillColor(248, 250, 255);
      doc.rect(M, y - 2, CW, rowH, 'F');
    }
    doc.setTextColor(50, 55, 80);
    doc.setFont('helvetica', 'normal');
    doc.text(String(idx + 1), colX.num, y + 4);

    const maxNameLen = 42;
    const name = item.product_name.length > maxNameLen
      ? item.product_name.slice(0, maxNameLen - 1) + '...'
      : item.product_name;
    doc.text(name, colX.item, y + 4);

    doc.setFont('helvetica', 'bold');
    doc.text(String(item.quantity), colX.qty, y + 4, { align: 'center' });

    doc.setFont('helvetica', 'normal');
    doc.text(fmtCur(item.unit_price), colX.price, y + 4, { align: 'right' });

    doc.setFont('helvetica', 'bold');
    doc.text(fmtCur(item.line_total), colX.total, y + 4, { align: 'right' });
    y += rowH;
  });

  // Bottom border of table
  doc.setDrawColor(210, 215, 240);
  doc.setLineWidth(0.4);
  doc.line(M, y + 1, M + CW, y + 1);
  y += 10;

  // ═══════════════════════════════════════════
  // SUMMARY (right-aligned block)
  // ═══════════════════════════════════════════
  const sumLabelX = M + CW * 0.60;
  const sumValX   = M + CW - 4;

  function drawSummaryRow(label, value, isBold) {
    doc.setFont('helvetica', isBold ? 'bold' : 'normal');
    doc.setFontSize(isBold ? 10.5 : 9.5);
    doc.setTextColor(isBold ? 20 : 80, isBold ? 24 : 85, isBold ? 45 : 120);
    doc.text(label, sumLabelX, y);
    doc.setTextColor(30, 35, 60);
    doc.text(value, sumValX, y, { align: 'right' });
    y += isBold ? 9 : 7;
  }

  drawSummaryRow('Subtotal', fmtCur(b.subtotal), false);
  const discPct = b.subtotal > 0 ? ((b.discount / b.subtotal) * 100).toFixed(0) : '0';
  drawSummaryRow('Discount (' + discPct + '%)', '-' + fmtCur(b.discount), false);
  drawSummaryRow('GST (' + b.gst_rate + '%)', fmtCur(b.gst_amount), false);

  y += 3;

  // TOTAL highlight bar
  const totalBarW = CW * 0.42;
  const totalBarX = M + CW - totalBarW;
  doc.setFillColor(20, 24, 45);
  doc.roundedRect(totalBarX, y - 3, totalBarW, 13, 3, 3, 'F');
  
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11.5);
  doc.setTextColor(255, 255, 255);
  doc.text('TOTAL', totalBarX + 6, y + 6);
  doc.setTextColor(6, 214, 160);
  doc.text(fmtCur(b.total), sumValX, y + 6, { align: 'right' });
  y += 22;

  // ═══════════════════════════════════════════
  // PAID BADGE
  // ═══════════════════════════════════════════
  doc.setFillColor(6, 214, 160);
  doc.roundedRect(M, y - 3, 30, 8, 2, 2, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.setTextColor(255, 255, 255);
  doc.text((b.status || 'PAID').toUpperCase(), M + 15, y + 2.5, { align: 'center' });

  // ═══════════════════════════════════════════
  // FOOTER
  // ═══════════════════════════════════════════
  const footY = H - 18;
  doc.setDrawColor(220, 225, 245);
  doc.setLineWidth(0.3);
  doc.line(M, footY, M + CW, footY);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(140, 150, 190);
  doc.text('Thank you for your business!', W / 2, footY + 6, { align: 'center' });
  doc.setFontSize(7);
  doc.text('Generated by Warehouse Automation  |  Retail Intelligence Platform', W / 2, footY + 11, { align: 'center' });

  doc.save((b.bill_number || 'Bill') + '.pdf');
}

/* ════════════════════════════════════════════
   FORECAST
════════════════════════════════════════════ */
async function loadForecastProducts() {
  try {
    const data = await fetch(`${API}/forecast/products`).then(r => r.json());
    const sel  = document.getElementById('forecastProduct');
    sel.innerHTML = '<option value="">— Select Product —</option>' +
      (data.products || []).map(p => `<option value="${p.product_name}">${p.product_name}</option>`).join('');
  } catch { toast('Failed to load products', 'error'); }
}

async function runForecast() {
  const product = document.getElementById('forecastProduct').value;
  const days    = document.getElementById('forecastDays').value;
  if (!product) { toast('Select a product', 'error'); return; }

  document.getElementById('forecastResults').style.display = 'none';
  document.getElementById('forecastEmpty').style.display   = 'none';
  document.getElementById('forecastLoading').style.display = 'block';
  startForecastLoadingAnimation();

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    const res = await fetch(`${API}/forecast/${encodeURIComponent(product)}?days=${days}`, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) { let e = `Server error (${res.status})`; try { e = (await res.json()).detail; } catch {} throw new Error(e); }
    const data = await res.json();

    document.getElementById('forecastLoading').style.display = 'none';
    stopForecastLoadingAnimation();
    document.getElementById('forecastResults').style.display = 'block';

    const preds = data.predictions || [];
    const m     = data.model_metrics || {};
    const allM  = data.all_metrics   || {};

    document.getElementById('forecastModelBadge').textContent = data.model_used || '—';

    let metricsHTML = `
      <div class="metric-card"><div class="metric-label">MAE</div>
        <div class="metric-value" style="color:var(--accent)">${(m.mae||0).toFixed(2)}</div>
        <div class="metric-sub">Mean Absolute Error</div></div>
      <div class="metric-card"><div class="metric-label">RMSE</div>
        <div class="metric-value" style="color:var(--teal)">${(m.rmse||0).toFixed(2)}</div>
        <div class="metric-sub">Root Mean Sq Error</div></div>
      <div class="metric-card"><div class="metric-label">MAPE</div>
        <div class="metric-value" style="color:var(--amber)">${(m.mape||0).toFixed(2)}%</div>
        <div class="metric-sub">Mean Abs % Error</div></div>`;
    if (data.data_points) metricsHTML += `<div class="metric-card"><div class="metric-label">Training Data</div>
      <div class="metric-value" style="color:var(--sky)">${data.data_points}</div>
      <div class="metric-sub">days of history</div></div>`;
    document.getElementById('forecastMetrics').innerHTML = metricsHTML;

    if (forecastChart) { try { forecastChart.destroy(); } catch (_) {} forecastChart = null; }
    forecastChart = new Chart(document.getElementById('forecastChart'), {
      type: 'line',
      data: {
        labels: preds.map(p => p.ds),
        datasets: [
          { label: 'Predicted Demand', data: preds.map(p => p.yhat), borderColor: '#4f6ef7', backgroundColor: 'rgba(79,110,247,.12)', fill: false, tension: .4, pointRadius: 2 },
          { label: 'Upper Bound',      data: preds.map(p => p.yhat_upper), borderColor: 'rgba(6,214,160,.5)', borderDash: [5,4], pointRadius: 0, fill: '+1', backgroundColor: 'rgba(6,214,160,.06)' },
          { label: 'Lower Bound',      data: preds.map(p => p.yhat_lower), borderColor: 'rgba(244,63,94,.4)',  borderDash: [5,4], pointRadius: 0, fill: false },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#a0a3c4', font: { size: 11 } } },
          tooltip: { backgroundColor: 'rgba(22,24,41,.95)', titleColor: '#e8eaf8', bodyColor: '#a0a3c4', borderColor: '#252742', borderWidth: 1 },
        },
        scales: {
          x: { ticks: { color: '#5e6189', maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,.04)' } },
          y: { ticks: { color: '#5e6189' }, grid: { color: 'rgba(255,255,255,.04)' }, beginAtZero: true },
        },
      },
    });

    document.getElementById('forecastTableBody').innerHTML = preds.map(p => `
      <tr>
        <td class="mono" style="font-size:12px">${p.ds}</td>
        <td style="font-weight:600">${Math.max(0, Math.round(p.yhat))}</td>
        <td style="color:var(--text3)">${Math.max(0, Math.round(p.yhat_lower))}</td>
        <td style="color:var(--text3)">${Math.max(0, Math.round(p.yhat_upper))}</td>
      </tr>`).join('');

    // Model comparison
    const existingCompare = document.getElementById('forecastModelCompare');
    if (existingCompare) existingCompare.remove();
    if (Object.keys(allM).length > 1) {
      const div = document.createElement('div');
      div.id = 'forecastModelCompare'; div.className = 'table-card'; div.style.marginTop = '16px';
      div.innerHTML = `
        <div class="table-header"><h3>📊 All Model Performance</h3></div>
        <div class="table-responsive"><table>
          <thead><tr><th>Model</th><th>MAE ↓</th><th>RMSE ↓</th><th>MAPE %</th><th></th></tr></thead>
          <tbody>${Object.entries(allM).map(([name, mm]) => `
            <tr style="${name===data.model_used?'background:rgba(79,110,247,.08)':''}">
              <td class="mono" style="font-size:12px">${name}</td>
              <td style="font-weight:${name===data.model_used?700:400};color:${name===data.model_used?'var(--accent)':'inherit'}">${(mm.mae||0).toFixed(2)}</td>
              <td>${(mm.rmse||0).toFixed(2)}</td>
              <td>${(mm.mape||0).toFixed(2)}%</td>
              <td>${name===data.model_used?'<span class="tag tag-ok">Best</span>':''}</td>
            </tr>`).join('')}
          </tbody>
        </table></div>`;
      document.getElementById('forecastResults').appendChild(div);
    }
  } catch (e) {
    document.getElementById('forecastLoading').style.display = 'none';
    stopForecastLoadingAnimation();
    document.getElementById('forecastEmpty').style.display = 'block';
    toast(e.name === 'AbortError' ? 'Forecast timed out. Try again.' : (e.message || 'Forecast failed'), 'error');
  }
}

/* ════════════════════════════════════════════
   REORDER (Functions moved to reorder_functions.js)
════════════════════════════════════════════ */

/* ════════════════════════════════════════════
   UPLOAD
════════════════════════════════════════════ */
function initUploadZone() {
  const uploadZone = document.getElementById('uploadZone');
  if (!uploadZone) return;
  uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone.addEventListener('drop', e => {
    e.preventDefault(); uploadZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0]; if (file) uploadCSV(file);
  });
}

function handleFileUpload() {
  const file = document.getElementById('csvFile').files[0];
  if (file) uploadCSV(file);
}

async function uploadCSV(file) {
  const status        = document.getElementById('uploadStatus');
  const statusContent = document.getElementById('uploadStatusContent');
  status.style.display = 'block';
  statusContent.innerHTML = `<div style="text-align:center;padding:20px"><div class="loading-spinner"></div><p style="margin-top:8px;color:var(--text3)">Uploading and processing…</p></div>`;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res  = await fetch(`${API}/upload/`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    statusContent.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:4px">
        <div class="metric-card"><div class="metric-label">Rows Processed</div><div class="metric-value" style="color:var(--accent)">${data.total_rows}</div></div>
        <div class="metric-card"><div class="metric-label">Products Added</div><div class="metric-value" style="color:var(--teal)">${data.products_added}</div></div>
        <div class="metric-card"><div class="metric-label">Sales Records</div><div class="metric-value" style="color:var(--amber)">${data.sales_records_added}</div></div>
      </div>
      <p style="font-size:12px;color:var(--text3);margin-top:12px;text-align:center">Date range: ${data.date_range?.start} → ${data.date_range?.end}</p>`;
    toast('CSV uploaded successfully!', 'success');
    loadUploadStatus();
  } catch (e) {
    statusContent.innerHTML = `<div style="padding:16px;color:var(--rose)">❌ ${e.message}</div>`;
    toast('Upload failed: ' + e.message, 'error');
  }
}

async function loadUploadStatus() {
  try {
    const data = await fetch(`${API}/upload/status`).then(r => r.json());
    const el = document.getElementById('uploadedFiles');
    if (!data.files.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">📂</div><p>No files uploaded yet</p></div>'; return;
    }
    el.innerHTML = `<div style="padding:8px 0">${data.files.map(f =>
      `<div style="display:flex;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid var(--border)">
        <span style="font-size:18px">📄</span><span style="font-size:13px;font-weight:500">${f}</span></div>`
    ).join('')}</div>`;
  } catch {}
}

/* ════════════════════════════════════════════
   MANUAL ENTRY
════════════════════════════════════════════ */
async function loadManualProducts() {
  try {
    const data = await fetch(`${API}/products/`).then(r => r.json());
    const sel  = document.getElementById('manualProduct');
    sel.innerHTML = '<option value="">— Select Product —</option>' +
      (data.products || []).map(p => `<option value="${p.product_id}">${p.product_name}</option>`).join('');
    document.getElementById('manualDate').value = new Date().toISOString().slice(0, 10);
  } catch {}
}

async function loadManualSales() {
  try {
    const data  = await fetch(`${API}/products/manual-sales`).then(r => r.json());
    const tbody = document.getElementById('manualSalesBody');
    if (!data.entries.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="icon">✏️</div><p>No manual entries yet</p></div></td></tr>`;
      return;
    }
    tbody.innerHTML = data.entries.map(e => `
      <tr>
        <td class="mono" style="font-size:12px">${e.date}</td>
        <td>${e.product_name}</td>
        <td style="font-weight:600">${e.units_sold}</td>
        <td>${fmtCur(e.selling_price)}</td>
        <td style="color:var(--text3)">${e.notes || '—'}</td>
      </tr>`).join('');
  } catch { toast('Failed to load manual sales', 'error'); }
}

async function submitManualSale() {
  const productId = document.getElementById('manualProduct').value;
  const date      = document.getElementById('manualDate').value;
  const units     = parseInt(document.getElementById('manualUnits').value);
  const price     = parseFloat(document.getElementById('manualPrice').value) || null;
  const notes     = document.getElementById('manualNotes').value;
  if (!productId || !date || !units) { toast('Fill in Product, Date and Units Sold', 'error'); return; }
  try {
    const res = await fetch(`${API}/products/manual-sale`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, date, units_sold: units, selling_price: price, notes }),
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
    toast('Sale recorded successfully', 'success');
    document.getElementById('manualUnits').value = '';
    document.getElementById('manualPrice').value = '';
    document.getElementById('manualNotes').value = '';
    loadManualSales();
  } catch (e) { toast(e.message || 'Failed to save entry', 'error'); }
}

/* ════════════════════════════════════════════
   ALERTS
════════════════════════════════════════════ */
async function loadAlerts() {
  try {
    // 1. Load historical notifications
    const alertsData  = await fetch(`${API}/products/alerts?unread_only=false`).then(r => r.json());
    const alertsEl    = document.getElementById('alertsList');
    if (!alertsData.alerts.length) {
      alertsEl.innerHTML = `<div class="empty-state"><div class="icon">✅</div><p style="font-size:12px">No recent notifications</p></div>`;
    } else {
      const icons  = { low_stock: '⚠️', out_of_stock: '🚨', reorder: '📦', high_demand: '📈' };
      alertsEl.innerHTML = alertsData.alerts.map(a => `
        <div class="alert-item" style="${a.is_read ? 'opacity:.5' : ''};padding:10px;font-size:12px">
          <span class="alert-icon" style="font-size:14px">${icons[a.alert_type] || '🔔'}</span>
          <div class="alert-content">
            <div class="alert-msg" style="font-weight:500">${a.message}</div>
            <div class="alert-time" style="font-size:10px">${fmtDate(a.created_at)}</div>
          </div>
          ${!a.is_read ? `<button class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px" onclick="markAlertRead(${a.id})">Read</button>` : ''}
        </div>`).join('');
    }

    // 2. Load real-time low stock products
    const lowStockData = await fetch(`${API}/products/low-stock`).then(r => r.json());
    const statsEl      = document.getElementById('lowStockStats');
    const tableBody    = document.getElementById('lowStockBody');

    // Update stats card
    const oos = lowStockData.products.filter(p => p.is_out_of_stock).length;
    statsEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div class="metric-card" style="padding:10px">
          <div class="metric-label" style="font-size:9px">Out of Stock</div>
          <div class="metric-value" style="font-size:18px;color:var(--rose)">${oos}</div>
        </div>
        <div class="metric-card" style="padding:10px">
          <div class="metric-label" style="font-size:9px">Low Stock</div>
          <div class="metric-value" style="font-size:18px;color:var(--amber)">${lowStockData.count - oos}</div>
        </div>
      </div>
      <p style="font-size:11px;color:var(--text3);margin-top:10px;text-align:center">Total critical items: ${lowStockData.count}</p>
    `;

    // Update table
    if (!lowStockData.products.length) {
      tableBody.innerHTML = '<tr><td colspan="5"><div class="empty-state">✅ All stock levels are sufficient</div></td></tr>';
    } else {
      tableBody.innerHTML = lowStockData.products.map(p => {
        const pct = Math.min(100, Math.max(0, (p.current_stock / (p.reorder_point || 1)) * 100));
        const color = p.current_stock <= 0 ? 'var(--rose)' : 'var(--amber)';
        return `
          <tr>
            <td>
              <div style="font-weight:600">${p.product_name}</div>
              <div style="font-size:10px;color:var(--text3)">ID: ${p.product_id}</div>
            </td>
            <td><span class="tag tag-blue">${p.category}</span></td>
            <td>
              <div style="display:flex;align-items:center;gap:10px;min-width:120px">
                <div style="flex:1;height:6px;background:var(--bg2);border-radius:10px;overflow:hidden">
                  <div style="height:100%;width:${pct}%;background:${color};box-shadow:0 0 8px ${color}44"></div>
                </div>
                <span class="mono" style="font-size:12px">${p.current_stock} / ${p.reorder_point}</span>
              </div>
            </td>
            <td>
              ${p.is_out_of_stock 
                ? '<span class="tag tag-out">Out of Stock</span>' 
                : '<span class="tag tag-low">Low Stock</span>'}
            </td>
            <td>
              <button class="btn btn-primary btn-sm" onclick="goTo('reorder')">📦 Reorder</button>
            </td>
          </tr>
        `;
      }).join('');
    }

  } catch (e) { 
    console.error(e);
    toast('Failed to load alerts', 'error'); 
  }
}

async function markAlertRead(id) {
  try {
    await fetch(`${API}/products/alerts/${id}/read`, { method: 'POST' });
    loadAlerts(); loadDashboard();
  } catch {}
}

/* ════════════════════════════════════════════
   REPORTS
════════════════════════════════════════════ */
function downloadReport(path) {
  toast('Preparing download…', 'info');
  const a = document.createElement('a');
  a.href = `${API}/reports/${path}`; a.download = '';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

async function loadReportProducts() {
  try {
    const data = await fetch(`${API}/forecast/products`).then(r => r.json());
    const sel  = document.getElementById('retrainProduct');
    sel.innerHTML = '<option value="">— Select Product —</option>' +
      (data.products || []).map(p => `<option value="${p.product_name}">${p.product_name}</option>`).join('');
  } catch {}
}

async function retrainModel() {
  const product = document.getElementById('retrainProduct').value;
  if (!product) { toast('Select a product to retrain', 'error'); return; }
  const btn    = document.getElementById('retrainBtn');
  const status = document.getElementById('retrainStatus');
  btn.disabled = true;
  btn.innerHTML = '<span class="loading-spinner" style="width:14px;height:14px;border-width:2px"></span> Training…';
  status.textContent = '';
  try {
    const res  = await fetch(`${API}/forecast/${encodeURIComponent(product)}?days=30`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    const allMetrics = data.all_metrics || {};
    const bestModel  = data.model_used;
    const card       = document.getElementById('modelCompareCard');
    const tbody      = document.getElementById('modelCompareBody');
    card.style.display = '';
    tbody.innerHTML = Object.entries(allMetrics).map(([name, m]) => `
      <tr style="${name === bestModel ? 'background:rgba(79,110,247,.08)' : ''}">
        <td><span class="mono" style="font-size:12px">${name}</span>
          ${name === bestModel ? '<span class="tag tag-ok" style="margin-left:8px;font-size:10px">✓ Best</span>' : ''}</td>
        <td style="font-weight:${name===bestModel?700:400}">${(m.mae||0).toFixed(2)}</td>
        <td>${(m.rmse||0).toFixed(2)}</td>
        <td>${(m.mape||0).toFixed(2)}%</td>
        <td>${name===bestModel?'<span class="tag tag-ok">Selected</span>':'<span class="tag" style="background:rgba(255,255,255,.05);color:var(--text3)">Available</span>'}</td>
      </tr>`).join('') || '<tr><td colspan="5" style="color:var(--text3)">No model data</td></tr>';
    status.innerHTML = `<span style="color:var(--teal)">✓ Retrained with ${data.data_points || '?'} data points</span>`;
    toast(`Model retrained — best: ${bestModel}`, 'success');
  } catch (e) {
    status.innerHTML = `<span style="color:var(--rose)">❌ ${e.message}</span>`;
    toast('Retrain failed: ' + e.message, 'error');
  }
  btn.disabled = false;
  btn.innerHTML = '🔁 Retrain Model';
}

/* ════════════════════════════════════════════
   ALERT BADGE POLLING
════════════════════════════════════════════ */
function refreshAlertBadge() {
  fetch(`${API}/products/alerts`)
    .then(r => r.json())
    .then(d => {
      const badge = document.getElementById('alertBadge');
      if (d.count > 0) { badge.textContent = d.count; badge.style.display = ''; }
      else badge.style.display = 'none';
    }).catch(() => {});
}

/* ════════════════════════════════════════════
   INIT
════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  // Sidebar toggle — mobile
  const menuBtn        = document.getElementById('menuBtn');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  if (menuBtn)        menuBtn.addEventListener('click', openSidebar);
  if (sidebarOverlay) sidebarOverlay.addEventListener('click', closeSidebar);

  // Modal close on overlay click
  document.addEventListener('click', e => {
    if (e.target.classList.contains('modal-overlay')) {
      e.target.classList.remove('open');
      editingProductId = null;
      if (e.target.id === 'billModal') { currentBillId = null; currentBillNumber = null; }
    }
  });

  // Clock
  updateClock(); setInterval(updateClock, 1000);

  // API health
  checkAPI(); setInterval(checkAPI, 30000);

  // Upload zone drag-drop
  initUploadZone();

  // Initial page
  const savedPage = localStorage.getItem('active_page') || 'dashboard';
  goTo(savedPage);

  // Alert badge polling
  refreshAlertBadge(); setInterval(refreshAlertBadge, 60000);
});

/* ════════════════════════════════════════════
   SETTINGS PAGE
════════════════════════════════════════════ */
function loadSettings() {
  fetch(`${API}/auth/me`)
    .then(r => {
      if (!r.ok) throw new Error();
      return r.json();
    })
    .then(user => {
      const pic = localStorage.getItem('user_pic_' + user.id);

      document.getElementById('settingsUserName').textContent = user.full_name;
      document.getElementById('settingsUserRole').textContent = user.store_name || 'Administrator';
      document.getElementById('setFullName').value = user.full_name;
      document.getElementById('setEmail').value = user.email;
      document.getElementById('setEmail').disabled = true; 
      document.getElementById('setPhone').value = user.phone || '';

      if (pic) {
        document.getElementById('userProfilePic').src = pic;
      } else {
        document.getElementById('userProfilePic').src = `https://ui-avatars.com/api/?name=${encodeURIComponent(user.full_name)}&background=4f6ef7&color=fff&size=120`;
      }
      
      document.getElementById('page-settings').dataset.userId = user.id;
    })
    .catch(() => {
      toast('Failed to load profile details', 'error');
    });
}

async function saveProfileInfo() {
  const name = document.getElementById('setFullName').value.trim();
  const phone = document.getElementById('setPhone').value.trim();

  if (!name) {
    toast('Name cannot be empty', 'error');
    return;
  }

  try {
    const res = await fetch(`${API}/auth/profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: name, phone: phone })
    });
    
    if (!res.ok) throw new Error();
    
    document.getElementById('settingsUserName').textContent = name;
    toast('Profile updated successfully', 'success');
  } catch (e) {
    toast('Failed to update profile on server', 'error');
  }
}

function handleProfilePicChange(event) {
  const file = event.target.files[0];
  const userId = document.getElementById('page-settings').dataset.userId;
  if (!file || !userId) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    const dataUrl = e.target.result;
    document.getElementById('userProfilePic').src = dataUrl;
    localStorage.setItem('user_pic_' + userId, dataUrl);
    toast('Profile picture updated', 'success');
  };
  reader.readAsDataURL(file);
}

async function changePassword() {
  const oldPass = document.getElementById('setOldPassword').value;
  const newPass = document.getElementById('setNewPassword').value;
  const confirmPass = document.getElementById('setConfirmPassword').value;

  if (!oldPass || !newPass || !confirmPass) {
    toast('Please fill all password fields', 'error');
    return;
  }

  if (newPass !== confirmPass) {
    toast('New passwords do not match', 'error');
    return;
  }

  if (newPass.length < 6) {
    toast('Password must be at least 6 characters', 'error');
    return;
  }

  try {
    const res = await fetch(`${API}/auth/change-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password: oldPass, new_password: newPass })
    });
    
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to change password');
    }
    
    toast('Password updated successfully', 'success');
    document.getElementById('setOldPassword').value = '';
    document.getElementById('setNewPassword').value = '';
    document.getElementById('setConfirmPassword').value = '';
  } catch (e) {
    toast(e.message, 'error');
  }
}

function toggleTheme() {
  const isDark = document.getElementById('setThemeToggle').checked;
  if (isDark) {
    document.documentElement.style.setProperty('--bg', '#07080f');
    document.documentElement.style.setProperty('--bg1', '#0c0e1a');
    document.documentElement.style.setProperty('--bg2', '#111323');
    document.documentElement.style.setProperty('--surface', '#161829');
    document.documentElement.style.setProperty('--border', '#252742');
    document.documentElement.style.setProperty('--text', '#e8eaf8');
    document.documentElement.style.setProperty('--text2', '#a0a3c4');
    toast('Dark mode enabled', 'info');
  } else {
    document.documentElement.style.setProperty('--bg', '#f3f4f6');
    document.documentElement.style.setProperty('--bg1', '#ffffff');
    document.documentElement.style.setProperty('--bg2', '#f9fafb');
    document.documentElement.style.setProperty('--surface', '#ffffff');
    document.documentElement.style.setProperty('--border', '#e5e7eb');
    document.documentElement.style.setProperty('--text', '#111827');
    document.documentElement.style.setProperty('--text2', '#4b5563');
    toast('Light mode enabled', 'info');
  }
}

/* ════════════════════════════════════════════
   INTERACTIVE ENHANCEMENTS
════════════════════════════════════════════ */

/* ── Welcome Banner — Time-based greeting ── */
function updateWelcomeBanner() {
  const hour = new Date().getHours();
  const greetEl = document.getElementById('welcomeGreeting');
  const emojiEl = document.getElementById('welcomeEmoji');
  const subEl   = document.getElementById('welcomeSubtext');
  if (!greetEl) return;

  let greeting, emoji, subtext;
  if (hour < 5) {
    greeting = 'Burning the midnight oil!'; emoji = '🌙';
    subtext = 'Late night stock check? Everything looks good.';
  } else if (hour < 12) {
    greeting = 'Good Morning!'; emoji = '☀️';
    subtext = 'Fresh start! Let\'s check your inventory and get ready for the day.';
  } else if (hour < 17) {
    greeting = 'Good Afternoon!'; emoji = '🌤️';
    subtext = 'Peak hours! Keep an eye on fast-moving items and stock levels.';
  } else if (hour < 21) {
    greeting = 'Good Evening!'; emoji = '🌅';
    subtext = 'End-of-day wrap up — review today\'s sales and plan for tomorrow.';
  } else {
    greeting = 'Working Late!'; emoji = '🌃';
    subtext = 'Great effort! Here\'s a quick glance before you call it a day.';
  }

  greetEl.textContent = greeting;
  emojiEl.textContent = emoji;
  subEl.textContent = subtext;

  // Rotate business tips
  rotateTip();
}

/* ── Rotating Business Tips ─────────────── */
const businessTips = [
  'Use the Billing Desk to quickly generate bills and track real-time sales.',
  'Set reorder points for your products so you never run out of bestsellers.',
  'Upload your CSV sales data to unlock AI-powered demand forecasting.',
  'Check the Alerts page regularly — low stock items need your attention!',
  'Download Excel reports to share with your accountant or supplier.',
  'Use the Manual Entry page to log walk-in sales that bypass billing.',
  'Review the 7-Day Sales Trend chart to spot your peak selling days.',
  'Keep your product catalog updated — accurate prices mean accurate bills.',
  'Enable notifications to get instant alerts when stock runs low.',
  'Use the Reorder Plan to calculate the perfect quantity to order.',
  'Track your daily revenue on the dashboard to measure business growth.',
  'Use category filters to quickly find products in large inventories.',
  'The AI Forecast can predict demand — plan your purchases in advance!',
  'Compare payment methods (Cash/Card/UPI) to understand customer preferences.',
  'Print PDF bills for your customers — it builds trust and professionalism.',
];
let _currentTipIdx = Math.floor(Math.random() * businessTips.length);

function rotateTip() {
  const tipEl = document.getElementById('tipText');
  if (!tipEl) return;
  _currentTipIdx = (_currentTipIdx + 1) % businessTips.length;
  tipEl.style.opacity = '0';
  tipEl.style.transition = 'opacity .3s';
  setTimeout(() => {
    tipEl.textContent = businessTips[_currentTipIdx];
    tipEl.style.opacity = '1';
  }, 300);
}

/* ── FAB Toggle ─────────────────────────── */
function toggleFab() {
  const btn = document.getElementById('fabMainBtn');
  const actions = document.getElementById('fabActions');
  btn.classList.toggle('open');
  actions.classList.toggle('open');
}

// Close FAB when clicking outside
document.addEventListener('click', e => {
  const fab = document.getElementById('quickFab');
  if (fab && !fab.contains(e.target)) {
    document.getElementById('fabMainBtn')?.classList.remove('open');
    document.getElementById('fabActions')?.classList.remove('open');
  }
});

/* ── Confetti Celebration ───────────────── */
function launchConfetti() {
  const container = document.getElementById('confettiContainer');
  if (!container) return;
  const colors = ['#4f6ef7', '#06d6a0', '#f59e0b', '#f43f5e', '#38bdf8', '#7c3aed', '#ff6b6b', '#ffd93d'];
  const shapes = ['circle', 'square', 'triangle'];

  for (let i = 0; i < 60; i++) {
    const piece = document.createElement('div');
    piece.className = 'confetti-piece';
    const color = colors[Math.floor(Math.random() * colors.length)];
    const shape = shapes[Math.floor(Math.random() * shapes.length)];
    const left = Math.random() * 100;
    const delay = Math.random() * 0.8;
    const size = 6 + Math.random() * 10;
    const duration = 2 + Math.random() * 2;

    piece.style.left = left + '%';
    piece.style.width = size + 'px';
    piece.style.height = size + 'px';
    piece.style.animationDelay = delay + 's';
    piece.style.animationDuration = duration + 's';
    piece.style.background = color;

    if (shape === 'circle') piece.style.borderRadius = '50%';
    else if (shape === 'triangle') {
      piece.style.width = '0';
      piece.style.height = '0';
      piece.style.borderLeft = size/2 + 'px solid transparent';
      piece.style.borderRight = size/2 + 'px solid transparent';
      piece.style.borderBottom = size + 'px solid ' + color;
      piece.style.background = 'none';
    } else {
      piece.style.borderRadius = '2px';
    }

    container.appendChild(piece);
  }

  // Cleanup after animation
  setTimeout(() => { container.innerHTML = ''; }, 4000);
}

/* ── Animated Number Counter ────────────── */
function animateCounter(element, targetValue, duration = 800) {
  if (!element || isNaN(targetValue)) return;
  const startValue = 0;
  const startTime = performance.now();

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(startValue + (targetValue - startValue) * eased);

    if (element.dataset.format === 'currency') {
      element.textContent = '₹' + current.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else {
      element.textContent = current.toLocaleString('en-IN');
    }

    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

/* ── Enhanced Billing Grid with Stock Colors ── */
const _origRenderBillingGrid = renderBillingGrid;
renderBillingGrid = function(products) {
  _origRenderBillingGrid(products);
  // Add stock-level classes after render
  const grid = document.getElementById('billingProductGrid');
  if (!grid) return;
  const tiles = grid.querySelectorAll('.product-tile');
  products.forEach((p, i) => {
    if (tiles[i]) {
      if (p.current_stock <= 0) {
        tiles[i].classList.add('out-of-stock');
      } else if (p.reorder_point && p.current_stock <= p.reorder_point) {
        tiles[i].classList.add('low-stock');
      }
      // Add stagger animation
      tiles[i].style.animationDelay = (i * 0.03) + 's';
      tiles[i].style.animation = 'metricPop .3s cubic-bezier(.34,1.56,.64,1) both';
    }
  });
};

/* ── Enhanced submitBill with Confetti ──── */
const _origSubmitBill = submitBill;
submitBill = async function() {
  const hadItems = cart.length > 0;
  await _origSubmitBill();
  // If cart was cleared (bill succeeded), celebrate!
  if (hadItems && cart.length === 0) {
    launchConfetti();
  }
};

/* ── Initialize Interactive Features ────── */
const _origDOMContentLoaded = () => {
  // Welcome banner
  updateWelcomeBanner();
  // Rotate tips every 20 seconds
  setInterval(rotateTip, 20000);
};

// Hook into DOMContentLoaded if already loaded, otherwise wait
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _origDOMContentLoaded);
} else {
  _origDOMContentLoaded();
}
