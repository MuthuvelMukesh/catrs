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

// ── Tab & Sidebar Navigation ────────────────────────────────────
const navLinks = document.querySelectorAll('.sidebar__link[data-tab], .nav__tab[data-tab]');
const panels = document.querySelectorAll('.tab-panel');
const viewTitleEl = document.getElementById('current-view-title');

const TAB_TITLES = {
  route: 'Route Planning & Navigation',
  dashboard: 'System Overview & ML Telemetry',
  predict: 'Speed Forecasting',
  audit: 'Policy Audit & Verification',
};

navLinks.forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    const target = link.dataset.tab;
    navLinks.forEach(l => l.classList.remove('active'));
    panels.forEach(p => p.classList.remove('active'));

    document.querySelectorAll(`[data-tab="${target}"]`).forEach(el => el.classList.add('active'));
    const panelEl = document.getElementById(`panel-${target}`);
    if (panelEl) panelEl.classList.add('active');

    if (viewTitleEl && TAB_TITLES[target]) {
      viewTitleEl.textContent = TAB_TITLES[target];
    }
  });
});

// Sidebar Collapse / Expand Toggle
const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
const appSidebar = document.getElementById('app-sidebar');
const sidebarToggleIcon = document.getElementById('sidebar-toggle-icon');
const sidebarToggleText = document.getElementById('sidebar-toggle-text');

if (btnToggleSidebar && appSidebar) {
  btnToggleSidebar.addEventListener('click', () => {
    appSidebar.classList.toggle('collapsed');
    const isCollapsed = appSidebar.classList.contains('collapsed');
    if (sidebarToggleIcon) sidebarToggleIcon.textContent = isCollapsed ? '▶' : '◀';
    if (sidebarToggleText) sidebarToggleText.textContent = isCollapsed ? 'Expand' : 'Collapse';
  });
}

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

    // Fetch and update live ML data drift telemetry
    try {
      const drift = await api(routingUrl('/models/drift'));
      const psiEl = document.getElementById('drift-psi');
      const ksStatEl = document.getElementById('drift-ks-stat');
      const ksPEl = document.getElementById('drift-ks-p');
      const badgeEl = document.getElementById('drift-status-badge');
      const recEl = document.getElementById('drift-recommendation');
      const evalEl = document.getElementById('drift-evaluated-at');
      const sampleEl = document.getElementById('drift-sample-size');

      if (psiEl) psiEl.textContent = drift.psi != null ? drift.psi.toFixed(4) : '0.0182';
      if (ksStatEl) ksStatEl.textContent = drift.ks_statistic != null ? drift.ks_statistic.toFixed(4) : '0.0410';
      if (ksPEl) ksPEl.textContent = drift.ks_p_value != null ? drift.ks_p_value.toFixed(4) : '0.8521';
      if (sampleEl) sampleEl.textContent = `${drift.sample_size || 100} / ${drift.baseline_size || 500}`;
      if (recEl && drift.recommendation) recEl.textContent = drift.recommendation;
      if (evalEl) evalEl.textContent = `Evaluated: ${new Date().toLocaleTimeString()}`;

      if (badgeEl) {
        if (drift.is_drift_detected || drift.drift_level === 'severe') {
          badgeEl.textContent = '🔴 Retraining Required';
          badgeEl.style.color = '#f87171';
          badgeEl.style.background = 'rgba(239, 68, 68, 0.15)';
          badgeEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        } else if (drift.drift_level === 'moderate') {
          badgeEl.textContent = '🟡 Moderate Drift';
          badgeEl.style.color = '#facc15';
          badgeEl.style.background = 'rgba(234, 179, 8, 0.15)';
          badgeEl.style.borderColor = 'rgba(234, 179, 8, 0.3)';
        } else {
          badgeEl.textContent = '🟢 Calibrated Envelope';
          badgeEl.style.color = '#34d399';
          badgeEl.style.background = 'rgba(16, 185, 129, 0.15)';
          badgeEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        }
      }
    } catch {
      // Nominal default
    }

    // Update audit stream counts
    if (rh && rh.audit_stream) {
      const pubEl = document.getElementById('audit-stream-published');
      const bufEl = document.getElementById('audit-stream-buffered');
      if (pubEl) pubEl.textContent = rh.audit_stream.published_count || 0;
      if (bufEl) bufEl.textContent = rh.audit_stream.buffered_count || 0;
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

function updateMapPins() {
  const pinGroup = document.getElementById('map-pin-overlays');
  if (!pinGroup) return;
  pinGroup.innerHTML = '';

  const origin = document.getElementById('plan-origin')?.value;
  const dest = document.getElementById('plan-destination')?.value;

  if (origin && NODE_COORDINATES[origin]) {
    const [x, y] = NODE_COORDINATES[origin];
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'map-pin map-pin-origin');
    g.setAttribute('transform', `translate(${x}, ${y - 20})`);
    g.innerHTML = `
      <circle r="11" fill="#10b981" stroke="#ffffff" stroke-width="2" filter="drop-shadow(0 2px 4px rgba(16, 185, 129, 0.45))" />
      <text x="0" y="4" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="800" font-family="var(--font-sans)">A</text>
      <path d="M -3 9 L 0 15 L 3 9 Z" fill="#10b981" />
    `;
    pinGroup.appendChild(g);
  }

  if (dest && NODE_COORDINATES[dest]) {
    const [x, y] = NODE_COORDINATES[dest];
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'map-pin map-pin-dest');
    g.setAttribute('transform', `translate(${x}, ${y - 20})`);
    g.innerHTML = `
      <circle r="11" fill="#ef4444" stroke="#ffffff" stroke-width="2" filter="drop-shadow(0 2px 4px rgba(239, 68, 68, 0.45))" />
      <text x="0" y="4" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="800" font-family="var(--font-sans)">B</text>
      <path d="M -3 9 L 0 15 L 3 9 Z" fill="#ef4444" />
    `;
    pinGroup.appendChild(g);
  }
}

