/* =========================================================================
   views/alerts.js — consolidated alert feed with acknowledgement
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views.alerts = {
  state: { filter: "all" },

  async load(root) {
    root.innerHTML = `
      <div class="view-stack">
        <div class="alerts-head">
          <div class="segmented" id="al-filter">
            <button class="seg is-active" data-filter="all">All</button>
            <button class="seg" data-filter="unacked">Unacknowledged</button>
          </div>
          <div class="summary-pills" id="al-summary">…</div>
        </div>
        <section class="card">
          <div class="card-head"><h2>Alert feed</h2><span class="chip" id="al-count">…</span></div>
          <div class="card-body" id="al-body">${MC.skeleton(4)}</div>
        </section>
      </div>`;
    MC.setFoot("Polling ground-station alert bus…");

    const alerts = await MC.api.alerts();
    this.render(alerts);

    MC.setFoot(
      `${alerts.length} alerts · ${alerts.filter((a) => !a.acknowledged).length} unacknowledged · feed from alert bus`
    );

    document.getElementById("al-filter").addEventListener("click", (e) => {
      const seg = e.target.closest(".seg");
      if (!seg) return;
      this.state.filter = seg.dataset.filter;
      document.querySelectorAll("#al-filter .seg").forEach((s) =>
        s.classList.toggle("is-active", s === seg)
      );
      this.render(alerts);
    });
    document.getElementById("al-body").addEventListener("click", async (e) => {
      const btn = e.target.closest('[data-ack]');
      if (!btn) return;
      try {
        const acked = await MC.api.ackAlert(btn.dataset.ack, true);
        MC.toast(acked ? "Alert acknowledged" : "Alert acknowledged", "ok");
        await MC.refreshView();
      } catch (err) {
        MC.toast(`Ack failed: ${err.message}`, "danger");
      }
    });
  },

  render(alerts) {
    const unacked = alerts.filter((a) => !a.acknowledged);
    const list =
      this.state.filter === "unacked"
        ? unacked
        : alerts;

    document.getElementById("al-count").textContent = `${list.length} shown`;
    document.getElementById("al-summary").innerHTML = [
      pill("Unacked", unacked.length, unacked.length ? "chip--warn" : "chip--ok"),
      pill(
        "Critical",
        unacked.filter((a) => a.severity === "critical").length,
        "chip--danger"
      ),
      pill("High", unacked.filter((a) => a.severity === "high").length, "chip--danger"),
    ].join("");

    const body = document.getElementById("al-body");
    if (!list.length) {
      body.innerHTML = `<div class="empty-state"><p class="empty-title">All clear</p><p>No alerts${this.state.filter === "unacked" ? " left to acknowledge" : ""}.</p></div>`;
      return;
    }
    body.innerHTML = list
      .map((a) => `
        <article class="alert-row ${a.acknowledged ? "" : "is-unacked"}">
          ${MC.sevBlock(a.severity)}
          <div class="al-body">
            <p class="al-title">${MC.esc(a.title)} ${a.acknowledged ? '<span class="badge badge--muted">acked</span>' : ""}</p>
            <p class="al-msg">${MC.esc(a.message)}</p>
            <p class="al-meta">
              <span>${MC.esc(a.source)}</span> · <time>${MC.timeAgo(a.createdAt)}</time> · ${MC.fmtISO(a.createdAt)}
            </p>
          </div>
          ${a.acknowledged ? "" : `<button class="btn btn--sm btn--ok" data-ack="${a.id}">Acknowledge</button>`}
        </article>`)
      .join("");

    function pill(label, n, tone) {
      return `<span class="chip ${tone}">${label} · ${n}</span>`;
    }
  },
};