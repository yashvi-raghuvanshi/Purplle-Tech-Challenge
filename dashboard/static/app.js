const POLL_MS = 2000;
const storeSelect = document.getElementById("store-select");
const feedStatus = document.getElementById("feed-status");
const lastUpdated = document.getElementById("last-updated");

let prevVisitors = null;

function flash(el) {
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 600);
}

function pct(n) {
  return `${(n * 100).toFixed(1)}%`;
}

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

function renderMetrics(data) {
  const visitorsEl = document.getElementById("m-visitors");
  const v = data.unique_visitors ?? 0;
  if (prevVisitors !== null && v !== prevVisitors) flash(visitorsEl);
  prevVisitors = v;

  visitorsEl.textContent = v;
  document.getElementById("m-conversion").textContent = pct(data.conversion_rate ?? 0);
  document.getElementById("m-queue").textContent = data.queue_depth ?? 0;
  document.getElementById("m-abandon").textContent = pct(data.abandonment_rate ?? 0);
  document.getElementById("m-meta").textContent =
    `${data.customer_events ?? 0} customer events · ${data.total_events ?? 0} total`;
}

function renderFunnel(data) {
  const root = document.getElementById("funnel");
  root.innerHTML = "";
  const max = Math.max(...(data.funnel || []).map((s) => s.count), 1);

  (data.funnel || []).forEach((stage) => {
    const row = document.createElement("div");
    row.className = "funnel-step";
    const width = Math.round((stage.count / max) * 100);
    row.innerHTML = `
      <span>${stage.stage}</span>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar" style="width:${width}%"></div>
      </div>
      <span>${stage.count}</span>
    `;
    if (stage.drop_off_pct != null) {
      const drop = document.createElement("span");
      drop.className = "funnel-drop";
      drop.textContent = `−${stage.drop_off_pct}%`;
      row.appendChild(drop);
    }
    root.appendChild(row);
  });
}

function renderHeatmap(data) {
  document.getElementById("heatmap-confidence").textContent = data.data_confidence
    ? "High confidence (20+ sessions)"
    : "Low confidence (<20 sessions)";

  const root = document.getElementById("heatmap");
  root.innerHTML = "";
  (data.zones || []).forEach((z) => {
    const score = Math.round((z.visit_frequency + z.avg_dwell_normalized) / 2);
    const row = document.createElement("div");
    row.className = "zone-row";
    row.innerHTML = `
      <span>${z.zone_id}</span>
      <div class="zone-bar-wrap">
        <div class="zone-bar" style="width:${score}%"></div>
      </div>
      <span>${score}</span>
    `;
    root.appendChild(row);
  });
  if (!data.zones?.length) {
    root.innerHTML = '<p class="hint">No zone visits yet</p>';
  }
}

function renderAnomalies(data) {
  const root = document.getElementById("anomalies");
  root.innerHTML = "";
  const items = data.anomalies || [];
  if (!items.length) {
    root.innerHTML = '<li class="empty">No active anomalies</li>';
    return;
  }
  items.forEach((a) => {
    const li = document.createElement("li");
    li.className = `severity-${a.severity}`;
    li.innerHTML = `
      <strong>[${a.severity}]</strong> ${a.type}: ${a.message}
      <span class="action">${a.suggested_action}</span>
    `;
    root.appendChild(li);
  });
}

function updateFeedStatus(health, storeId) {
  const store = health.stores?.[storeId];
  if (!store) {
    feedStatus.textContent = "NO DATA";
    feedStatus.className = "badge badge--warn";
    return;
  }
  if (store.stale) {
    feedStatus.textContent = "STALE";
    feedStatus.className = "badge badge--stale";
  } else {
    feedStatus.textContent = "LIVE";
    feedStatus.className = "badge badge--ok";
  }
}

async function refresh() {
  const storeId = storeSelect.value;
  try {
    const [metrics, funnel, heatmap, anomalies, health] = await Promise.all([
      fetchJson(`/stores/${storeId}/metrics`),
      fetchJson(`/stores/${storeId}/funnel`),
      fetchJson(`/stores/${storeId}/heatmap`),
      fetchJson(`/stores/${storeId}/anomalies`),
      fetchJson("/health"),
    ]);
    renderMetrics(metrics);
    renderFunnel(funnel);
    renderHeatmap(heatmap);
    renderAnomalies(anomalies);
    updateFeedStatus(health, storeId);
    lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    feedStatus.textContent = "ERROR";
    feedStatus.className = "badge badge--stale";
    lastUpdated.textContent = `Error: ${err.message}`;
  }
}

storeSelect.addEventListener("change", () => {
  prevVisitors = null;
  refresh();
});

refresh();
setInterval(refresh, POLL_MS);
