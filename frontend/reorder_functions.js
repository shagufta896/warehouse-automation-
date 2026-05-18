// ════════════════════════════════════════════════════════
//  REORDER — backup-days-aware smart reorder plan
// ════════════════════════════════════════════════════════

/** Returns the current global backup days as an integer */
function getGlobalBackupDays() {
  return parseInt(document.getElementById('globalBackupDays')?.value || '5', 10);
}

/** Inventory size label + pill colour based on backup days */
function inventorySizeLabel(days) {
  if (days <= 3)  return { label: '⚡ Tiny Inventory',   color: '#22d3ee', bg: 'rgba(34, 211, 238, 0.12)',  border: 'rgba(34, 211, 238, 0.3)' };
  if (days <= 5)  return { label: '📦 Small Inventory',  color: '#22d3ee', bg: 'rgba(34, 211, 238, 0.12)',  border: 'rgba(34, 211, 238, 0.3)' };
  if (days <= 7)  return { label: '📊 Medium Inventory', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.3)' };
  if (days <= 14) return { label: '🏢 Large Inventory',  color: '#a78bfa', bg: 'rgba(167, 139, 250, 0.12)', border: 'rgba(167, 139, 250, 0.3)' };
  return           { label: '🏗️ Bulk Warehouse',     color: '#f97316', bg: 'rgba(249, 115, 22, 0.12)', border: 'rgba(249, 115, 22, 0.3)' };
}

/** Called whenever the global backup-days selector changes */
function onBackupDaysChange() {
  const days = getGlobalBackupDays();
  const { label, color, bg, border } = inventorySizeLabel(days);

  // Update pill
  const pill = document.getElementById('inventorySizePill');
  if (pill) {
    pill.textContent = label;
    pill.style.color = color;
    pill.style.background = bg;
    pill.style.borderColor = border;
    pill.style.boxShadow = `0 0 12px ${bg}`;
  }

  // Update description banner
  const banner = document.getElementById('backupDaysBanner');
  if (banner) {
    const adjective = days <= 3 ? 'very lean' : days <= 5 ? 'lean'
                    : days <= 7 ? 'balanced'   : days <= 14 ? 'spacious' : 'warehouse-scale';
    banner.innerHTML = `
      <strong style="color:var(--accent)">${days}-day backup</strong> —
      Reorder points and storage caps are calculated for <strong>${days} days</strong> of demand.
      This is a <em>${adjective}</em> inventory setting.
      ${days <= 3 ? '⚡ Great for perishables or tiny shops — order frequently in small batches.'
        : days <= 7 ? '✅ Balanced: safe buffer without tying up too much cash.'
        : '📦 Bulk mode: fewer orders, more storage needed. Ideal for non-perishables.'}
    `;
  }

  // Reload the plan with new backup_days
  loadReorderPlan();
}

async function loadReorderProducts() {
  try {
    const data = await fetch(`${API}/products/`).then(r => r.json());
    const list = document.getElementById('reorderProductList');
    const products = data.products || [];
    list.innerHTML = products.map(p => `<option value="${p.product_name}">`).join('');
  } catch (e) {
    console.error('Failed to load products for reorder select:', e);
    toast('Failed to load products', 'error');
  }
}