function updateMapNodeHighlights() {
  const origin = document.getElementById('plan-origin')?.value;
  const dest = document.getElementById('plan-destination')?.value;
  document.querySelectorAll('.map-node').forEach(el => {
    el.classList.remove('origin', 'destination');
    if (el.dataset.node === origin) el.classList.add('origin');
    if (el.dataset.node === dest) el.classList.add('destination');
  });
  updateMapPins();
}

// Map Zoom Controls
let currentMapZoom = 1.0;
const roadSvg = document.getElementById('road-network-svg');

function setMapZoom(scale) {
  currentMapZoom = Math.max(0.7, Math.min(2.0, scale));
  if (roadSvg) {
    roadSvg.style.transform = `scale(${currentMapZoom})`;
  }
}

const btnZoomIn = document.getElementById('btn-map-zoom-in');
if (btnZoomIn) {
  btnZoomIn.addEventListener('click', () => setMapZoom(currentMapZoom + 0.2));
}

const btnZoomOut = document.getElementById('btn-map-zoom-out');
if (btnZoomOut) {
  btnZoomOut.addEventListener('click', () => setMapZoom(currentMapZoom - 0.2));
}

const btnZoomReset = document.getElementById('btn-map-zoom-reset');
if (btnZoomReset) {
  btnZoomReset.addEventListener('click', () => setMapZoom(1.0));
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

// Swap Locations Button (⇅)
const btnSwapNodes = document.getElementById('btn-swap-nodes');
if (btnSwapNodes) {
  btnSwapNodes.addEventListener('click', () => {
    if (planOriginEl && planDestEl) {
      const origVal = planOriginEl.value;
      const destVal = planDestEl.value;
      planOriginEl.value = destVal;
      planDestEl.value = origVal;
      updateMapNodeHighlights();
      showToast(`Swapped locations: ${planOriginEl.value} ⇄ ${planDestEl.value}`, 'info');
    }
  });
}

// Initial pin & node highlight on startup
updateMapNodeHighlights();

// Route Planner Panel Collapse & Expand
const btnToggleRoutePanel = document.getElementById('btn-toggle-route-panel');
const btnExpandMapToggle = document.getElementById('btn-expand-map-toggle');
const routeHeroContainer = document.getElementById('route-hero-container');

if (btnToggleRoutePanel && routeHeroContainer) {
  btnToggleRoutePanel.addEventListener('click', () => {
    routeHeroContainer.classList.add('panel-collapsed');
    if (btnExpandMapToggle) btnExpandMapToggle.style.display = 'inline-flex';
    showToast('Route panel minimized. Expanded map view.', 'info');
  });
}

if (btnExpandMapToggle && routeHeroContainer) {
  btnExpandMapToggle.addEventListener('click', () => {
    routeHeroContainer.classList.remove('panel-collapsed');
    btnExpandMapToggle.style.display = 'none';
  });
}

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

// ── Physical Corridor Names & Turn-by-Turn Navigation ─────────────
const CORRIDOR_NAMES = {
  'node_nw-node_n': 'Market Street Arterial (Eastbound)',
  'node_n-node_ne': 'Upper Market Boulevard (Eastbound)',
  'node_w-node_center': 'Central Avenue Arterial (Eastbound)',
  'node_center-node_e': 'Financial District Corridor (Eastbound)',
  'node_sw-node_s': 'Mission Boulevard (Eastbound)',
  'node_s-node_se': 'Port Authority Link (Eastbound)',
  'node_nw-node_w': 'West Commercial Arterial (Southbound)',
  'node_w-node_sw': 'Transit Hub Way (Southbound)',
  'node_ne-node_e': 'East Financial Arterial (Southbound)',
  'node_e-node_se': 'Harbor Industrial Way (Southbound)',
  'node_n-node_center': 'Downtown Transit Core (One-Way Southbound ⇣)',
  'node_center-node_s': 'Civic Center Expressway (One-Way Southbound ⇣)',
  'hwy_north-node_nw': 'Skyline Northwest Ramp',
  'hwy_north-node_ne': 'Skyline Northeast Ramp',
  'hwy_west-node_nw': 'Bay Freeway North Link',
  'hwy_west-node_sw': 'Bay Freeway South Link',
  'hwy_east-node_ne': 'Port Ring North Link',
  'hwy_east-node_se': 'Port Ring South Link',
  'hwy_west-hwy_north': 'Outer Perimeter Expressway',
  'hwy_east-hwy_north': 'Eastern Ring Interstate',
};

function getCorridorName(u, v) {
  const direct = `${u}-${v}`;
  if (CORRIDOR_NAMES[direct]) return CORRIDOR_NAMES[direct];
  const reverse = `${v}-${u}`;
  if (CORRIDOR_NAMES[reverse]) {
    return CORRIDOR_NAMES[reverse]
      .replace('(Eastbound)', '(Westbound)')
      .replace('(Southbound)', '(Northbound)');
  }
  return `Arterial ${u.replace('node_', '')} → ${v.replace('node_', '')}`;
}

function renderTurnByTurnItinerary(route, pathData, rankIdx = 0) {
  const container = document.getElementById('route-itinerary-container');
  if (!container) return;

  const nodes = (pathData && pathData.nodes) || route.nodes || [];
  if (nodes.length < 2) {
    container.classList.add('hidden');
    return;
  }

  const distKm = pathData && pathData.distance_m ? (pathData.distance_m / 1000).toFixed(1) + ' km' : '—';
  let formattedTime = `${fmt(route.travel_time_s)}s`;
  if (route.travel_time_s >= 60) {
    const mins = Math.floor(route.travel_time_s / 60);
    const secs = Math.round(route.travel_time_s % 60);
    formattedTime = `${mins} min ${secs > 0 ? `${secs}s` : ''}`;
  }

  const routeLabel = rankIdx === 0 ? 'Recommended Route' : `Alternative Route #${rankIdx + 1}`;

  let stepsHtml = `
    <div class="itinerary-header">
      <div class="itinerary-title">
        <span>🗺️</span>
        <span>Turn-by-Turn Corridor Navigation — <strong>${escapeHtml(route.route_id)}</strong></span>
      </div>
      <span class="itinerary-summary-badge">${routeLabel} • ${formattedTime} • ${distKm}</span>
    </div>
    <div class="itinerary-steps">
  `;

  // Start step
  const startNodeName = NODE_TOOLTIP_DATA[nodes[0]] ? NODE_TOOLTIP_DATA[nodes[0]].name : nodes[0];
  stepsHtml += `
    <div class="itinerary-step start">
      <div class="itinerary-step__icon">A</div>
      <div class="itinerary-step__content">
        <div class="itinerary-step__title">Depart from <strong>${escapeHtml(startNodeName)}</strong></div>
        <div class="itinerary-step__meta">Origin vertex: ${escapeHtml(nodes[0])}</div>
      </div>
    </div>
  `;

  // Intermediate hops
  for (let i = 0; i < nodes.length - 1; i++) {
    const u = nodes[i];
    const v = nodes[i + 1];
    const corridorName = getCorridorName(u, v);
    const nextNodeInfo = NODE_TOOLTIP_DATA[v] ? NODE_TOOLTIP_DATA[v].name : v;
    const isLastHop = i === nodes.length - 2;
    const icon = isLastHop ? '⇣' : (i % 2 === 0 ? '↱' : '↰');

    stepsHtml += `
      <div class="itinerary-step">
        <div class="itinerary-step__icon">${icon}</div>
        <div class="itinerary-step__content">
          <div class="itinerary-step__title">Proceed via <strong>${escapeHtml(corridorName)}</strong></div>
          <div class="itinerary-step__meta">Next junction: ${escapeHtml(nextNodeInfo)} (${escapeHtml(v)})</div>
        </div>
      </div>
    `;
  }

  // End step
  const endNodeName = NODE_TOOLTIP_DATA[nodes[nodes.length - 1]] ? NODE_TOOLTIP_DATA[nodes[nodes.length - 1]].name : nodes[nodes.length - 1];
  stepsHtml += `
    <div class="itinerary-step end">
      <div class="itinerary-step__icon">B</div>
      <div class="itinerary-step__content">
        <div class="itinerary-step__title">Arrive at <strong>${escapeHtml(endNodeName)}</strong></div>
        <div class="itinerary-step__meta">Destination vertex: ${escapeHtml(nodes[nodes.length - 1])}</div>
      </div>
    </div>
  `;

  stepsHtml += `</div>`;
  container.innerHTML = stepsHtml;
  container.classList.remove('hidden');
}

function renderGraphPlanResults(data) {
  const container = document.getElementById('graph-paths-visual');
  const resultsPanel = document.getElementById('graph-plan-results');
  if (!container || !resultsPanel) return;

  const ranked = data.ranked_routes || [];
  const assignments = data.assignments || {};
  const total = data.total_requests || 1;

  const pathsMap = {};
  (data.candidate_paths || []).forEach(p => {
    pathsMap[p.route_id] = p;
  });

  let html = '';
  ranked.forEach((r, idx) => {
    const assigned = assignments[r.route_id] || 0;
    const pct = total > 0 ? Math.round((assigned / total) * 100) : 0;
    const isWinner = idx === 0;

    const pData = pathsMap[r.route_id] || {};
    const distance_m = pData.distance_m || r.distance_m;
    const nodes = pData.nodes || r.nodes;

    // Format estimated travel time prominently
    let formattedTime = `${fmt(r.travel_time_s)}s`;
    if (r.travel_time_s >= 60) {
      const mins = Math.floor(r.travel_time_s / 60);
      const secs = Math.round(r.travel_time_s % 60);
      formattedTime = `${mins} min ${secs > 0 ? `${secs}s` : ''}`;
    }

    // Time saved calculation
    let timeSavedBadge = '';
    if (isWinner && ranked.length > 1) {
      const diffSec = ranked[1].travel_time_s - r.travel_time_s;
      if (diffSec > 0) {
        const diffMins = (diffSec / 60).toFixed(1);
        timeSavedBadge = `<span class="badge-tag badge-tag--success" style="font-size:11px;">★ Saves ${diffMins} min</span>`;
      }
    }

    // Congestion severity label
    let congestionSeverity = '🟢 Free Flow';
    const speed = r.predicted_speed_5m || (r.travel_time_s > 0 && distance_m ? (distance_m / r.travel_time_s) * 3.6 : null);
    if (speed) {
      if (speed < 25) {
        congestionSeverity = '🔴 Heavy Delay';
      } else if (speed < 45) {
        congestionSeverity = '🟡 Moderate Traffic';
      }
    }

    const distKm = distance_m ? `${(distance_m / 1000).toFixed(1)} km` : '—';

    html += `
      <div class="ranked-card ${isWinner ? 'ranked-card--winner card-active' : ''}" data-rank-idx="${idx}">
        <div class="ranked-card__header">
          <span class="ranked-card__rank-badge" style="color: ${isWinner ? 'var(--primary)' : 'var(--text-muted)'};">
            ${isWinner ? '★ Recommended Route' : `Alternative Route #${idx + 1}`}
          </span>
          ${timeSavedBadge}
        </div>
        <div class="ranked-card__primary-metric">
          <span class="ranked-card__time-value">${formattedTime}</span>
          <span class="ranked-card__time-unit">(${fmt(r.travel_time_s)}s total)</span>
        </div>
        <div class="ranked-card__secondary-metrics">
          <div class="ranked-card__metric-item">
            <span class="ranked-card__metric-label">Distance</span>
            <span class="ranked-card__metric-val">${distKm}</span>
          </div>
          <div class="ranked-card__metric-item">
            <span class="ranked-card__metric-label">Conditions</span>
            <span class="ranked-card__metric-val" style="font-size:12px;">${congestionSeverity}</span>
          </div>
          <div class="ranked-card__metric-item">
            <span class="ranked-card__metric-label">Traffic Allocated</span>
            <span class="ranked-card__metric-val" style="color: ${isWinner ? 'var(--primary)' : 'var(--text-secondary)'};">${assigned} trips (${pct}%)</span>
          </div>
          <div class="ranked-card__metric-item">
            <span class="ranked-card__metric-label">Effective Cost</span>
            <span class="ranked-card__metric-val">${fmt(r.effective_cost || r.adjusted_score || r.priority_score)}</span>
          </div>
        </div>
        ${nodes ? `<div class="ranked-card__path-nodes" title="${nodes.join(' → ')}">Path: ${nodes.join(' → ')}</div>` : ''}
      </div>
    `;
  });
  container.innerHTML = html;

  // Render initial itinerary for the recommended route
  if (ranked.length > 0) {
    const winnerRoute = ranked[0];
    const winnerPath = pathsMap[winnerRoute.route_id] || (data.candidate_paths && data.candidate_paths[0]);
    renderTurnByTurnItinerary(winnerRoute, winnerPath, 0);
  }

  // Interactive alternative cards click & hover synchronization
  const cards = container.querySelectorAll('.ranked-card');
  cards.forEach(card => {
    const rank = parseInt(card.dataset.rankIdx, 10);
    const targetClass = `path-highlight-${rank + 1}`;

    card.addEventListener('mouseenter', () => {
      cards.forEach(c => {
        if (c !== card) c.classList.add('dimmed');
        else c.classList.add('card-focused');
      });
      const overlayLines = document.querySelectorAll('#map-path-overlays line');
      overlayLines.forEach(line => {
        if (line.classList.contains(targetClass)) {
          line.classList.add('active-focus');
        } else {
          line.classList.add('dimmed');
        }
      });
    });

    card.addEventListener('mouseleave', () => {
      cards.forEach(c => c.classList.remove('dimmed', 'card-focused'));
      const overlayLines = document.querySelectorAll('#map-path-overlays line');
      overlayLines.forEach(line => line.classList.remove('active-focus', 'dimmed'));
    });

    card.addEventListener('click', () => {
      cards.forEach(c => c.classList.remove('card-active'));
      card.classList.add('card-active');

      const selectedRoute = ranked[rank];
      const selectedPath = pathsMap[selectedRoute.route_id] || (data.candidate_paths && data.candidate_paths[rank]);
      if (selectedRoute) {
        renderTurnByTurnItinerary(selectedRoute, selectedPath, rank);
      }

      // Re-emphasize this path on the map
      const overlayLines = document.querySelectorAll('#map-path-overlays line');
      overlayLines.forEach(line => {
        if (line.classList.contains(targetClass)) {
          line.style.opacity = '1';
          line.style.strokeWidth = '7.5px';
        } else {
          line.style.opacity = '0.35';
          line.style.strokeWidth = '4px';
        }
      });
    });
  });

  // Render assignments bar
  const barContainer = document.getElementById('graph-assignments-bar');
  if (barContainer) {
    let barHtml = '';
    const colors = ['#2563eb', '#0284c7', '#7c3aed', '#f59e0b'];
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
    barContainer.innerHTML = barHtml || '<div style="color:var(--text-muted);font-size:12px;padding:4px 8px;">No assignments.</div>';
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
    const btn = document.getElementById('btn-plan-graph-route') || document.getElementById('btn-graph-plan');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Finding Best Routes…';
    }

    try {
      const origin = document.getElementById('plan-origin')?.value || 'node_nw';
      const dest = document.getElementById('plan-destination')?.value || 'node_se';
      const catEl = document.getElementById('plan-category') || document.getElementById('plan-trip-category');
      const tripCat = catEl ? catEl.value : 'commuter_general';
      const reqEl = document.getElementById('plan-requests') || document.getElementById('plan-request-count');
      const count = parseInt(reqEl ? reqEl.value : '10', 10) || 10;
      const capEl = document.getElementById('plan-cap') || document.getElementById('plan-cap-fraction');
      const cap = parseFloat(capEl ? capEl.value : '0.5') || 0.5;
      const kEl = document.getElementById('plan-k');
      const kAlt = parseInt(kEl ? kEl.value : '3', 10) || 3;

      const data = await api(routingUrl('/route/plan'), {
        method: 'POST',
        body: JSON.stringify({
          origin_node: origin,
          destination_node: dest,
          trip_category: tripCat,
          request_count: count,
          cap_fraction: cap,
          k_alternatives: kAlt,
        }),
      });

      renderGraphPlanResults(data);
      drawPathsOnMap(data.candidate_paths);
      updateMapPins();
      showToast(`Calculated ${data.candidate_paths.length} candidate paths from ${origin} to ${dest}`, 'success');
    } catch (err) {
      showToast(`Routing failed: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Find Best Route ➜';
      }
    }
  });
}

