/* ------------------------------------------------------------------ *
 *  Horaire — schedule editor client
 * ------------------------------------------------------------------ */
(() => {
  "use strict";

  const API = "/editor/api";
  const TINTS = 8;

  const state = {
    session: null,
    data: null,
    dayStartMin: 8 * 60,
    dayEndMin: 22 * 60,
    snap: 15,
    minDuration: 30,
    days: [],
    pxPerMin: 1.08,
    busy: false,
    selectedCourseId: null,
  };

  const el = {
    sessionSelect: document.getElementById("sessionSelect"),
    dayHeads: document.getElementById("dayHeads"),
    gutter: document.getElementById("gutter"),
    grid: document.getElementById("grid"),
    board: document.getElementById("board"),
    trashList: document.getElementById("trashList"),
    trashCount: document.getElementById("trashCount"),
    undoBtn: document.getElementById("undoBtn"),
    redoBtn: document.getElementById("redoBtn"),
    resetBtn: document.getElementById("resetBtn"),
    addBtn: document.getElementById("addBtn"),
    statusText: document.getElementById("statusText"),
    statusDot: document.getElementById("statusDot"),
    addModal: document.getElementById("addModal"),
    addForm: document.getElementById("addForm"),
    catalogList: document.getElementById("catalogList"),
    fJour: document.getElementById("fJour"),
    fSigle: document.getElementById("fSigle"),
    fTitre: document.getElementById("fTitre"),
    toast: document.getElementById("toast"),
  };

  /* ---------------------------- helpers --------------------------- */
  const toMin = (hhmm) => {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  };
  const toHHMM = (min) => {
    min = Math.max(0, Math.round(min));
    const h = Math.floor(min / 60);
    const m = min % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  };
  const snap = (min) => Math.round(min / state.snap) * state.snap;
  const totalMin = () => state.dayEndMin - state.dayStartMin;
  const minToPx = (min) => (min - state.dayStartMin) * state.pxPerMin;
  const durToPx = (min) => min * state.pxPerMin;

  const tintFor = (sigle) => {
    let h = 0;
    for (let i = 0; i < sigle.length; i++) h = (h * 31 + sigle.charCodeAt(i)) >>> 0;
    return h % TINTS;
  };

  function setStatus(text, busy) {
    el.statusText.textContent = text;
    state.busy = !!busy;
    el.statusDot.classList.toggle("is-busy", !!busy);
  }

  let toastTimer = null;
  function toast(msg, isError) {
    el.toast.textContent = msg;
    el.toast.classList.toggle("is-error", !!isError);
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.toast.hidden = true), 2600);
  }

  /* ------------------------------ api ----------------------------- */
  async function apiGet(session) {
    const res = await fetch(`${API}/state?session=${encodeURIComponent(session)}`);
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    return res.json();
  }
  async function apiPost(path, body) {
    setStatus("Enregistrement…", true);
    try {
      const res = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
      applyState(data);
      setStatus("Enregistré.", false);
      return data;
    } catch (err) {
      setStatus("Erreur.", false);
      toast(err.message || "Échec de l'opération", true);
      throw err;
    }
  }

  /* --------------------------- rendering -------------------------- */
  function applyState(data, opts) {
    state.session = data.session;
    state.data = data;
    const meta = data.meta;
    state.dayStartMin = toMin(meta.dayStart);
    state.dayEndMin = toMin(meta.dayEnd);
    state.snap = meta.snapMin;
    state.minDuration = meta.minDuration;
    state.days = meta.days;
    renderSessions(data);
    renderScaffold();
    renderBlocks(opts && opts.animate);
    renderTrash(data.trash);
    renderCatalog(meta.catalog);
    el.undoBtn.disabled = !data.canUndo;
    el.redoBtn.disabled = !data.canRedo;
  }

  function renderSessions(data) {
    if (el.sessionSelect.dataset.filled === "1" && el.sessionSelect.value === data.session)
      return;
    el.sessionSelect.innerHTML = "";
    data.sessions.forEach((code) => {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = code;
      if (code === data.session) opt.selected = true;
      el.sessionSelect.appendChild(opt);
    });
    el.sessionSelect.dataset.filled = "1";
  }

  function renderScaffold() {
    // Day headers
    el.dayHeads.innerHTML = "";
    state.days.forEach((d) => {
      const h = document.createElement("div");
      h.className = "dayhead";
      h.innerHTML = `<span class="dayhead__short">${d.short}</span><span class="dayhead__name">${d.name}</span>`;
      el.dayHeads.appendChild(h);
    });

    const height = durToPx(totalMin());

    // Hour gutter
    el.gutter.innerHTML = "";
    el.gutter.style.height = `${height}px`;
    for (let m = state.dayStartMin; m <= state.dayEndMin; m += 30) {
      const label = document.createElement("div");
      const onHour = m % 60 === 0;
      label.className = "hourlabel" + (onHour ? " hourlabel--on" : "");
      label.style.top = `${minToPx(m)}px`;
      label.textContent = toHHMM(m);
      el.gutter.appendChild(label);
    }

    // Day columns with gridlines
    el.grid.innerHTML = "";
    el.grid.style.height = `${height}px`;
    state.days.forEach((d) => {
      const col = document.createElement("div");
      col.className = "daycol";
      col.dataset.jour = d.jour;
      const lines = document.createElement("div");
      lines.className = "daycol__lines";
      for (let m = state.dayStartMin; m <= state.dayEndMin; m += 30) {
        const line = document.createElement("div");
        const onHour = m % 60 === 0;
        line.className = "gridline " + (onHour ? "gridline--hour" : "gridline--half");
        line.style.top = `${minToPx(m)}px`;
        lines.appendChild(line);
      }
      col.appendChild(lines);
      el.grid.appendChild(col);
    });
  }

  function columnFor(jour) {
    return el.grid.querySelector(`.daycol[data-jour="${jour}"]`);
  }

  function renderBlocks(animate) {
    document.querySelectorAll(".block").forEach((b) => b.remove());
    let count = 0;
    let selectionAlive = false;
    (state.data.blocks || []).forEach((blk) => {
      const col = columnFor(blk.jour);
      if (!col) return;
      const node = buildBlock(blk, animate);
      if (blk.courseId === state.selectedCourseId) {
        node.classList.add("is-selected");
        selectionAlive = true;
      }
      col.appendChild(node);
      count++;
    });
    if (!selectionAlive) state.selectedCourseId = null;
    renderEmpty(count === 0);
  }

  function selectCourse(courseId) {
    state.selectedCourseId = courseId;
    document.querySelectorAll(".block").forEach((n) =>
      n.classList.toggle("is-selected", n.dataset.courseId === courseId)
    );
  }

  function renderEmpty(isEmpty) {
    const existing = el.board.querySelector(".board__empty");
    if (existing) existing.remove();
    if (!isEmpty) return;
    const div = document.createElement("div");
    div.className = "board__empty";
    div.innerHTML = `<p>Aucun cours cette session — ajoutez-en un.</p>`;
    el.board.appendChild(div);
  }

  function buildBlock(blk, animate) {
    const start = toMin(blk.heureDebut);
    const end = toMin(blk.heureFin);
    const dur = end - start;
    const node = document.createElement("div");
    node.className = "block" + (blk.kind === "labo" ? " is-labo" : "");
    if (animate) node.classList.add("is-entering");
    if (dur <= 60) node.classList.add("is-compact");
    const t = tintFor(blk.sigle);
    node.style.setProperty("--bg", `var(--c${t}-bg)`);
    node.style.setProperty("--bd", `var(--c${t}-bd)`);
    node.style.setProperty("--tx", `var(--c${t}-tx)`);
    node.style.top = `${minToPx(start)}px`;
    node.style.height = `${durToPx(dur) - 3}px`;
    node.dataset.blockId = blk.id;
    node.dataset.courseId = blk.courseId;
    node.dataset.jour = blk.jour;
    node.dataset.start = start;
    node.dataset.dur = dur;

    const kindLabel = blk.kind === "labo" ? "Labo" : "";
    node.innerHTML = `
      <div class="block__handle block__handle--top"></div>
      <div class="block__inner">
        <div class="block__sigle">${blk.sigle}<span class="block__grp">gr ${blk.groupe}${kindLabel ? " · " + kindLabel : ""}</span></div>
        <div class="block__title">${escapeHtml(blk.titre)}</div>
        <div class="block__meta"><span>${blk.heureDebut}–${blk.heureFin}</span><span>${blk.room || ""}</span></div>
      </div>
      <button class="block__del" title="Supprimer le cours">×</button>
      <div class="block__tag">${blk.heureDebut}</div>
      <div class="block__handle block__handle--bottom"></div>`;

    node.querySelector(".block__del").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteCourse(blk.courseId);
    });
    attachDrag(node, blk);
    return node;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }

  function renderTrash(trash) {
    el.trashCount.textContent = trash.length;
    el.trashList.innerHTML = "";
    if (!trash.length) {
      const li = document.createElement("li");
      li.className = "trash__empty";
      li.textContent = "Vide — rien de supprimé.";
      el.trashList.appendChild(li);
      return;
    }
    trash.forEach((c) => {
      const li = document.createElement("li");
      li.className = "trash__item";
      li.innerHTML = `
        <div class="trash__meta">
          <div class="trash__sigle">${c.sigle} · ${c.groupe}</div>
          <div class="trash__title">${escapeHtml(c.titre)}</div>
        </div>
        <button class="trash__restore">Restaurer</button>`;
      li.querySelector(".trash__restore").addEventListener("click", () =>
        apiPost("/course/restore", { session: state.session, courseId: c.courseId }).then(
          () => toast(`${c.sigle} restauré`)
        )
      );
      el.trashList.appendChild(li);
    });
  }

  let catalogFilled = false;
  function renderCatalog(catalog) {
    if (catalogFilled) return;
    el.catalogList.innerHTML = "";
    catalog.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.sigle;
      opt.label = c.titre;
      el.catalogList.appendChild(opt);
    });
    el.fJour.innerHTML = "";
    state.days.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.jour;
      opt.textContent = d.name;
      el.fJour.appendChild(opt);
    });
    catalogFilled = true;
    state.catalog = catalog;
  }

  /* --------------------- drag & resize engine --------------------- */
  function attachDrag(node, blk) {
    const topH = node.querySelector(".block__handle--top");
    const botH = node.querySelector(".block__handle--bottom");
    node.addEventListener("pointerdown", (e) => {
      if (e.target.classList.contains("block__del")) return;
      if (e.target === topH) return startGesture(e, node, blk, "resize-top");
      if (e.target === botH) return startGesture(e, node, blk, "resize-bottom");
      startGesture(e, node, blk, "move");
    });
  }

  function startGesture(e, node, blk, mode) {
    if (state.busy) return;
    e.preventDefault();
    node.setPointerCapture(e.pointerId);

    const gridRect = el.grid.getBoundingClientRect();
    const colWidth = gridRect.width / state.days.length;
    const startMin0 = Number(node.dataset.start);
    const dur0 = Number(node.dataset.dur);
    const startY = e.clientY;
    const startX = e.clientX;
    let moved = false;
    let cur = { jour: blk.jour, start: startMin0, dur: dur0 };
    const tag = node.querySelector(".block__tag");

    node.classList.add("is-dragging");

    const onMove = (ev) => {
      const dy = ev.clientY - startY;
      const dMin = dy / state.pxPerMin;
      if (Math.abs(dy) > 2 || Math.abs(ev.clientX - startX) > 2) moved = true;

      if (mode === "move") {
        let ns = snap(startMin0 + dMin);
        ns = Math.max(state.dayStartMin, Math.min(ns, state.dayEndMin - dur0));
        // Which column is the pointer over?
        let idx = Math.floor((ev.clientX - gridRect.left) / colWidth);
        idx = Math.max(0, Math.min(idx, state.days.length - 1));
        const jour = state.days[idx].jour;
        cur = { jour, start: ns, dur: dur0 };
        placeInColumn(node, jour);
        node.style.top = `${minToPx(ns)}px`;
        highlightColumn(jour);
        tag.textContent = `${state.days[idx].short} ${toHHMM(ns)}`;
      } else if (mode === "resize-bottom") {
        let ne = snap(startMin0 + dur0 + dMin);
        ne = Math.min(state.dayEndMin, Math.max(ne, startMin0 + state.minDuration));
        cur.dur = ne - startMin0;
        node.style.height = `${durToPx(cur.dur) - 3}px`;
        tag.textContent = `${toHHMM(startMin0)}–${toHHMM(ne)}`;
      } else if (mode === "resize-top") {
        let ns = snap(startMin0 + dMin);
        ns = Math.max(state.dayStartMin, Math.min(ns, startMin0 + dur0 - state.minDuration));
        cur.start = ns;
        cur.dur = startMin0 + dur0 - ns;
        node.style.top = `${minToPx(ns)}px`;
        node.style.height = `${durToPx(cur.dur) - 3}px`;
        tag.textContent = `${toHHMM(ns)}–${toHHMM(startMin0 + dur0)}`;
      }
    };

    const onUp = () => {
      node.releasePointerCapture(e.pointerId);
      node.removeEventListener("pointermove", onMove);
      node.removeEventListener("pointerup", onUp);
      node.classList.remove("is-dragging");
      clearHighlight();

      const changed =
        cur.jour !== blk.jour ||
        cur.start !== startMin0 ||
        cur.dur !== dur0;
      if (!moved || !changed) {
        renderBlocks(false); // snap back
        if (!moved) selectCourse(blk.courseId);
        return;
      }
      commitGesture(mode, blk, cur);
    };

    node.addEventListener("pointermove", onMove);
    node.addEventListener("pointerup", onUp);
    node.addEventListener("pointercancel", onUp);
  }

  function placeInColumn(node, jour) {
    if (node.dataset.jour === String(jour)) return;
    const col = columnFor(jour);
    if (col) {
      col.appendChild(node);
      node.dataset.jour = jour;
    }
  }
  function highlightColumn(jour) {
    clearHighlight();
    const col = columnFor(jour);
    if (col) col.classList.add("daycol--drop");
  }
  function clearHighlight() {
    document.querySelectorAll(".daycol--drop").forEach((c) => c.classList.remove("daycol--drop"));
  }

  function commitGesture(mode, blk, cur) {
    if (mode === "move") {
      apiPost("/block/move", {
        session: state.session,
        blockId: blk.id,
        jour: cur.jour,
        heureDebut: toHHMM(cur.start),
      });
    } else {
      apiPost("/block/resize", {
        session: state.session,
        blockId: blk.id,
        heureDebut: toHHMM(cur.start),
        heureFin: toHHMM(cur.start + cur.dur),
      });
    }
  }

  /* --------------------------- actions ---------------------------- */
  function deleteCourse(courseId) {
    apiPost("/course/delete", { session: state.session, courseId }).then(() =>
      toast("Cours déplacé vers la corbeille")
    );
  }

  async function loadSession(session, animate) {
    setStatus("Chargement…", true);
    try {
      const data = await apiGet(session);
      applyState(data, { animate });
      setStatus("Prêt.", false);
    } catch (err) {
      setStatus("Erreur.", false);
      toast(err.message, true);
    }
  }

  /* ---------------------------- modal ----------------------------- */
  function openModal() {
    el.addModal.hidden = false;
    el.fSigle.value = "";
    el.fTitre.value = "";
    setTimeout(() => el.fSigle.focus(), 30);
  }
  function closeModal() {
    el.addModal.hidden = true;
  }

  el.fSigle.addEventListener("input", () => {
    const match = (state.catalog || []).find(
      (c) => c.sigle.toLowerCase() === el.fSigle.value.trim().toLowerCase()
    );
    if (match && !el.fTitre.value) el.fTitre.value = match.titre;
  });

  el.addForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(el.addForm);
    const body = {
      session: state.session,
      sigle: fd.get("sigle"),
      titre: fd.get("titre"),
      jour: fd.get("jour"),
      heureDebut: fd.get("heureDebut"),
      heureFin: fd.get("heureFin"),
      kind: fd.get("kind"),
    };
    apiPost("/course/add", body).then(() => {
      closeModal();
      toast(`${body.sigle.toUpperCase()} ajouté`);
    });
  });

  el.addModal.querySelectorAll("[data-close]").forEach((n) =>
    n.addEventListener("click", closeModal)
  );

  /* --------------------------- wiring ----------------------------- */
  el.sessionSelect.addEventListener("change", (e) => loadSession(e.target.value, true));
  el.addBtn.addEventListener("click", openModal);
  el.undoBtn.addEventListener("click", () =>
    apiPost("/undo", { session: state.session })
  );
  el.redoBtn.addEventListener("click", () =>
    apiPost("/redo", { session: state.session })
  );
  el.resetBtn.addEventListener("click", () => {
    if (confirm("Réinitialiser cette session à son horaire d'origine ?"))
      apiPost("/reset", { session: state.session }).then(() =>
        toast("Session réinitialisée")
      );
  });

  document.addEventListener("keydown", (e) => {
    if (!el.addModal.hidden && e.key === "Escape") return closeModal();
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) {
        if (!el.redoBtn.disabled) el.redoBtn.click();
      } else if (!el.undoBtn.disabled) el.undoBtn.click();
    } else if (mod && e.key.toLowerCase() === "y") {
      e.preventDefault();
      if (!el.redoBtn.disabled) el.redoBtn.click();
    } else if ((e.key === "Delete" || e.key === "Backspace") && !typing) {
      if (state.selectedCourseId) {
        e.preventDefault();
        deleteCourse(state.selectedCourseId);
      }
    } else if (e.key === "Escape") {
      selectCourse(null);
    }
  });

  el.board.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".block")) selectCourse(null);
  });

  window.addEventListener("resize", () => {
    if (state.data) renderBlocks(false);
  });

  /* ----------------------------- boot ----------------------------- */
  (async () => {
    try {
      const data = await apiGet("");
      applyState(data, { animate: true });
      if (!state.data.blocks.length && !data.sessions.length) {
        setStatus("Aucune session avec des cours.", false);
      } else {
        setStatus("Prêt.", false);
      }
    } catch (err) {
      setStatus("Impossible de contacter le serveur.", false);
      toast(err.message || "Serveur injoignable", true);
    }
  })();
})();