async function loadReorderPlan() {
  const tbody  = document.getElementById('reorderPlanBody');
  const filter = document.getElementById('reorderFilter').value;
  const backupDays = getGlobalBackupDays();

  try {
    const res = await fetch(`${API}/reorder/plan/all?backup_days=${backupDays}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    const data = await res.json();
    let plan = data.plan;

    // Apply filter
    if (filter === 'today')    plan = plan.filter(p => p.days_until_reorder <= 0 && !p.is_reordered);
    else if (filter === 'tomorrow') plan = plan.filter(p => p.days_until_reorder > 0 && p.days_until_reorder <= 1 && !p.is_reordered);
    else if (filter === '7days')    plan = plan.filter(p => p.days_until_reorder <= 7 && !p.is_reordered);
    else if (filter === '10days')   plan = plan.filter(p => p.days_until_reorder <= 10 && !p.is_reordered);
    else if (filter === 'ordered')  plan = plan.filter(p => p.is_reordered);

    if (!plan.length) {
      tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state">✅ No items matching filter</div></td></tr>`;
      return;
    }

    tbody.innerHTML = plan.map(p => {
      let statusTag = '';
      if (p.is_reordered)              statusTag = '<span class="tag tag-blue">Ordered</span>';
      else if (p.days_until_reorder <= 0) statusTag = '<span class="tag tag-out">Critical</span>';
      else if (p.days_until_reorder <= 4) statusTag = '<span class="tag tag-low">Low Stock</span>';
      else                                statusTag = '<span class="tag tag-success">Healthy</span>';

      const daysColor = p.days_until_reorder <= 0 ? 'var(--rose)'
                      : p.days_until_reorder <= 4  ? 'var(--amber)' : 'var(--teal)';

      // Storage cap bar  (how full storage is)
      const storagePct = p.storage_capacity > 0
        ? Math.min(100, Math.round((p.current_stock / p.storage_capacity) * 100))
        : null;
      const storageBar = storagePct !== null
        ? `<div style="font-size:10px;color:var(--text3);margin-top:3px">
             <div style="height:3px;border-radius:2px;background:var(--bg3);width:60px;display:inline-block;vertical-align:middle">
               <div style="height:3px;border-radius:2px;background:${storagePct > 80 ? 'var(--rose)' : 'var(--teal)'};width:${storagePct}%"></div>
             </div>
             <span style="margin-left:4px">${p.current_stock}/${p.storage_capacity}</span>
           </div>`
        : `<div style="font-size:10px;color:var(--text3)">${p.current_stock} units</div>`;

      return `
        <tr>
          <td>
            <div style="font-weight:600">${p.product_name}</div>
            <div style="font-size:10px;color:var(--text3)">${p.category || p.product_id}</div>
          </td>
          <td>
            <div>${p.current_stock}</div>
            ${storageBar}
          </td>
          <td>${p.reorder_point || '—'}</td>
          <td style="font-size:11px;color:var(--text3)">${p.storage_capacity || '—'} <span style="font-size:9px">(${p.backup_days}d)</span></td>
          <td style="color:${daysColor};font-weight:600">${p.days_until_reorder <= 0 ? 'Due Now' : p.days_until_reorder + ' d'}</td>
          <td class="mono" style="font-size:11px">${p.estimated_reorder_date}</td>
          <td>${statusTag}</td>
          <td>
            ${p.is_reordered
              ? `<button class="btn btn-ghost btn-sm" onclick="toggleOrdered('${p.product_id}', false)">Clear</button>`
              : `<button class="btn btn-primary btn-sm" onclick="toggleOrdered('${p.product_id}', true)">Order</button>`}
          </td>
        </tr>`;
    }).join('');

  } catch (e) {
    console.error('Reorder plan error:', e);
    toast('Failed to load reorder plan', 'error');
  }
}

async function toggleOrdered(pid, status) {
  try {
    const endpoint = status ? 'mark-ordered' : 'mark-received';
    const res = await fetch(`${API}/reorder/${pid}/${endpoint}`, { method: 'POST' });
    if (!res.ok) throw new Error();
    toast(status ? 'Marked as ordered ✅' : 'Reorder status cleared', 'success');
    loadReorderPlan();
  } catch (e) {
    toast('Action failed', 'error');
  }
}