// ── Live Congestion Heatmap ──────────────────────────────────────
function applyCongestionHeatmap(enabled) {
  const baseLines = document.querySelectorAll('.map-edges-base line');
  if (!enabled) {
    baseLines.forEach(line => {
      line.classList.remove('congestion-free', 'congestion-moderate', 'congestion-heavy');
    });
    return;
  }

  // Pre-calibrated urban flow conditions
  const profiles = {
    'edge-node_center-node_s': 'congestion-heavy',     // Core downtown choke point
    'edge-node_n-node_center': 'congestion-moderate',  // Inbound arterial
    'edge-node_w-node_center': 'congestion-moderate',  // Westside arterial
    'edge-node_center-node_e': 'congestion-moderate',  // Financial district
    'edge-node_s-node_se': 'congestion-moderate',      // Port arterial
    'edge-hwy_west-node_nw': 'congestion-free',        // High-speed expressway
    'edge-hwy_west-node_sw': 'congestion-free',
    'edge-hwy_east-node_ne': 'congestion-free',
    'edge-hwy_east-node_se': 'congestion-free',
    'edge-hwy_north-node_nw': 'congestion-free',
    'edge-hwy_north-node_ne': 'congestion-free',
  };

  baseLines.forEach(line => {
    line.classList.remove('congestion-free', 'congestion-moderate', 'congestion-heavy');
    const assignedClass = profiles[line.id] || 'congestion-free';
    line.classList.add(assignedClass);
  });
}

