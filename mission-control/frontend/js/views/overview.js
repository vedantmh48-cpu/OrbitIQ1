/* =========================================================================
   views/overview.js — console home: KPIs, active missions, live alert feed
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views.overview = {
  async load(root) {
    root.innerHTML = `
      <div class="view-stack">
        <div class="kpi-grid" id="ov-kpis">${MC.skeleton(4, 60).replace(/skeleton/g, "skeleton card")}</div>
        <div class="overview-grid">
          <section class="card">
            <div class="card-head">
              <h2>Active missions</h2>
              <span class="chip chip--accent" id="ov-mission-count">…</span>
            </div>
            <div class="card-body"><div id="ov-missions">${MC.skeleton(4)}</div></div>
          </section>
          <div style="display:flex;flex-direction:column;gap:1.25rem">
            <section class="card">
              <div class="card-head"><h2>Fleet</h2><span class="chip" id="ov-fleet-count">…</span></div>
              <div class="card-body"><div id="ov-fleet">${MC.skeleton(3, 12)}</div></div>
            </section>
            <section class="card">
              <div class="card-head"><h2>Alert feed</h2><a class="btn btn--ghost btn--sm" href="#/alerts">View all →</a></div>
              <div class="card-body"><div id="ov-alerts">${MC.skeleton(3)}</div></div>
            </section>
          </div>
        </div>
      </div>`;
    MC.setFoot("Fetching live overview…");

    const [overview, missions, alerts, sats] = await Promise.all([
      MC.api.overview(),
      MC.api.missions(),
      MC.api.alerts(),
      MC.api.satellites(),
    ]);

    renderKpis(overview);
    renderMissions(missions);
    renderFleet(sats);
    renderAlerts(alerts);

    MC.setFoot(
      `${overview.missions.total} missions · ${overview.fleet.total} satellites · ` +
        `${overview.alerts.unacked} unacknowledged alerts · updated ${MC.fmtUTC(Math.floor(Date.now() / 1000))}`
    );

    function renderKpis(ov) {
      const active = ov.missions.inProgress + ov.missions.holding;
      const unacked = ov.alerts.unacked;
      document.getElementById("ov-kpis").innerHTML = `
        <div class="kpi">
          <span class="kpi-label">Active missions</span>
          <span class="kpi-value">${active}</span>
          <span class="kpi-meta">${ov.missions.queued} queued · ${ov.missions.planned} planned</span>
          <span class="ring"></span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Fleet nominal</span>
          <span class="kpi-value">${ov.fleet.operational}<span style="font-size:.65em;color:var(--text-faint)">/${ov.fleet.total}</span></span>
          <span class="kpi-meta">${ov.fleet.standby} standby · ${ov.fleet.calibrating} calibrating</span>
          <span class="ring"></span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Unacknowledged alerts</span>
          <span class="kpi-value ${unacked ? "tone-warn" : "tone-ok"}">${unacked}</span>
          <span class="kpi-meta">${ov.alerts.critical} critical · ${ov.alerts.high} high</span>
          <span class="ring"></span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Avg link health</span>
          <span class="kpi-value">${ov.fleet.avgLinkHealth}%</span>
          <span class="kpi-meta"><span class="dot dot--ok"></span>fleet-wide RF link</span>
          <span class="ring"></span>
        </div>`;
    }

    function renderMissions(list) {
      const top = list.slice(0, 5);
      document.getElementById("ov-mission-count").textContent = activeLabel(list);
      if (!top.length) {
        document.getElementById("ov-missions").innerHTML =
          `<div class="empty-state"><p class="empty-title">No missions scheduled</p><p>Create one from the Missions view.</p></div>`;
        return;
      }
      document.getElementById("ov-missions").innerHTML = `
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Mission</th><th>Satellite</th><th>Status</th><th>Progress</th></tr></thead>
            <tbody>${top.map(missionRow).join("")}</tbody>
          </table>
        </div>`;
    }

    function missionRow(m) {
      return `
        <tr class="mission-row">
          <td><div class="mission-name"><span class="m-title">${MC.esc(m.name)}</span><span class="m-meta">${MC.esc(m.code)} · ${MC.esc(m.region)}</span></div></td>
          <td class="cell-mono">${MC.esc(m.satellite)}</td>
          <td>${MC.statusBadge(m.status)}</td>
          <td><div class="progress-in-cell">
            <div class="progress" style="flex:1"><span class="progress-fill" style="width:${m.progress}%"></span></div>
            <span class="pct">${m.progress}%</span>
          </div></td>
        </tr>`;
    }

    function activeLabel(list) {
      const active = list.filter((m) => m.status === "in-progress" || m.status === "holding").length;
      return `${active} active · ${list.length} total`;
    }

    function renderFleet(satList) {
      document.getElementById("ov-fleet-count").textContent = `${satList.length} assets`;
      const avg = satList.reduce((a, s) => a + s.linkHealth, 0) / satList.length;
      document.getElementById("ov-fleet").innerHTML = `
        <div class="fleet-strip">
          ${satList.map((s) => `
            <span class="fleet-item ${s.status === "operational" ? "" : "is-warn"}">
              <span class="dot ${MC.dotByStatus(s.status)}"></span>
              <span class="fi-name">${MC.esc(s.name)}</span>
              <span class="tone-dim">${MC.esc(s.orbit.split("·")[0])}</span>
            </span>`).join("")}
        </div>
        <div class="progress-track" style="margin-top:1rem;align-items:center">
          <span>Fleet link:</span>
          <span class="progress" style="flex:1"><span class="progress-fill progress-fill--ok" style="width:${avg}%"></span></span>
          <span>${avg.toFixed(1)}%</span>
        </div>`;
    }

    function renderAlerts(list) {
      const top = list.filter((a) => !a.acknowledged).slice(0, 4);
      document.getElementById("ov-alerts").innerHTML = top.length
        ? `<ul class="feed-list">${top.map(alertItem).join("")}</ul>`
        : `<div class="empty-state"><p class="empty-title">All clear</p><p>No unacknowledged alerts on the floor.</p></div>`;
    }

    function alertItem(a) {
      return `
        <li class="feed-item is-${a.severity}">
          <span class="feed-sev"></span>
          <div class="feed-body">
            <p class="feed-title">${MC.esc(a.title)}</p>
            <p class="feed-meta">${MC.esc(a.source)} · <time>${MC.timeAgo(a.createdAt)}</time></p>
          </div>
        </li>`;
    }
  },
};