async function runReorder() {
  const product    = document.getElementById('reorderProduct').value;
  if (!product) { toast('Please select a product first', 'error'); return; }

  // Per-product backup days override, fallback to global
  const perProductDays = document.getElementById('productBackupDays')?.value;
  const backupDays     = perProductDays ? parseInt(perProductDays, 10) : getGlobalBackupDays();

  document.getElementById('reorderResults').style.display = 'none';
  document.getElementById('reorderEmpty').style.display   = 'none';
  document.getElementById('reorderLoading').style.display = 'block';

  try {
    const url = `${API}/reorder/${encodeURIComponent(product)}?backup_days=${backupDays}`;
    const res = await fetch(url);
    if (!res.ok) {
      let msg = `Server error (${res.status})`;
      try { msg = (await res.json()).detail; } catch {}
      throw new Error(msg);
    }
    const data = await res.json();
    const showError = (msg) => typeof toast === "function" ? toast(msg, 'error') : console.error(msg);
    if (!data || !data.product_name) {
        showError("Invalid reorder response");
        document.getElementById('reorderLoading').style.display = 'none';
        document.getElementById('reorderEmpty').style.display = 'block';
        return;
    }

    document.getElementById('reorderLoading').style.display = 'none';
    document.getElementById('reorderResults').style.display = 'block';

    // ── Inventory size label on results card ──
    const { label: invLabel, color: invColor, bg: invBg, border: invBorder } = inventorySizeLabel(data.backup_days || backupDays);
    const labelEl = document.getElementById('reorderInventoryLabel');
    if (labelEl) {
      labelEl.textContent = invLabel;
      labelEl.style.color = invColor;
      labelEl.style.background = invBg;
      labelEl.style.borderColor = invBorder;
      labelEl.style.boxShadow = `0 0 12px ${invBg}`;
    }

    const statusColor = (data.reorder_status === 'Out of Stock' || data.reorder_status === 'Critical Reorder') ? 'rose'
                      : data.reorder_status === 'Low Stock' ? 'amber'
                      : data.reorder_status === 'Ordered' ? 'blue' : 'teal';

    document.getElementById('reorderMetrics').innerHTML = `
      <div class="metric-card">
        <div class="metric-label">Status</div>
        <div class="metric-value" style="font-size:16px;color:var(--${statusColor})">${data.reorder_status || '—'}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Days Left</div>
        <div class="metric-value" style="color:${data.days_until_reorder <= 4 ? 'var(--amber)' : 'inherit'}">
          ${data.days_until_reorder <= 0 ? 'Due Now' : data.days_until_reorder + ' d'}
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Target Date</div>
        <div class="metric-value" style="font-size:14px">${data.estimated_reorder_date}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Suggested Qty</div>
        <div class="metric-value" style="color:var(--accent)">${Math.round(data.suggested_order_quantity || 0)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Storage Cap</div>
        <div class="metric-value" style="font-size:14px">${data.storage_capacity || '—'} units</div>
      </div>
    `;

    // ── Breakdown table ──
    const rows = [
      ['Product',                  data.product_name || 'N/A'],
      ['Category',                 data.category     || 'N/A'],
      ['Backup Days Setting',      `${data.backup_days} days`],
      ['Current Stock',            `${fmt(data.current_stock || 0)} units`],
      ['Avg Daily Demand',         `${data.average_daily_demand || 0} units/day`],
      ['Lead Time',                `${data.lead_time || 0} days`],
      ['Shelf Life',               `${data.shelf_life_days || '—'} days`],
      ['Safety Stock (Dynamic)',   `${data.safety_stock || 0} units`],
      ['Reorder Point',            `${data.reorder_point || 0} units`],
      ['Storage Capacity (cap)',   `${data.storage_capacity || '—'} units`],
      ['Supplier Pack Size',       `${data.supplier_pack_size || 1} units`],
      ['EOQ (price-aware)',        `${Math.round(data.eoq || 0)} units`],
      ['Raw EOQ (unconstrained)',  `${Math.round(data.raw_eoq || 0)} units`],
      ['Suggested Order Qty',      `${Math.round(data.suggested_order_quantity || 0)} units`],
      ['Stock Coverage',           `${data.stock_coverage_days || 0} days`],
      ['Inventory Turnover',       `${(data.inventory_turnover_ratio || 0).toFixed(2)}×/year`],
    ];
    document.getElementById('reorderTableBody').innerHTML = rows.map(([k, v]) =>
      `<tr><td style="color:var(--text3);width:220px">${k}</td><td style="font-weight:500">${v}</td></tr>`
    ).join('');

    // ── Filter pipeline visual ──
    const filters = data.filters_applied || {};
    const pipeline = [
      { label: 'Base Qty',      value: '—',                         color: 'var(--bg3)' },
      { label: `Shelf cap ${Math.round(filters.shelf_life_cap || 0)}`,
                                value: `${data.shelf_life_days}d life`, color: 'var(--amber)' },
      { label: `Storage cap ${filters.storage_cap || '—'}`,
                                value: `${data.backup_days}d backup`, color: 'var(--teal)' },
      { label: `Pack ×${data.supplier_pack_size || 1}`,
                                value: 'round up',                   color: 'var(--green)' },
      { label: `= ${Math.round(data.suggested_order_quantity || 0)} units`,
                                value: 'final order',                color: 'var(--accent)' },
    ];
    document.getElementById('filterPipeline').innerHTML = pipeline.map((f, i) =>
      `${i > 0 ? '<span style="color:var(--text3);font-size:18px">→</span>' : ''}
       <div style="background:${f.color};border-radius:6px;padding:6px 10px;font-size:11px;color:#fff;text-align:center;min-width:80px">
         <div style="font-weight:700">${f.label}</div>
         <div style="opacity:0.8;font-size:10px">${f.value}</div>
       </div>`
    ).join('');

  } catch (e) {
    document.getElementById('reorderLoading').style.display = 'none';
    document.getElementById('reorderEmpty').style.display   = 'block';
    toast(e.message || 'Failed to calculate reorder plan', 'error');
  }
}
