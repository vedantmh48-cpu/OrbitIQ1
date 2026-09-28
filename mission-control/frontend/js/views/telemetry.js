/* =========================================================================
   views/telemetry.js — live spacecraft telemetry with 2s polling
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views.telemetry = {
  state: { selected: null, timer: null, sats: [] },

  unload() {
    if (this.state.timer) {
      clearInterval(this.state.timer);
      this.state.timer = null;
    }
  },

  async load(root) {
    root.innerHTML = `
      <div class="view-stack">
        <div class="telemetry-layout">
          <div class="sat-picker" id="tl-picker">
            <p class="nav-label">Select asset</p>
            ${MC.skeleton(6, 34).replace(/skeleton/g, "skeleton card")}
          </div>
          <div class="telemetry-panel">
            <div class="card-head">
              <h2 id="tl-name">—</h2>
              <span class="live-indicator" id="tl-live"><span class="pulse-dot"></span>LIVE · 2s</span>
            </div>
            <div id="tl-chart"><div class="card-body" style="text-align:center">${MC.skeleton(1, 120)}</div></div>
            <div class="telemetry-readouts" id="tl-readouts">${MC.skeleton(2, 40).replace(/skeleton/g, "skeleton card")}</div>
            <p class="progress-track" id="tl-sampled" style="align-items:center"><span>Awaiting first sample…</span></p>
          </div>
        </div>
      </div>`;
    MC.setFoot("Opening downlink to flight bus…");

    const sats = await MC.api.satellites();
    this.state.sats = sats;
    const prefer = MC.views.telemetry.state.selected || sats[0].id;
    this.state.selected = prefer;
    renderPicker(sats);
    await fetchAndRender(prefer);

    this.state.timer = setInterval(() => fetchAndRender(this.state.selected), 2000);
    MC.views.telemetry.state.timer = this.state.timer;

    function renderPicker(sats) {
      document.getElementById("tl-picker").innerHTML = `
        <p class="nav-label">Select asset</p>
        ${sats.map((s) => `
          <button class="sat-opt ${s.id === MC.views.telemetry.state.selected ? "is-active" : ""}" data-id="${s.id}">
            <span>${MC.esc(s.name)}</span>
            <span class="so-id">${MC.esc(s.id)}</span>
          </button>`).join("")}`;
      document.getElementById("tl-picker").addEventListener("click", (e) => {
        const btn = e.target.closest(".sat-opt");
        if (!btn) return;
        MC.views.telemetry.state.selected = btn.dataset.id;
        document.querySelectorAll(".sat-opt").forEach((o) => o.classList.toggle("is-active", o === btn));
        fetchAndRender(btn.dataset.id);
      });
    }

    async function fetchAndRender(id) {
      try {
        const snap = await MC.api.telemetry(id);
        renderPanel(snap);
      } catch (err) {
        MC.toast(`Telemetry: ${err.message}`, "danger");
      }
    }

    function renderPanel(snap) {
      document.getElementById("tl-name").textContent = `${snap.satellite} · downlink telemetry`;
      const c = snap.current;

      document.getElementById("tl-chart").innerHTML =
        MC.chartSVG(snap.history.map((h) => h.link), { label: `link Mbps · ${c.link} Mbps now` });

      document.getElementById("tl-readouts").innerHTML = [
        ro("Downlink", `${c.link} Mbps`, ""),
        ro("Battery", `${c.battery}%`, batteryTone(c.battery)),
        ro("Bus temp", `${c.temp} °C`, tempTone(c.temp)),
        ro("Signal", `${c.signal} dBm`, c.signal > -75 ? "tone-ok" : c.signal < -88 ? "tone-danger" : "tone-warn"),
        ro("Altitude", `${MC.fmtNum(c.altitude)} km`, ""),
        ro("Pass data", `${MC.fmtNum(c.data)} MB`, ""),
      ].join("");

      document.getElementById("tl-sampled").innerHTML = `
        <span class="dot dot--ok" style="width:.5rem;height:.5rem;border-radius:999px"></span>
        <span>Sampled <time class="cell-mono">${MC.fmtUTC(c.t)}</time> · ${snap.history.length} samples buffered</span>`;

      function ro(label, value, tone) {
        return `<div class="readout"><span class="readout-label">${label}</span><span class="readout-value">${value}</span></div>`;
      }
    }
  },
};

function batteryTone(v) {
  if (v <= 25) return "tone-danger";
  if (v <= 45) return "tone-warn";
  return "tone-ok";
}
function tempTone(v) {
  if (v <= 8 || v >= 42) return "tone-danger";
  if (v <= 14 || v >= 34) return "tone-warn";
  return "tone-ok";
}