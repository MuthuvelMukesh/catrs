/* ═══════════════════════════════════════════════════════════════
   CATRS Dashboard — Application Logic
   ═══════════════════════════════════════════════════════════════ */

// ── Configuration ──────────────────────────────────────────────
const CONFIG = {
  // When useProxy is true, requests go through Vite's dev proxy
  useProxy: true,
  routingBaseUrl: 'http://localhost:8001',
  auditBaseUrl: 'http://localhost:8002',
  autoRefreshMs: 30000, // 30 seconds
};

function loadSettings() {
  try {
    const saved = localStorage.getItem('catrs-settings');
    if (saved) Object.assign(CONFIG, JSON.parse(saved));
  } catch { /* ignore */ }
}

function saveSettings() {
  localStorage.setItem('catrs-settings', JSON.stringify({
    useProxy: CONFIG.useProxy,
    routingBaseUrl: CONFIG.routingBaseUrl,
    auditBaseUrl: CONFIG.auditBaseUrl,
  }));
}

loadSettings();

// ── API Client ─────────────────────────────────────────────────
function routingUrl(path) {
  if (CONFIG.useProxy) return `/routing${path}`;
  return `${CONFIG.routingBaseUrl}${path}`;
}

function auditUrl(path) {
  if (CONFIG.useProxy) return `/audit${path}`;
  return `${CONFIG.auditBaseUrl}${path}`;
}

async function api(url, options = {}) {
  const defaultHeaders = { 'Content-Type': 'application/json' };
  const res = await fetch(url, {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  });
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || `HTTP ${res.status}`);
    return json;
  }
  const text = await res.text();
  if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
  return text;
}

// ── Toast System ───────────────────────────────────────────────
const toastContainer = document.getElementById('toast-container');

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ── Tab Navigation ─────────────────────────────────────────────
const tabs = document.querySelectorAll('.nav__tab');
const panels = document.querySelectorAll('.tab-panel');

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    tabs.forEach(t => t.classList.remove('active'));
    panels.forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`panel-${target}`).classList.add('active');
  });
});

// ── Sub-tab Navigation (Audit) ─────────────────────────────────
const subTabs = document.querySelectorAll('.sub-tab');
const subPanels = document.querySelectorAll('.sub-panel');

subTabs.forEach(st => {
  st.addEventListener('click', () => {
    const target = st.dataset.subtab;
    subTabs.forEach(t => t.classList.remove('active'));
    subPanels.forEach(p => p.classList.remove('active'));
    st.classList.add('active');
    document.getElementById(`subpanel-${target}`).classList.add('active');
  });
});

// ═══════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════

const statusDot = document.getElementById('global-status-dot');
const statusText = document.getElementById('global-status-text');

async function refreshHealth() {
  // Routing Engine
  try {
    const rh = await api(routingUrl('/health?full=true'));
    setStatusCard('health-routing-status', rh.status, rh.status === 'ok' ? 'ok' : 'error');
    setStatusCard('health-db-status', rh.database || '—', rh.database === 'connected' ? 'ok' : 'warn');
    setStatusCard('health-redis-status', rh.redis || '—', rh.redis === 'connected' ? 'ok' : 'warn');
    setStatusCard('health-predictor-status', rh.predictor || '—',
      rh.predictor === 'loaded' ? 'ok' : rh.predictor === 'fallback' ? 'warn' : 'error');
    document.getElementById('health-predictor-detail').textContent =
      rh.predictor === 'loaded' ? 'ST-GNN model active' : 'Heuristic fallback';
  } catch (err) {
    setStatusCard('health-routing-status', 'offline', 'error');
    setStatusCard('health-db-status', '—', 'error');
    setStatusCard('health-redis-status', '—', 'error');
    setStatusCard('health-predictor-status', '—', 'error');
  }

  // Audit Service
  try {
    const ah = await api(auditUrl('/health?full=true'));
    setStatusCard('health-audit-status', ah.status, ah.status === 'ok' ? 'ok' : 'error');
  } catch {
    setStatusCard('health-audit-status', 'offline', 'error');
  }

  // Global dot
  const routingOk = document.getElementById('health-routing-status').textContent === 'ok';
  const auditOk = document.getElementById('health-audit-status').textContent === 'ok';
  if (routingOk && auditOk) {
    statusDot.classList.remove('offline');
    statusText.textContent = 'All systems operational';
  } else {
    statusDot.classList.add('offline');
    statusText.textContent = 'Some services degraded';
  }
}

