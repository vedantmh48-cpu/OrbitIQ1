/* =========================================================================
   views/fleet.js — satellite constellation status cards with mini telemetry
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views.fleet = {
  async load(root) {
    root.innerHTML = `
      <div class="view-stack">
        <section class="card">
          <div class="card-head">
            <h2>Constellation status</h2>
            <span class="chip chip--accent" id="fc-count">…</span>
          </div>
          <div class="card-body">
            <div class="fleet-grid" id="fc-grid">${MC.skeleton(6, 80).replace(/skeleton/g, "skeleton card")}</div>
          </div>
        </section>
      </div>`;
    MC.setFoot("Contacting flight dynamics…");

    const sats = await MC.api.satellites();
    const withTelemetry = await Promise.all(
      sats.map(async (s) => {
        try {
          const tl = await MC.api.telemetry(s.id);
          return { ...s, telemetry: tl.history.map((h) => h.link) };
        } catch (_) {
          return { ...s, telemetry: [] };
        }
      })
    );

    document.getElementById("fc-count").textContent = `${sats.length} tracked assets`;
    document.getElementById("fc-grid").innerHTML = withTelemetry.map(card).join("");
    const nominal = sats.filter((s) => s.status === "operational").length;
    MC.setFoot(`${nominal}/${sats.length} nominal · last state vector ${MC.fmtUTC(Math.floor(Date.now() / 1000))}`);

    function card(s) {
      return `
        <article class="fleet-card">
          <div class="fleet-card-head">
            <div class="fc-topline">
              <span class="dot ${MC.dotByStatus(s.status)}"></span>
              <span class="fc-name">${MC.esc(s.name)}</span>
              <span class="fc-id">${MC.esc(s.id)}</span>
            </div>
            <span class="fc-orbit">${MC.esc(s.orbit)} · ${MC.esc(s.catalog)}</span>
          </div>

          <div class="fc-metrics">
            ${readout("Link", `${s.linkHealth}%`)}
            ${readout("Battery", `${s.battery}%`)}
            ${readout("Altitude", `${MC.fmtNum(s.altitudeKm)} km`)}
          </div>

          ${spark(s)}

          <div class="fc-instruments">
            ${s.instruments.map((i) => `<span class="inst">${MC.esc(i)}</span>`).join("")}
          </div>

          <div class="fc-status">
            <span>${MC.statusBadge(s.status)}</span>
            <span class="fc-meta">Last pass <span class="cell-mono">${MC.esc(s.lastPass)}</span></span>
          </div>
        </article>`;
    }

    function readout(label, value) {
      return `<div class="readout"><span class="readout-label">${label}</span><span class="readout-value">${value}</span></div>`;
    }

    function spark(s) {
      const values = s.telemetry;
      if (!values || values.length < 2) return "";
      const w = 260;
      const h = 34;
      const pad = 4;
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max - min || 1;
      const stepX = (w - pad * 2) / (values.length - 1);
      const pts = values.map((v, i) => {
        const x = pad + i * stepX;
        const y = h - pad - ((v - min) / span) * (h - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      return `
        <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="Downlink trend">
          <polyline points="${pts.join(" ")}" fill="none"
            stroke="var(--accent)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
            opacity="0.9" />
        </svg>`;
    }
  },
};