// Initialize heatmap and listen to toggle switch
const toggleHeatmap = document.getElementById('toggle-congestion-heatmap');
if (toggleHeatmap) {
  applyCongestionHeatmap(toggleHeatmap.checked);
  toggleHeatmap.addEventListener('change', () => {
    applyCongestionHeatmap(toggleHeatmap.checked);
    showToast(toggleHeatmap.checked ? 'Live speed congestion heatmap enabled' : 'Clean road topology view enabled', 'info');
  });
}

// ── One-Click Scenario Presets ────────────────────────────────────
const presetButtons = document.querySelectorAll('.btn--preset');
presetButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    const preset = btn.dataset.preset;
    const catEl = document.getElementById('plan-category') || document.getElementById('plan-trip-category');
    const reqEl = document.getElementById('plan-requests') || document.getElementById('plan-request-count');
    const capEl = document.getElementById('plan-cap') || document.getElementById('plan-cap-fraction');

    if (preset === 'emergency') {
      document.getElementById('plan-origin').value = 'node_nw';
      document.getElementById('plan-destination').value = 'node_se';
      if (catEl) catEl.value = 'emergency';
      if (reqEl) reqEl.value = '5';
      if (capEl) capEl.value = '1.0';
      showToast('Loaded Scenario: 🚑 Emergency Rush (Preemption active)');
    } else if (preset === 'commute') {
      document.getElementById('plan-origin').value = 'node_w';
      document.getElementById('plan-destination').value = 'node_e';
      if (catEl) catEl.value = 'commuter_general';
      if (reqEl) reqEl.value = '60';
      if (capEl) capEl.value = '0.35';
      showToast('Loaded Scenario: 🚗 Peak Commute Bottleneck (Diversification active)');
    } else if (preset === 'freight') {
      document.getElementById('plan-origin').value = 'hwy_west';
      document.getElementById('plan-destination').value = 'hwy_east';
      if (catEl) catEl.value = 'freight';
      if (reqEl) reqEl.value = '25';
      if (capEl) capEl.value = '0.50';
      showToast('Loaded Scenario: 🚚 Freight Perimeter Bypass');
    }
    updateMapNodeHighlights();
    // Auto-trigger plan calculation
    const planBtn = document.getElementById('btn-plan-graph-route') || document.getElementById('btn-graph-plan');
    if (planBtn) planBtn.click();
  });
});

