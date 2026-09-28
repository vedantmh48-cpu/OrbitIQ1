/* =========================================================================
   views/missions.js — full mission lifecycle: create, command, delete
   ========================================================================= */
"use strict";

const MC = window.MC || (window.MC = {});

MC.views.missions = {
  state: { filter: "all", query: MC.searchQuery || "" },

  async load(root) {
    // consume one-shot search from the topbar
    if (MC.searchQuery) {
      this.state.query = MC.searchQuery;
      MC.searchQuery = "";
      document.getElementById("search-input").value = this.state.query;
    }
    root.innerHTML = `
      <div class="view-stack">
        <div class="missions-toolbar">
          <div class="segmented filter-seg" id="m-filter">
            <button class="seg is-active" data-filter="all">All</button>
            <button class="seg" data-filter="active">Active</button>
            <button class="seg" data-filter="holding">Holding</button>
          </div>
          <div class="grow"></div>
          <input class="toolbar-input" style="width:14rem" id="m-search" placeholder="Filter missions…" />
          <button class="btn btn--solid" id="m-new">＋ New Mission</button>
        </div>
        <section class="card">
          <div class="card-head">
            <h2>Mission manifests</h2>
            <span class="chip chip--accent" id="m-count">…</span>
          </div>
          <div class="card-body" id="m-body">${MC.skeleton(5)}</div>
        </section>
      </div>`;

    MC.setFoot("Loading mission manifests…");
    const missions = await MC.api.missions();
    const sats = await MC.api.satellites();
    this._sats = sats;
    this.render(missions);

    MC.setFoot(`${missions.length} missions · manifest from in-memory mission store`);

    // toolbar wiring (once per load)
    const filter = document.getElementById("m-filter");
    filter.addEventListener("click", (e) => {
      const seg = e.target.closest(".seg");
      if (!seg) return;
      this.state.filter = seg.dataset.filter;
      filter.querySelectorAll(".seg").forEach((s) => s.classList.toggle("is-active", s === seg));
      this.render(missions);
    });
    document.getElementById("m-search").addEventListener("input", (e) => {
      this.state.query = e.target.value.toLowerCase();
      this.render(missions);
    });
    document.getElementById("m-new").addEventListener("click", () => this.openCreate(sats));
    document.getElementById("m-body").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      this.command(btn.dataset.act, btn.dataset.id, missions);
    });
  },

  render(missions) {
    const q = this.state.query;
    const list = missions.filter((m) => {
      if (this.state.filter === "active") {
        if (m.status !== "in-progress" && m.status !== "holding" && m.status !== "queued") return false;
      } else if (this.state.filter === "holding") {
        if (m.status !== "holding") return false;
      }
      if (q) {
        const hay = `${m.name} ${m.code} ${m.satellite} ${m.region} ${m.target}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    document.getElementById("m-count").textContent = activeLabel(missions);
    const body = document.getElementById("m-body");
    if (!list.length) {
      body.innerHTML = `<div class="empty-state"><p class="empty-title">No missions match</p><p>Adjust the filter or create a new mission.</p></div>`;
      return;
    }
    body.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Code</th><th>Mission</th><th>Satellite</th><th>Status</th>
              <th>Progress</th><th>ETA</th><th style="text-align:right">Command</th>
            </tr>
          </thead>
          <tbody>${list.map(row).join("")}</tbody>
        </table>
      </div>`;

    function activeLabel(all) {
      const active = all.filter((m) => m.status === "in-progress" || m.status === "holding" || m.status === "queued").length;
      return `${list.filter((m) => m.status === "in-progress" || m.status === "holding" || m.status === "queued").length} active · ${all.length} total`;
    }

    function row(m) {
      return `
        <tr class="mission-row">
          <td class="cell-mono">${MC.esc(m.code)}</td>
          <td>
            <div class="mission-name">
              <span class="m-title">${MC.esc(m.name)}</span>
              <span class="m-meta">${MC.esc(m.region)} · ${MC.esc(m.target)}</span>
            </div>
          </td>
          <td class="cell-mono">${MC.esc(m.satellite)}</td>
          <td>${MC.statusBadge(m.status)}</td>
          <td>
            <div class="progress-in-cell">
              <div class="progress" style="flex:1"><span class="progress-fill" style="width:${m.progress}%"></span></div>
              <span class="pct">${m.progress}%</span>
            </div>
          </td>
          <td class="cell-mono tone-dim">${MC.esc(m.eta)}</td>
          <td style="text-align:right"><div class="row-actions">${actions(m)}</div></td>
        </tr>`;
    }

    function actions(m) {
      const s = m.status;
      const act = (name, label, extra = "") =>
        `<button class="btn btn--sm ${extra}" data-act="${name}" data-id="${m.id}" title="${label}">${label}</button>`;
      let buttons = "";
      if (s === "planned" || s === "queued") buttons += act("start", "Start", "btn--ok");
      if (s === "in-progress") {
        buttons += act("hold", "Hold", "btn--warn");
        buttons += act("complete", "Complete", "btn--ok");
      } else if (s === "holding") {
        buttons += act("resume", "Resume", "btn--ok");
        buttons += act("complete", "Complete", "btn--ok");
      }
      if (s !== "completed" && s !== "aborted") buttons += act("abort", "Abort", "btn--danger");
      buttons += act("delete", "Delete", "btn--ghost");
      return buttons;
    }
  },

  async command(name, id) {
    const patches = {
      start: { status: "in-progress", phase: "Executing · go for pass" },
      hold: { status: "holding", phase: "Holding · link margin low" },
      resume: { status: "in-progress", phase: "Resumed by console" },
      complete: { status: "completed", progress: 100, phase: "Completed · data delivered" },
      abort: { status: "aborted", phase: "Aborted by console" },
    };
    try {
      if (name === "delete") {
        await MC.api.deleteMission(id);
        MC.toast("Mission removed", "warn");
      } else {
        const patch = patches[name];
        if (!patch) return;
        const updated = await MC.api.updateMission(id, patch);
        MC.toast(`Mission ${updated.code} → ${patch.status}`, "ok");
      }
      await MC.refreshView();
    } catch (err) {
      MC.toast(`Command failed: ${err.message}`, "danger");
    }
  },

  openCreate(sats) {
    MC.modal(`
      <div class="modal-head">
        <h3>Schedule new mission</h3>
        <button class="icon-btn" data-close aria-label="Close">✕</button>
      </div>
      <form id="m-form" style="margin-top:1rem">
        <div class="form-grid">
          <div class="field field--full">
            <label for="m-name">Mission name</label>
            <input id="m-name" name="name" required minlength="2" placeholder="e.g. Coastal Flood Watch" />
          </div>
          <div class="field">
            <label for="m-sat">Satellite</label>
            <select id="m-sat" name="satellite" required>
              ${sats.map((s) => `<option value="${MC.esc(s.name)}">${MC.esc(s.name)} (${MC.esc(s.id)})</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="m-priority">Priority</label>
            <select id="m-priority" name="priority">
              <option value="low">Low</option>
              <option value="normal" selected>Normal</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div class="field">
            <label for="m-target">Target</label>
            <input id="m-target" name="target" placeholder="Sector / ground feature" />
          </div>
          <div class="field">
            <label for="m-region">Region</label>
            <input id="m-region" name="region" placeholder="e.g. Pacific Sector" />
          </div>
          <div class="field field--full">
            <label for="m-objective">Objective</label>
            <textarea id="m-objective" name="objective" placeholder="What should this pass deliver?"></textarea>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn" data-close>Cancel</button>
          <button type="submit" class="btn btn--solid">Create mission</button>
        </div>
      </form>`);
    document.querySelectorAll("[data-close]").forEach((b) =>
      b.addEventListener("click", () => MC.closeModal())
    );
    const form = document.getElementById("m-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = Object.fromEntries(new FormData(form));
      try {
        const created = await MC.api.createMission(payload);
        MC.closeModal();
        MC.toast(`Mission ${created.code} created`, "ok");
        await MC.refreshView();
      } catch (err) {
        MC.toast(`Create failed: ${err.message}`, "danger");
      }
    });
  },
};