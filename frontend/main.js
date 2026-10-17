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
    const isHealthy = rh.status === 'ok' || rh.status === 'healthy';
    const isDegraded = rh.status === 'degraded';
    setStatusCard('health-routing-status', rh.status, isHealthy ? 'ok' : isDegraded ? 'warn' : 'error');
    setStatusCard('health-db-status', rh.database || '—', rh.database === 'connected' ? 'ok' : 'warn');
    setStatusCard('health-redis-status', rh.redis || '—', rh.redis === 'connected' ? 'ok' : 'warn');
    setStatusCard('health-predictor-status', rh.predictor || '—',
      rh.predictor === 'loaded' ? 'ok' : rh.predictor === 'heuristic_fallback' ? 'warn' : 'error');
    document.getElementById('health-predictor-detail').textContent =
      rh.predictor_health ? `Status: ${rh.predictor_health}` : (rh.predictor === 'loaded' ? 'ST-GNN model active' : 'Persistence champion active');

    if (rh.dataset) {
      const nameEl = document.getElementById('telemetry-dataset-name');
      const nodesEl = document.getElementById('telemetry-nodes');
      const samplingEl = document.getElementById('telemetry-sampling');
      const modelEl = document.getElementById('telemetry-model');
      const versionEl = document.getElementById('telemetry-version');
      const horizonsEl = document.getElementById('telemetry-horizons');
      const selectEl = document.getElementById('dataset-select');
      const provEl = document.getElementById('telemetry-provenance');
      const healthEl = document.getElementById('telemetry-predictor-health');

      if (nameEl) nameEl.textContent = rh.dataset;
      if (nodesEl) nodesEl.textContent = rh.num_nodes || '—';
      if (samplingEl) samplingEl.textContent = rh.sampling_interval || '5 min';
      if (modelEl) modelEl.textContent = rh.model || 'ST-GNN';
      if (versionEl) versionEl.textContent = rh.model_version || 'stgnn-v1';
      if (horizonsEl && rh.horizons) horizonsEl.textContent = rh.horizons.join(' / ');
      if (selectEl && rh.dataset_mode) selectEl.value = rh.dataset_mode;
      if (provEl) {
        provEl.textContent = rh.is_synthetic ? 'Synthetic (Simulated)' : 'Live Sensor Feed';
        provEl.style.color = rh.is_synthetic ? '#f59e0b' : '#10b981';
      }
      if (healthEl) {
        healthEl.textContent = rh.predictor_health || (rh.predictor === 'loaded' ? 'ST-GNN active' : 'Champion: Persistence');
      }
    }

    const headerBadge = document.getElementById('header-data-badge');
    if (headerBadge) {
      if (rh && rh.is_synthetic) {
        headerBadge.textContent = '🟡 Simulation';
        headerBadge.style.color = '#f59e0b';
        headerBadge.style.background = 'rgba(245, 158, 11, 0.15)';
        headerBadge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
      } else if (rh) {
        headerBadge.textContent = '🟢 Live Sensors';
        headerBadge.style.color = '#10b981';
        headerBadge.style.background = 'rgba(16, 185, 129, 0.15)';
        headerBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      }
    }

    const degradedBox = document.getElementById('degraded-warning-container');
    const degradedText = document.getElementById('degraded-warning-text');
    if (degradedBox) {
      if (rh && (rh.status === 'degraded' || rh.redis === 'process_local_fallback')) {
        degradedBox.style.display = 'block';
        if (degradedText) {
          degradedText.textContent = '⚠️ System operating in degraded mode: Process-local fallback counter active. Cross-instance capacity is not synchronized.';
        }
      } else {
        degradedBox.style.display = 'none';
      }
    }
  } catch (err) {
    setStatusCard('health-routing-status', 'offline', 'error');
    setStatusCard('health-db-status', '—', 'error');
    setStatusCard('health-redis-status', '—', 'error');
    setStatusCard('health-predictor-status', '—', 'error');
  }

  // Audit Service
  try {
    const ah = await api(auditUrl('/health?full=true'));
    const isAuditOk = ah.status === 'ok' || ah.status === 'healthy';
    setStatusCard('health-audit-status', ah.status, isAuditOk ? 'ok' : 'error');
  } catch {
    setStatusCard('health-audit-status', 'offline', 'error');
  }

  // Global dot
  const routingStatus = document.getElementById('health-routing-status').textContent;
  const auditStatus = document.getElementById('health-audit-status').textContent;
  const routingOk = routingStatus === 'ok' || routingStatus === 'healthy';
  const auditOk = auditStatus === 'ok' || auditStatus === 'healthy';
  if (routingOk && auditOk) {
    statusDot.classList.remove('offline');
    statusText.textContent = 'All systems operational';
  } else if (routingStatus === 'degraded' || auditStatus === 'degraded') {
    statusDot.classList.add('offline');
    statusText.textContent = 'System operating in degraded mode';
  } else {
    statusDot.classList.add('offline');
    statusText.textContent = 'Some services offline';
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

const btnApplyDataset = document.getElementById('btn-apply-dataset');
if (btnApplyDataset) {
  btnApplyDataset.addEventListener('click', async () => {
    const ds = document.getElementById('dataset-select').value;
    try {
      await api(routingUrl('/dataset/select'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset: ds }),
      });
      showToast(`Active dataset set to ${ds.toUpperCase()}`);
      refreshHealth();
    } catch (err) {
      showToast(`Failed to switch dataset: ${err.message}`, 'error');
    }
  });
}

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
    const isModel = data.model_used === 'st_gnn';
    const modelBadge = isModel
      ? '<span class="tag tag--true">ST-GNN Neural Model</span>'
      : '<span class="tag tag--false">Deterministic Heuristic Fallback</span>';

    visual.innerHTML = `
      <div style="grid-column: 1 / -1; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--bg-surface-elevated); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
        <span style="font-size:13px; font-weight:600; color:var(--text-secondary)">Prediction Engine:</span>
        <div>${modelBadge}</div>
      </div>
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

// ── Route Sub-Tab Switcher ──────────────────────────────────────
const routeSubtabBtns = document.querySelectorAll('.subtab-btn[data-routesubtab]');
routeSubtabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.routesubtab;
    routeSubtabBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (target === 'graph-plan') {
      document.getElementById('route-subpanel-graph').classList.remove('hidden');
      document.getElementById('route-subpanel-manual').classList.add('hidden');
    } else {
      document.getElementById('route-subpanel-graph').classList.add('hidden');
      document.getElementById('route-subpanel-manual').classList.remove('hidden');
    }
  });
});

// ── Interactive Road Graph Map ──────────────────────────────────
const NODE_COORDINATES = {
  node_nw: [200, 110],
  node_n: [350, 110],
  node_ne: [500, 110],
  node_w: [200, 220],
  node_center: [350, 220],
  node_e: [500, 220],
  node_sw: [200, 330],
  node_s: [350, 330],
  node_se: [500, 330],
  hwy_west: [80, 220],
  hwy_east: [620, 220],
  hwy_north: [350, 30],
};

let currentSelectionStage = 'origin';

function updateMapNodeHighlights() {
  const origin = document.getElementById('plan-origin').value;
  const dest = document.getElementById('plan-destination').value;
  document.querySelectorAll('.map-node').forEach(el => {
    el.classList.remove('origin', 'destination');
    if (el.dataset.node === origin) el.classList.add('origin');
    if (el.dataset.node === dest) el.classList.add('destination');
  });
}

document.querySelectorAll('.map-node').forEach(nodeEl => {
  nodeEl.addEventListener('click', () => {
    const nodeId = nodeEl.dataset.node;
    if (currentSelectionStage === 'origin') {
      document.getElementById('plan-origin').value = nodeId;
      updateMapNodeHighlights();
      currentSelectionStage = 'destination';
      showToast(`Origin set to ${nodeId}. Now select destination node.`);
    } else {
      document.getElementById('plan-destination').value = nodeId;
      updateMapNodeHighlights();
      currentSelectionStage = 'origin';
      showToast(`Destination set to ${nodeId}. Ready to plan trip.`);
    }
  });
});

const planOriginEl = document.getElementById('plan-origin');
const planDestEl = document.getElementById('plan-destination');
if (planOriginEl) planOriginEl.addEventListener('change', updateMapNodeHighlights);
if (planDestEl) planDestEl.addEventListener('change', updateMapNodeHighlights);

function drawPathsOnMap(paths) {
  const overlayGroup = document.getElementById('map-path-overlays');
  if (!overlayGroup) return;
  overlayGroup.innerHTML = '';

  const classMap = ['path-highlight-1', 'path-highlight-2', 'path-highlight-3'];

  paths.forEach((path, idx) => {
    const colorClass = classMap[idx] || 'path-highlight-3';
    const nodes = path.nodes;
    if (!nodes || nodes.length < 2) return;

    for (let i = 0; i < nodes.length - 1; i++) {
      const u = nodes[i];
      const v = nodes[i + 1];
      const uCoords = NODE_COORDINATES[u];
      const vCoords = NODE_COORDINATES[v];
      if (!uCoords || !vCoords) continue;

      const offset = (idx - 1) * 3;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', uCoords[0] + offset);
      line.setAttribute('y1', uCoords[1] + offset);
      line.setAttribute('x2', vCoords[0] + offset);
      line.setAttribute('y2', vCoords[1] + offset);
      line.setAttribute('class', `map-edge ${colorClass}`);
      overlayGroup.appendChild(line);
    }
  });
}

function renderGraphPlanResults(data) {
  const container = document.getElementById('graph-paths-visual');
  const resultsPanel = document.getElementById('graph-plan-results');
  if (!container || !resultsPanel) return;

  const ranked = data.ranked_routes || [];
  const assignments = data.assignments || {};
  const total = data.total_requests || 1;

  let html = '';
  ranked.forEach((r, idx) => {
    const assigned = assignments[r.route_id] || 0;
    const pct = total > 0 ? Math.round((assigned / total) * 100) : 0;
    const isWinner = idx === 0;
    const badgeColor = isWinner ? '#00ff88' : idx === 1 ? '#00d4ff' : '#a855f7';

    html += `
      <div class="ranked-card ${isWinner ? 'ranked-card--winner' : ''}" style="border-left: 4px solid ${badgeColor};">
        <div class="ranked-card__rank" style="color:${badgeColor}">Rank #${idx + 1} ${isWinner ? '★ Primary Selected' : 'Alternative Corridor'}</div>
        <div class="ranked-card__id">${escapeHtml(r.route_id)}</div>
        <div class="ranked-card__meta">
          <div>
            <span class="ranked-card__meta-label">Est. Travel Time</span>
            <span class="ranked-card__meta-value">${fmt(r.travel_time_s)} s</span>
          </div>
          <div>
            <span class="ranked-card__meta-label">Path Distance</span>
            <span class="ranked-card__meta-value">${fmt(r.distance_m)} m</span>
          </div>
          <div>
            <span class="ranked-card__meta-label">Priority Cost</span>
            <span class="ranked-card__meta-value">${fmt(r.effective_cost || r.priority_score)}</span>
          </div>
          <div>
            <span class="ranked-card__meta-label">Allocated Traffic</span>
            <span class="ranked-card__meta-value" style="color:${badgeColor}">${assigned} trips (${pct}%)</span>
          </div>
        </div>
        ${r.nodes ? `<div style="margin-top:10px; font-size:12px; font-family:var(--font-mono); color:#94a3b8; background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:4px;">Node Path: ${r.nodes.join(' → ')}</div>` : ''}
      </div>
    `;
  });
  container.innerHTML = html;

  // Render assignments bar
  const barContainer = document.getElementById('graph-assignments-bar');
  if (barContainer) {
    let barHtml = '';
    const colors = ['#00ff88', '#00d4ff', '#a855f7', '#ffb800'];
    let colorIdx = 0;
    for (const [rid, count] of Object.entries(assignments)) {
      const pct = total > 0 ? (count / total) * 100 : 0;
      if (pct > 0) {
        const c = colors[colorIdx % colors.length];
        barHtml += `
          <div class="assignments-bar__seg" style="width:${pct}%; background:${c};" title="${escapeHtml(rid)}: ${count} (${pct.toFixed(1)}%)">
            <span>${escapeHtml(rid)}: ${count} (${pct.toFixed(0)}%)</span>
          </div>
        `;
        colorIdx++;
      }
    }
    barContainer.innerHTML = barHtml || '<div style="color:var(--text-muted);font-size:13px;">No assignments.</div>';
  }

  // Render explanation
  const expGrid = document.getElementById('graph-explanation-grid');
  if (expGrid) {
    const exp = data.explanation || {};
    expGrid.innerHTML = `
      <div class="explanation-item">
        <div class="explanation-item__label">Recommended Corridor</div>
        <div class="explanation-item__value">${escapeHtml(exp.route_id || '—')}</div>
      </div>
      <div class="explanation-item">
        <div class="explanation-item__label">Trip Category & Weight</div>
        <div class="explanation-item__value">${escapeHtml(data.trip_category || '—')} (${exp.priority_context ? exp.priority_context.weight_applied : '1.0'}x)</div>
      </div>
      <div class="explanation-item">
        <div class="explanation-item__label">Diversification Status</div>
        <div class="explanation-item__value">${exp.diversification && exp.diversification.applied ? 'Active (Cap Applied)' : 'Direct Allocation'}</div>
      </div>
      <div class="explanation-item">
        <div class="explanation-item__label">Operational Mode</div>
        <div class="explanation-item__value">${exp.diversification && exp.diversification.is_degraded ? '⚠️ Degraded Fallback' : 'Healthy (Atomic)'}</div>
      </div>
    `;
  }

  resultsPanel.classList.remove('hidden');
}

const graphPlanForm = document.getElementById('graph-plan-form');
if (graphPlanForm) {
  graphPlanForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-graph-plan');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Computing Graph Paths…';

    try {
      const origin = document.getElementById('plan-origin').value;
      const dest = document.getElementById('plan-destination').value;
      const tripCat = document.getElementById('plan-trip-category').value;
      const count = parseInt(document.getElementById('plan-request-count').value, 10) || 1;
      const cap = parseFloat(document.getElementById('plan-cap-fraction').value) || 1.0;

      const data = await api(routingUrl('/route/plan'), {
        method: 'POST',
        body: JSON.stringify({
          origin_node: origin,
          destination_node: dest,
          trip_category: tripCat,
          request_count: count,
          cap_fraction: cap,
          k_alternatives: 3,
        }),
      });

      renderGraphPlanResults(data);
      drawPathsOnMap(data.candidate_paths);
      showToast(`Calculated ${data.candidate_paths.length} candidate paths from ${origin} to ${dest}`, 'success');
    } catch (err) {
      showToast(`Routing failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '🚀 Plan Physical Routes';
    }
  });
}

// ── Classical Custom Corridor Form ──────────────────────────────
// Add route row
const btnAddRoute = document.getElementById('btn-add-route');
if (btnAddRoute) {
  btnAddRoute.addEventListener('click', () => {
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
}

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