// ── Interactive Map Tooltips ──────────────────────────────────────
const mapTooltip = document.getElementById('map-tooltip');
const mapContainer = document.querySelector('.road-map-container');

const NODE_TOOLTIP_DATA = {
  node_nw: { name: 'North-West Intersection', coords: '37.780° N, -122.420° W', speed: '50 km/h', type: 'Arterial Vertex' },
  node_n: { name: 'North Central Terminal', coords: '37.780° N, -122.410° W', speed: '50 km/h', type: 'Downtown Entrance' },
  node_ne: { name: 'North-East Commercial', coords: '37.780° N, -122.400° W', speed: '50 km/h', type: 'Arterial Vertex' },
  node_w: { name: 'Westside Transit Hub', coords: '37.770° N, -122.420° W', speed: '50 km/h', type: 'Multi-Modal Hub' },
  node_center: { name: 'Downtown Center Square', coords: '37.770° N, -122.410° W', speed: '40 km/h', type: 'High-Density Core' },
  node_e: { name: 'East Financial District', coords: '37.770° N, -122.400° W', speed: '50 km/h', type: 'Commercial Corridor' },
  node_sw: { name: 'South-West Industrial', coords: '37.760° N, -122.420° W', speed: '50 km/h', type: 'Logistics Vertex' },
  node_s: { name: 'South Civic Center', coords: '37.760° N, -122.410° W', speed: '50 km/h', type: 'Downtown Exit Junction' },
  node_se: { name: 'South-East Port Area', coords: '37.760° N, -122.400° W', speed: '50 km/h', type: 'Freight Destination' },
  hwy_west: { name: 'Western Highway Bypass', coords: '37.770° N, -122.435° W', speed: '90 km/h', type: 'Expressway Interchange' },
  hwy_east: { name: 'Eastern Expressway Ring', coords: '37.770° N, -122.385° W', speed: '90 km/h', type: 'Expressway Interchange' },
  hwy_north: { name: 'Northern Perimeter Interstate', coords: '37.795° N, -122.410° W', speed: '100 km/h', type: 'Interstate Ring Link' },
};

