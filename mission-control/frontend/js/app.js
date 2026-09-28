/* =========================================================================
   app.js — Mission Control console shell
   Hash router, shared helpers, topbar (clock/theme/sidebar/search) and the
   global alert badge. Loads after the view modules (they register first).
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views = MC.views || {};

/* ---------------------------------------------------------------------------
   Shared helpers
   --------------------------------------------------------------------------- */

MC.esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

MC.fmtNum = (n) => Number(n ?? 0).toLocaleString("en-US", { maximumFractionDigits: 1 });

MC.fmtUTC = (epochSeconds) =>
  epochSeconds ? new Date(epochSeconds * 1000).toISOString().slice(11, 19) + " UTC" : "—";

MC.fmtISO = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ") + "Z";
};

MC.timeAgo = (iso) => {
  if (!iso) return "—";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "moments ago";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

/* Status → badge modifier + label */
const STATUS_META = {
  "in-progress": { cls: "badge--ok", label: "In progress" },
  holding: { cls: "badge--warn", label: "Holding" },
  queued: { cls: "badge--info", label: "Queued" },
  planned: { cls: "badge--info", label: "Planned" },
  completed: { cls: "badge--muted", label: "Completed" },
  aborted: { cls: "badge--danger", label: "Aborted" },
};
MC.statusBadge = (status) => {
  const m = STATUS_META[status] || { cls: "badge--muted", label: status };
  return `<span class="badge ${m.cls}">${MC.esc(m.label)}</span>`;
};

const SEV_META = {
  critical: { label: "CRIT", cls: "sev-critical" },
  high: { label: "HIGH", cls: "sev-high" },
  medium: { label: "MED", cls: "sev-medium" },
  low: { label: "LOW", cls: "sev-low" },
  info: { label: "INFO", cls: "sev-info" },
};
MC.sevBlock = (sev) => {
  const m = SEV_META[sev] || { label: sev, cls: "sev-info" };
  return `<span class="al-sev ${m.cls}">${m.label}</span>`;
};

MC.dotByStatus = (status) =>
  ({
    "in-progress": "dot--ok",
    holding: "dot--warn",
    queued: "dot--info",
    planned: "dot--info",
    completed: "dot--muted",
    aborted: "dot--danger",
    operational: "dot--ok",
    standby: "dot--info",
    calibrating: "dot--warn",
    maintenance: "dot--danger",
  }[status] || "dot--muted");

/* ------- chart SVG builder ---------------------------------------------- */
MC.chartSVG = (values, { width = 720, height = 176, stroke = null, label = "" } = {}) => {
  if (!values || values.length < 2) {
    return `<svg class="chart" viewBox="0 0 ${width} ${height}"></svg>`;
  }
  const pad = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = height - pad - ((v - min) / span) * (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const st = stroke || "var(--accent)";
  const grid = [0.25, 0.5, 0.75]
    .map((f) => `${pad} ${(height - pad - f * (height - pad * 2)).toFixed(1)}L${width - pad} ${(height - pad - f * (height - pad * 2)).toFixed(1)}`)
    .map((d) => "M" + d);
  return `
<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${MC.esc(label)}">
  <path class="chart-grid" d="${grid.join(" ")}" />
  ${label ? `<text class="chart-label" x="${pad}" y="${height - 1}">${MC.esc(label)}</text>` : ""}
  <polyline class="chart-fill" points="${pts.join(" ")}" />
</svg>`;
};

/* ------- skeleton builder ------------------------------------------------ */
MC.skeleton = (lines = 3, height = 14) => {
  let rows = "";
  for (let i = 0; i < lines; i++) {
    rows += `<div class="skeleton" style="height:${height}px;width:${100 - i * 12}%"></div>`;
  }
  return rows;
};

/* ------- toast ------------------------------------------------------------ */
MC.toast = (message, tone = "") => {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const node = document.createElement("div");
  node.className = `toast toast--${tone}`;
  node.innerHTML = MC.esc(message);
  stack.appendChild(node);
  if (stack.children.length > 4) stack.firstElementChild?.remove();
  setTimeout(() => {
    node.classList.add("is-leaving");
    setTimeout(() => node.remove(), 260);
  }, 3600);
};

/* ------- modal ------------------------------------------------------------ */
MC.modal = (innerHtml, { onClose } = {}) => {
  const backdrop = document.getElementById("modal-backdrop");
  document.getElementById("modal-inner").innerHTML = innerHtml;
  backdrop.hidden = false;
  MC.modalOnClose = onClose;
  document.body.style.overflow = "hidden";
};

MC.closeModal = () => {
  const backdrop = document.getElementById("modal-backdrop");
  if (!backdrop || backdrop.hidden) return;
  backdrop.hidden = true;
  document.body.style.overflow = "";
  const cb = MC.modalOnClose;
  MC.modalOnClose = null;
  if (typeof cb === "function") cb();
};

/* ------- view title + footer ---------------------------------------------- */
MC.setTitle = (title, subtitle) => {
  document.getElementById("view-title").textContent = title;
  document.getElementById("view-subtitle").textContent = subtitle;
};
MC.setFoot = (text) => {
  document.getElementById("foot-stats").textContent = text;
};

/* ---------------------------------------------------------------------------
   Router
   --------------------------------------------------------------------------- */

const VIEW_META = {
  overview: { title: "Overview", subtitle: "Mission Control · Global fleet & environmental telemetry" },
  missions: { title: "Missions", subtitle: "Plan, monitor and command satellite mission passes" },
  fleet: { title: "Fleet", subtitle: "Satellite constellation · orbit & link status" },
  telemetry: { title: "Telemetry", subtitle: "Live spacecraft bus and downlink telemetry" },
  alerts: { title: "Alerts", subtitle: "Consolidated alert feed from all ground systems" },
};

async function route() {
  const name = (location.hash || "#/overview").replace(/^#\//, "").split("?")[0];
  const view = MC.views[name];
  if (!view) {
    location.hash = "#/overview";
    return;
  }
  const root = document.getElementById("view");
  document.querySelectorAll(".nav-link").forEach((a) => {
    a.classList.toggle("is-active", a.dataset.view === name);
  });
  const meta = VIEW_META[name];
  MC.setTitle(meta.title, meta.subtitle);
  root.dataset.enter = "";
  root.innerHTML = "";
  if (typeof MC.views[MC.currentView]?.unload === "function") {
    try { MC.views[MC.currentView].unload(); } catch (_) { /* noop */ }
  }
  MC.currentView = name;
  try {
    await view.load(root);
  } catch (err) {
    root.innerHTML = `<div class="card"><div class="empty-state"><p class="empty-title">Load failed</p><p>${MC.esc(err.message)}</p></div></div>`;
  }
}

MC.refreshView = route;

/* ---------------------------------------------------------------------------
   Topbar: UTC clock, theme toggle, sidebar, search, alert badge
   --------------------------------------------------------------------------- */

function startClock() {
  const tick = () => {
    const now = new Date();
    const iso = now.toISOString();
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    document.getElementById("utc-clock").textContent = iso.slice(11, 19) + " UTC";
    document.getElementById("utc-date").textContent = days[now.getUTCDay()] + " " + iso.slice(0, 10);
  };
  tick();
  setInterval(tick, 1000);
}

function setupTheme() {
  const root = document.documentElement;
  if (localStorage.getItem("mc-theme") === "light") root.dataset.theme = "light";
  document.getElementById("theme-toggle").addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    localStorage.setItem("mc-theme", root.dataset.theme);
    updateThemeIcons();
  });
  updateThemeIcons();
}
function updateThemeIcons() {
  const light = document.documentElement.dataset.theme === "light";
  document.getElementById("theme-icon-sun").hidden = !light;
  document.getElementById("theme-icon-moon").hidden = light;
}

function setupSidebar() {
  const btn = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  btn.addEventListener("click", () => {
    document.body.style.overflow = sidebar.classList.toggle("is-open") ? "hidden" : "";
  });
  document.querySelectorAll(".nav-link").forEach((a) =>
    a.addEventListener("click", () => {
      sidebar.classList.remove("is-open");
      document.body.style.overflow = "";
    })
  );
}

function setupSearch() {
  const input = document.getElementById("search-input");
  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      input.focus();
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && input.value.trim()) {
      MC.searchQuery = input.value.trim();
      input.value = "";
      location.hash = "#/missions";
    }
  });
}

async function pollAlertBadges() {
  try {
    const alerts = await MC.api.alerts();
    const unacked = alerts.filter((a) => !a.acknowledged).length;
    const bell = document.getElementById("bell-count");
    const nav = document.getElementById("nav-alerts-badge");
    bell.hidden = unacked === 0;
    bell.textContent = unacked;
    nav.hidden = unacked === 0;
    nav.textContent = unacked;
  } catch (_) {
    /* backend not reachable — keep badges hidden */
  }
}

/* ---------------------------------------------------------------------------
   Boot
   --------------------------------------------------------------------------- */

window.addEventListener("DOMContentLoaded", () => {
  startClock();
  setupTheme();
  setupSidebar();
  setupSearch();
  window.addEventListener("hashchange", route);
  document.getElementById("modal-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "modal-backdrop") MC.closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") MC.closeModal();
  });
  pollAlertBadges();
  setInterval(pollAlertBadges, 15000);
  route();
});