function setStatusCard(elementId, value, state) {
  const el = document.getElementById(elementId);
  el.textContent = value;
  el.className = 'status-card__value';
  if (state) el.classList.add(state);
}

async function refreshMetrics() {
  // Routing
  try {
    const text = await api(routingUrl('/metrics'));
    renderMetrics('metrics-routing-content', text);
  } catch {
    document.getElementById('metrics-routing-content').innerHTML =
      '<p style="color:var(--text-muted);font-size:13px;">Could not load metrics.</p>';
  }

  // Audit
  try {
    const text = await api(auditUrl('/metrics'));
    renderMetrics('metrics-audit-content', text);
  } catch {
    document.getElementById('metrics-audit-content').innerHTML =
      '<p style="color:var(--text-muted);font-size:13px;">Could not load metrics.</p>';
  }
}

function renderMetrics(containerId, prometheusText) {
  const container = document.getElementById(containerId);
  const lines = prometheusText.split('\n').filter(l => l && !l.startsWith('#'));
  if (lines.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">No metrics available.</p>';
    return;
  }
  let html = '';
  for (const line of lines) {
    const parts = line.split(/\s+/);
    const name = parts[0] || '';
    const value = parts[1] || '0';
    html += `<div class="metric-row">
      <span class="metric-row__name">${escapeHtml(name)}</span>
      <span class="metric-row__value">${escapeHtml(value)}</span>
    </div>`;
  }
  container.innerHTML = html;
}

function refreshDashboard() {
  refreshHealth();
  refreshMetrics();
}

document.getElementById('btn-refresh-dashboard').addEventListener('click', () => {
  showToast('Refreshing dashboard…', 'info');
  refreshDashboard();
});

// Auto-refresh
let dashboardInterval = setInterval(refreshDashboard, CONFIG.autoRefreshMs);
refreshDashboard();

// ═══════════════════════════════════════════════════════════════
// PREDICT
// ═══════════════════════════════════════════════════════════════