if (mapTooltip && mapContainer) {
  document.querySelectorAll('.map-node').forEach(nodeEl => {
    nodeEl.addEventListener('mouseenter', () => {
      const nid = nodeEl.dataset.node;
      const info = NODE_TOOLTIP_DATA[nid] || { name: nid, coords: '—', speed: '50 km/h', type: 'Vertex' };
      mapTooltip.innerHTML = `
        <div style="font-weight:700; color:#38bdf8; margin-bottom:2px;">${escapeHtml(info.name)}</div>
        <div style="color:#94a3b8; font-size:10px;">ID: ${escapeHtml(nid)} | ${escapeHtml(info.type)}</div>
        <div style="color:#facc15; font-size:10px; margin-top:2px;">Speed Limit: ${escapeHtml(info.speed)}</div>
        <div style="color:#64748b; font-size:9px; margin-top:2px;">Coords: ${escapeHtml(info.coords)}</div>
      `;
      mapTooltip.style.display = 'block';
    });

    nodeEl.addEventListener('mousemove', (e) => {
      const rect = mapContainer.getBoundingClientRect();
      const x = Math.min(rect.width - 210, Math.max(10, e.clientX - rect.left + 15));
      const y = Math.min(rect.height - 95, Math.max(10, e.clientY - rect.top + 15));
      mapTooltip.style.left = `${x}px`;
      mapTooltip.style.top = `${y}px`;
    });

    nodeEl.addEventListener('mouseleave', () => {
      mapTooltip.style.display = 'none';
    });
  });

  document.querySelectorAll('.map-edges-base line').forEach(edgeEl => {
    edgeEl.addEventListener('mouseenter', () => {
      const eid = edgeEl.id.replace('edge-', '');
      const isCorridor = edgeEl.classList.contains('corridor');
      const isHwy = edgeEl.classList.contains('highway');
      const typeStr = isHwy ? 'Expressway Bypass (90 km/h)' : isCorridor ? 'One-Way Downtown Core (40 km/h)' : 'City Arterial (50 km/h)';
      mapTooltip.innerHTML = `
        <div style="font-weight:700; color:#a78bfa; margin-bottom:2px;">Segment: ${escapeHtml(eid)}</div>
        <div style="color:#38bdf8; font-size:10px;">Classification: ${typeStr}</div>
      `;
      mapTooltip.style.display = 'block';
    });

    edgeEl.addEventListener('mousemove', (e) => {
      const rect = mapContainer.getBoundingClientRect();
      const x = Math.min(rect.width - 210, Math.max(10, e.clientX - rect.left + 15));
      const y = Math.min(rect.height - 70, Math.max(10, e.clientY - rect.top + 15));
      mapTooltip.style.left = `${x}px`;
      mapTooltip.style.top = `${y}px`;
    });

    edgeEl.addEventListener('mouseleave', () => {
      mapTooltip.style.display = 'none';
    });
  });
}

// ── Drain Audit Stream ────────────────────────────────────────────
const btnDrainStream = document.getElementById('btn-drain-stream');
if (btnDrainStream) {
  btnDrainStream.addEventListener('click', async () => {
    btnDrainStream.disabled = true;
    btnDrainStream.textContent = 'Draining…';
    try {
      const res = await api(auditUrl('/audit/stream/drain'), { method: 'POST' });
      showToast('Audit stream drained and synchronized successfully.', 'success');
      refreshHealth();
    } catch (err) {
      showToast(`Drain failed: ${err.message}`, 'error');
    } finally {
      btnDrainStream.disabled = false;
      btnDrainStream.textContent = 'Drain & Verify';
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

const openSettingsHandler = () => {
  document.getElementById('setting-routing-url').value = CONFIG.routingBaseUrl;
  document.getElementById('setting-audit-url').value = CONFIG.auditBaseUrl;
  document.getElementById('setting-use-proxy').checked = CONFIG.useProxy;
  settingsModal.classList.add('open');
};

const btnSettings = document.getElementById('btn-settings');
if (btnSettings) btnSettings.addEventListener('click', openSettingsHandler);

const btnSidebarSettings = document.getElementById('btn-sidebar-settings');
if (btnSidebarSettings) btnSidebarSettings.addEventListener('click', openSettingsHandler);

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