document.getElementById('predict-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-predict');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Predicting…';

  try {
    const payload = {
      segment_id: val('predict-segment-id'),
      current_speed: num('predict-current-speed'),
      current_volume: int('predict-current-volume'),
      historical_baseline_speed: num('predict-baseline-speed'),
      weather_severity_score: num('predict-weather'),
      active_incident_flag: document.getElementById('predict-incident').checked,
      event_proximity_score: num('predict-event-prox'),
      upstream_segment_congestion: num('predict-upstream'),
      time_of_day: int('predict-hour'),
      day_of_week: int('predict-dow'),
    };

    const data = await api(routingUrl('/predict'), {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    // Render visual cards
    const visual = document.getElementById('predict-visual');
    visual.innerHTML = `
      <div class="prediction-card">
        <div class="prediction-card__horizon">5 Minutes</div>
        <div class="prediction-card__speed">${fmt(data.predicted_speed_5m)}</div>
        <div class="prediction-card__unit">km/h predicted</div>
      </div>
      <div class="prediction-card">
        <div class="prediction-card__horizon">15 Minutes</div>
        <div class="prediction-card__speed">${fmt(data.predicted_speed_15m)}</div>
        <div class="prediction-card__unit">km/h predicted</div>
      </div>
      <div class="prediction-card">
        <div class="prediction-card__horizon">30 Minutes</div>
        <div class="prediction-card__speed">${fmt(data.predicted_speed_30m)}</div>
        <div class="prediction-card__unit">km/h predicted</div>
      </div>
    `;

    document.getElementById('predict-raw-json').textContent = JSON.stringify(data, null, 2);
    document.getElementById('predict-results').classList.remove('hidden');
    showToast(`Prediction complete for ${data.segment_id}`, 'success');
  } catch (err) {
    showToast(`Prediction failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Run Prediction';
  }
});

// ═══════════════════════════════════════════════════════════════
// ROUTE
// ═══════════════════════════════════════════════════════════════

// Add route row
document.getElementById('btn-add-route').addEventListener('click', () => {
  const rows = document.getElementById('route-rows');
  const idx = rows.children.length;
  const row = document.createElement('div');
  row.className = 'route-row';
  row.dataset.routeIdx = idx;
  row.innerHTML = `
    <div class="form-group">
      <label>Route ID</label>
      <input type="text" class="route-id" value="route_${idx}" required />
    </div>
    <div class="form-group">
      <label>Travel Time (s)</label>
      <input type="number" class="route-tt" value="300" step="1" min="0" />
    </div>
    <div class="form-group">
      <label>Priority Score</label>
      <input type="number" class="route-priority" value="1.0" step="0.1" />
    </div>
    <div class="form-group">
      <label>Distance (m)</label>
      <input type="number" class="route-distance" placeholder="Optional" step="1" min="1" />
    </div>
    <div class="form-group">
      <label>Speed 5m</label>
      <input type="number" class="route-speed5m" placeholder="Optional" step="0.1" min="0.1" />
    </div>
    <button type="button" class="btn btn--danger btn--sm btn-remove-route">✕</button>
  `;
  rows.appendChild(row);
});

// Remove route row (delegated)
document.getElementById('route-rows').addEventListener('click', (e) => {
  if (e.target.classList.contains('btn-remove-route')) {
    const rows = document.getElementById('route-rows');
    if (rows.children.length > 1) {
      e.target.closest('.route-row').remove();
    } else {
      showToast('At least one route option is required.', 'error');
    }
  }
});

// Submit route form
document.getElementById('route-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-route');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Ranking…';

  try {
    // Collect routes
    const routeRows = document.querySelectorAll('.route-row');
    const routes = [];
    const currentCounts = {};

    routeRows.forEach(row => {
      const routeId = row.querySelector('.route-id').value;
      const opt = { route_id: routeId };
      const tt = parseFloat(row.querySelector('.route-tt').value);
      if (!isNaN(tt)) opt.travel_time_s = tt;
      const ps = parseFloat(row.querySelector('.route-priority').value);
      if (!isNaN(ps)) opt.priority_score = ps;
      const dist = parseFloat(row.querySelector('.route-distance').value);
      if (!isNaN(dist) && dist > 0) opt.distance_m = dist;
      const spd = parseFloat(row.querySelector('.route-speed5m').value);
      if (!isNaN(spd) && spd > 0) opt.predicted_speed_5m = spd;
      routes.push(opt);
      currentCounts[routeId] = 0;
    });

    // Weight schedule
    let weights;
    try {
      weights = JSON.parse(document.getElementById('ws-weights').value);
    } catch {
      showToast('Invalid JSON in weight schedule weights.', 'error');
      return;
    }

    const payload = {
      trip_category: document.getElementById('route-trip-category').value,
      routes,
      request_count: int('route-request-count'),
      current_counts: currentCounts,
      cap_fraction: num('route-cap-fraction'),
      weight_schedule: {
        version: val('ws-version'),
        effective_date: val('ws-date'),
        weights,
      },
    };

    const data = await api(routingUrl('/route'), {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    // Render ranked routes
    renderRankedRoutes(data.ranked_routes);
    renderAssignments(data.assignments);
    renderExplanation(data.explanation);

    document.getElementById('route-raw-json').textContent = JSON.stringify(data, null, 2);
    document.getElementById('route-results').classList.remove('hidden');
    showToast('Route ranking complete!', 'success');
  } catch (err) {
    showToast(`Route ranking failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🚀 Rank Routes';
  }
});

function renderRankedRoutes(ranked) {
  const container = document.getElementById('route-ranked-visual');
  container.innerHTML = ranked.map((r, i) => `
    <div class="route-rank-card">
      <div class="route-rank__position">#${i + 1}</div>
      <div class="route-rank__details">
        <div class="route-rank__stat">
          <span class="route-rank__stat-label">Route ID</span>
          <span class="route-rank__stat-value">${escapeHtml(r.route_id)}</span>
        </div>
        <div class="route-rank__stat">
          <span class="route-rank__stat-label">Travel Time</span>
          <span class="route-rank__stat-value">${fmt(r.travel_time_s)}s</span>
        </div>
        <div class="route-rank__stat">
          <span class="route-rank__stat-label">Priority</span>
          <span class="route-rank__stat-value">${fmt(r.priority_score)}</span>
        </div>
        <div class="route-rank__stat">
          <span class="route-rank__stat-label">Weight</span>
          <span class="route-rank__stat-value">${fmt(r.weight_applied)}</span>
        </div>
        <div class="route-rank__stat">
          <span class="route-rank__stat-label">Adjusted Score</span>
          <span class="route-rank__stat-value">${fmt(r.adjusted_score)}</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderAssignments(assignments) {
  const container = document.getElementById('route-assignments-bar');
  const total = Object.values(assignments).reduce((a, b) => a + b, 0);
  const colors = [
    'var(--accent-blue)', 'var(--accent-green)', 'var(--accent-amber)',
    'var(--accent-purple)', 'var(--accent-red)', '#00bcd4',
  ];
  container.innerHTML = Object.entries(assignments).map(([routeId, count], i) => {
    const pct = total > 0 ? (count / total) * 100 : 0;
    return `<div class="assignments-bar__segment" style="width:${pct}%;background:${colors[i % colors.length]}" title="${routeId}: ${count} (${pct.toFixed(0)}%)">
      ${routeId.replace('route_', '')} ${count}
    </div>`;
  }).join('');
}

function renderExplanation(exp) {
  if (!exp) return;
  const grid = document.getElementById('route-explanation-grid');
  grid.innerHTML = `
    <div class="explanation-card">
      <div class="explanation-card__title">Recommended Route</div>
      <div class="explanation-card__content">
        <strong>${escapeHtml(exp.recommended_route?.route_id || '—')}</strong><br>
        Travel time: <strong>${fmt(exp.recommended_route?.predicted_travel_time_s)}s</strong>
      </div>
    </div>
    <div class="explanation-card">
      <div class="explanation-card__title">Priority Context</div>
      <div class="explanation-card__content">
        Category: <strong>${escapeHtml(exp.priority_context?.trip_category || '—')}</strong><br>
        Weight: <strong>${fmt(exp.priority_context?.weight_applied)}</strong><br>
        Affected ranking: <span class="tag tag--${exp.priority_context?.affected_ranking}">${exp.priority_context?.affected_ranking}</span>
      </div>
    </div>
    <div class="explanation-card">
      <div class="explanation-card__title">Diversification</div>
      <div class="explanation-card__content">
        Applied: <span class="tag tag--${exp.diversification?.applied}">${exp.diversification?.applied}</span><br>
        Pool: <strong>${fmt(exp.diversification?.assignment_pool_pct)}%</strong><br>
        <em style="color:var(--text-secondary);font-size:12px">${escapeHtml(exp.diversification?.reason || '')}</em>
      </div>
    </div>
    <div class="explanation-card">
      <div class="explanation-card__title">Alternatives (${exp.alternatives_considered?.length || 0})</div>
      <div class="explanation-card__content">
        ${(exp.alternatives_considered || []).map(a =>
          `#${a.rank} <strong>${escapeHtml(a.route_id)}</strong> — ${fmt(a.predicted_travel_time_s)}s`
        ).join('<br>')}
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// AUDIT — Single Outcome
// ═══════════════════════════════════════════════════════════════

document.getElementById('audit-single-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-audit-single');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Auditing…';

  try {
    const outcome = {
      trip_category: val('as-trip-cat'),
      weight_applied: num('as-weight-applied'),
      weight_schedule_version: val('as-ws-version'),
    };
    const routeId = val('as-route-id');
    if (routeId) outcome.route_id = routeId;
    const outcomeAt = document.getElementById('as-outcome-at').value;
    if (outcomeAt) outcome.outcome_at = new Date(outcomeAt).toISOString();

    let schWeights;
    try {
      schWeights = JSON.parse(document.getElementById('as-sch-weights').value);
    } catch {
      showToast('Invalid JSON in schedule weights.', 'error');
      return;
    }

    const payload = {
      outcome,
      weight_schedule: {
        version: val('as-sch-version'),
        effective_date: val('as-sch-date'),
        weights: schWeights,
      },
    };

    const data = await api(auditUrl('/audit/outcome'), {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    document.getElementById('audit-single-badge').innerHTML = data.valid
      ? '<span class="audit-badge audit-badge--valid">✓ Valid</span>'
      : '<span class="audit-badge audit-badge--invalid">✕ Invalid</span>';
    document.getElementById('audit-single-raw').textContent = JSON.stringify(data, null, 2);
    document.getElementById('audit-single-results').classList.remove('hidden');
    showToast(`Audit result: ${data.valid ? 'VALID' : 'INVALID'}`, data.valid ? 'success' : 'error');
  } catch (err) {
    showToast(`Audit failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔍 Audit Outcome';
  }
});

// ═══════════════════════════════════════════════════════════════
// AUDIT — Batch
// ═══════════════════════════════════════════════════════════════

document.getElementById('audit-batch-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-audit-batch');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Auditing…';

  try {
    let payload;
    try {
      payload = JSON.parse(document.getElementById('ab-payload').value);
    } catch {
      showToast('Invalid JSON in batch payload.', 'error');
      return;
    }

    const data = await api(auditUrl('/audit/batch'), {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    document.getElementById('audit-batch-badge').innerHTML = data.all_valid
      ? '<span class="audit-badge audit-badge--valid">✓ All Valid</span>'
      : '<span class="audit-badge audit-badge--invalid">✕ Has Failures</span>';

    renderAuditSummaryGrid('audit-batch-summary-grid', data);
    document.getElementById('audit-batch-raw').textContent = JSON.stringify(data, null, 2);
    document.getElementById('audit-batch-results').classList.remove('hidden');
    showToast(`Batch audit: ${data.valid_count}/${data.total} valid`, data.all_valid ? 'success' : 'error');
  } catch (err) {
    showToast(`Batch audit failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '📦 Run Batch Audit';
  }
});

// ═══════════════════════════════════════════════════════════════
// AUDIT — Summary
// ═══════════════════════════════════════════════════════════════

document.getElementById('audit-summary-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-audit-summary');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Summarizing…';

  try {
    let payload;
    try {
      payload = JSON.parse(document.getElementById('asum-payload').value);
    } catch {
      showToast('Invalid JSON in summary payload.', 'error');
      return;
    }

    const data = await api(auditUrl('/audit/summary'), {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    renderAuditSummaryGrid('audit-summary-grid', data);
    document.getElementById('audit-summary-results').classList.remove('hidden');
    showToast(`Summary: ${data.total} total, ${data.valid_count} valid`, 'success');
  } catch (err) {
    showToast(`Summary failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '📊 Get Summary';
  }
});

function renderAuditSummaryGrid(containerId, data) {
  document.getElementById(containerId).innerHTML = `
    <div class="audit-summary-stat">
      <div class="audit-summary-stat__value" style="color:var(--text-primary)">${data.total ?? '—'}</div>
      <div class="audit-summary-stat__label">Total</div>
    </div>
    <div class="audit-summary-stat">
      <div class="audit-summary-stat__value" style="color:var(--accent-green)">${data.valid_count ?? '—'}</div>
      <div class="audit-summary-stat__label">Valid</div>
    </div>
    <div class="audit-summary-stat">
      <div class="audit-summary-stat__value" style="color:var(--accent-red)">${data.invalid_count ?? '—'}</div>
      <div class="audit-summary-stat__label">Invalid</div>
    </div>
    <div class="audit-summary-stat">
      <div class="audit-summary-stat__value" style="color:var(--accent-amber)">${data.unresolved_count ?? '—'}</div>
      <div class="audit-summary-stat__label">Unresolved</div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// SETTINGS MODAL
// ═══════════════════════════════════════════════════════════════

const settingsModal = document.getElementById('settings-modal');

document.getElementById('btn-settings').addEventListener('click', () => {
  document.getElementById('setting-routing-url').value = CONFIG.routingBaseUrl;
  document.getElementById('setting-audit-url').value = CONFIG.auditBaseUrl;
  document.getElementById('setting-use-proxy').checked = CONFIG.useProxy;
  settingsModal.classList.add('open');
});

document.getElementById('btn-settings-cancel').addEventListener('click', () => {
  settingsModal.classList.remove('open');
});

document.getElementById('btn-settings-save').addEventListener('click', () => {
  CONFIG.routingBaseUrl = document.getElementById('setting-routing-url').value;
  CONFIG.auditBaseUrl = document.getElementById('setting-audit-url').value;
  CONFIG.useProxy = document.getElementById('setting-use-proxy').checked;
  saveSettings();
  settingsModal.classList.remove('open');
  showToast('Settings saved.', 'success');
  refreshDashboard();
});

// Close modal on overlay click
settingsModal.addEventListener('click', (e) => {
  if (e.target === settingsModal) settingsModal.classList.remove('open');
});

// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════

function val(id) {
  return document.getElementById(id).value.trim();
}

function num(id) {
  return parseFloat(document.getElementById(id).value) || 0;
}

function int(id) {
  return parseInt(document.getElementById(id).value, 10) || 0;
}

function fmt(v) {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return Number.isInteger(n) ? n.toString() : n.toFixed(3);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
