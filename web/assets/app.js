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
    semester: null,
    weekIndex: null,
    editScope: "series",
  };

  const el = {
    sessionSelect: document.getElementById("sessionSelect"),
    scopeToggle: document.getElementById("scopeToggle"),
    weekPicker: document.getElementById("weekPicker"),
    weekSelect: document.getElementById("weekSelect"),
    weekPrev: document.getElementById("weekPrev"),
    weekNext: document.getElementById("weekNext"),
    weekToday: document.getElementById("weekToday"),
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

  const MONTHS_FR = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
  ];
  const todayISO = () => {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
  };
  const fmtDayDate = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return `${d} ${MONTHS_FR[m - 1]}`;
  };

  function currentWeek() {
    if (!state.semester) return null;
    return (
      state.semester.weeks.find((w) => w.index === state.weekIndex) || null
    );
  }
  function weekExists(index) {
    return !!state.semester && state.semester.weeks.some((w) => w.index === index);
  }
  function todayWeekIndex(semester) {
    if (!semester || !semester.weeks.length) return null;
    const today = todayISO();
    for (const w of semester.weeks) {
      // Week spans its Monday (w.start) through the following Sunday.
      const monday = new Date(w.start + "T00:00:00");
      const sunday = new Date(monday.getTime() + 6 * 864e5)
        .toISOString()
        .slice(0, 10);
      if (today >= w.start && today <= sunday) return w.index;
    }
    return null;
  }
  function defaultWeekIndex(semester) {
    if (!semester || !semester.weeks.length) return null;
    const today = todayWeekIndex(semester);
    return today != null ? today : semester.weeks[0].index;
  }

  const occurrenceMode = () => state.editScope === "occurrence" && !!currentWeek();

  // The date the recurring pattern would produce for a block in the current week.
  function anchorFor(blk) {
    const week = currentWeek();
    return week && week.dates ? week.dates[blk.jour] : null;
  }

  // Where a block actually sits in the selected week (applying any override).
  function effectiveForWeek(blk) {
    const anchor = anchorFor(blk);
    const ov =
      anchor && blk.occurrences
        ? blk.occurrences.find((o) => o.date === anchor)
        : null;
    if (ov && ov.canceled) {
      return {
        anchor,
        canceled: true,
        jour: blk.jour,
        heureDebut: blk.heureDebut,
        heureFin: blk.heureFin,
      };
    }
    if (ov) {
      return {
        anchor,
        overridden: true,
        jour: ov.jour,
        heureDebut: ov.heureDebut,
        heureFin: ov.heureFin,
      };
    }
    return {
      anchor,
      jour: blk.jour,
      heureDebut: blk.heureDebut,
      heureFin: blk.heureFin,
    };
  }

  function setStatus(text, busy) {
    el.statusText.textContent = text;
    state.busy = !!busy;
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
    const prevSession = state.session;
    state.session = data.session;
    state.data = data;
    const meta = data.meta;
    state.dayStartMin = toMin(meta.dayStart);
    state.dayEndMin = toMin(meta.dayEnd);
    state.snap = meta.snapMin;
    state.minDuration = meta.minDuration;
    state.days = meta.days;
    state.semester = meta.semester || null;
    if (
      prevSession !== data.session ||
      state.weekIndex == null ||
      !weekExists(state.weekIndex)
    ) {
      state.weekIndex = defaultWeekIndex(state.semester);
    }
    renderSessions(data);
    renderWeekPicker();
    renderScaffold();
    renderBlocks(opts && opts.animate);
    renderTrash(data.trash);
    renderCatalog(meta.catalog);
    el.undoBtn.disabled = !data.canUndo;
    el.redoBtn.disabled = !data.canRedo;
  }

  function renderWeekPicker() {
    const semester = state.semester;
    const occBtn = el.scopeToggle.querySelector('[data-scope="occurrence"]');
    if (!semester || !semester.weeks.length) {
      el.weekPicker.hidden = true;
      if (occBtn) occBtn.disabled = true;
      if (state.editScope === "occurrence") setScope("series");
      return;
    }
    if (occBtn) occBtn.disabled = false;
    el.weekPicker.hidden = false;
    el.weekSelect.innerHTML = "";
    semester.weeks.forEach((w) => {
      const opt = document.createElement("option");
      opt.value = String(w.index);
      opt.textContent = `S${w.index} · ${w.range}`;
      if (w.index === state.weekIndex) opt.selected = true;
      el.weekSelect.appendChild(opt);
    });
    const first = semester.weeks[0].index;
    const last = semester.weeks[semester.weeks.length - 1].index;
    el.weekPrev.disabled = state.weekIndex <= first;
    el.weekNext.disabled = state.weekIndex >= last;
    // "Today" jumps back to the current week; only show it when today falls
    // within the semester and we're not already viewing that week.
    const todayIdx = todayWeekIndex(semester);
    el.weekToday.hidden = todayIdx == null || todayIdx === state.weekIndex;
    sizeWeekSelect();
  }

  // A native <select> is as wide as its longest option. Size it to the widest
  // week label so the width stays constant as you navigate — otherwise the
  // ‹ / › buttons shift and you have to re-aim the mouse.
  function sizeWeekSelect() {
    const sel = el.weekSelect;
    if (!sel.options.length) return;
    const cs = getComputedStyle(sel);
    const canvas = sizeWeekSelect._c || (sizeWeekSelect._c = document.createElement("canvas"));
    const ctx = canvas.getContext("2d");
    ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    let textW = 0;
    for (const opt of sel.options) {
      textW = Math.max(textW, ctx.measureText(opt.textContent).width);
    }
    const padL = parseFloat(cs.paddingLeft) || 0;
    const padR = parseFloat(cs.paddingRight) || 0;
    const bord = (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0);
    sel.style.width = `${Math.ceil(textW + padL + padR + bord + 2)}px`;
  }

  function selectWeek(index) {
    if (!weekExists(index)) return;
    state.weekIndex = index;
    renderWeekPicker();
    renderScaffold();
    renderBlocks(false);
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
    fitPxPerMin();
    const week = currentWeek();
    const today = todayISO();
    // Day headers
    el.dayHeads.innerHTML = "";
    state.days.forEach((d) => {
      const h = document.createElement("div");
      h.className = "dayhead";
      const iso = week && week.dates ? week.dates[d.jour] : null;
      if (iso === today) h.classList.add("dayhead--today");
      const dateHtml = iso
        ? `<span class="dayhead__date">${fmtDayDate(iso)}</span>`
        : "";
      h.innerHTML = `<span class="dayhead__name">${d.name}</span>${dateHtml}`;
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
      const iso = week && week.dates ? week.dates[d.jour] : null;
      if (iso === today) col.classList.add("daycol--today");
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

  // Scale the grid so the whole day fits the board without vertical scroll.
  function fitPxPerMin() {
    const boardH = el.board.clientHeight;
    const total = totalMin();
    if (boardH <= 0 || total <= 0) return;
    const headH =
      parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--day-head-h"),
        10
      ) || 60;
    // Leave room for the last hour label, which is vertically centred on the
    // bottom gridline and therefore overhangs the grid by half its height.
    const avail = boardH - headH - 14;
    if (avail > 0) state.pxPerMin = Math.max(0.5, avail / total);
  }

  function renderBlocks(animate) {
    document.querySelectorAll(".block").forEach((b) => b.remove());
    let count = 0;
    let selectionAlive = false;
    const occMode = occurrenceMode();
    el.board.classList.toggle("is-occurrence", occMode);

    // Group visible blocks by day so overlapping ones can be laid out
    // side by side instead of stacking on top of each other.
    const byDay = new Map();
    (state.data.blocks || []).forEach((blk) => {
      const eff = effectiveForWeek(blk);
      const col = columnFor(eff.jour);
      if (!col) return;
      const start = toMin(eff.heureDebut);
      const end = toMin(eff.heureFin);
      const item = { blk, eff, col, start, end, lane: 0, lanes: 1 };
      if (!byDay.has(eff.jour)) byDay.set(eff.jour, []);
      byDay.get(eff.jour).push(item);
    });

    byDay.forEach((items) => {
      assignLanes(items);
      items.forEach((it) => {
        const node = buildBlock(it.blk, it.eff, animate, occMode);
        if (it.lanes > 1) applyLaneLayout(node, it.lane, it.lanes);
        if (it.blk.courseId === state.selectedCourseId) {
          node.classList.add("is-selected");
          selectionAlive = true;
        }
        it.col.appendChild(node);
        count++;
      });
    });

    if (!selectionAlive) state.selectedCourseId = null;
    renderEmpty(count === 0);
  }

  // Assign each block a horizontal lane within its day. Blocks whose times
  // overlap form a cluster and are split across as many lanes as needed.
  function assignLanes(items) {
    items.sort((a, b) => a.start - b.start || a.end - b.end);
    let cluster = [];
    let clusterEnd = -Infinity;

    const flush = () => {
      if (!cluster.length) return;
      const colEnds = [];
      cluster.forEach((it) => {
        let placed = false;
        for (let c = 0; c < colEnds.length; c++) {
          if (it.start >= colEnds[c]) {
            it.lane = c;
            colEnds[c] = it.end;
            placed = true;
            break;
          }
        }
        if (!placed) {
          it.lane = colEnds.length;
          colEnds.push(it.end);
        }
      });
      const total = colEnds.length;
      cluster.forEach((it) => (it.lanes = total));
      cluster = [];
      clusterEnd = -Infinity;
    };

    items.forEach((it) => {
      if (cluster.length && it.start >= clusterEnd) flush();
      cluster.push(it);
      clusterEnd = Math.max(clusterEnd, it.end);
    });
    flush();
  }

  function applyLaneLayout(node, lane, lanes) {
    const gap = 3;
    node.style.left = `calc(5px + (100% - 10px) * ${lane} / ${lanes})`;
    node.style.width = `calc((100% - 10px) / ${lanes} - ${gap}px)`;
    node.style.right = "auto";
  }

  function clearLaneLayout(node) {
    node.style.left = "";
    node.style.width = "";
    node.style.right = "";
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
    div.innerHTML = `<p>Aucun cours cette session, ajoutez-en un.</p>`;
    el.board.appendChild(div);
  }

  function buildBlock(blk, eff, animate, occMode) {
    const start = toMin(eff.heureDebut);
    const end = toMin(eff.heureFin);
    const dur = end - start;
    const node = document.createElement("div");
    node.className = "block" + (blk.kind === "labo" ? " is-labo" : "");
    if (animate) node.classList.add("is-entering");
    if (dur <= 60) node.classList.add("is-compact");
    if (eff.canceled) node.classList.add("is-canceled");
    if (eff.overridden) node.classList.add("is-overridden");
    const t = tintFor(blk.sigle);
    node.style.setProperty("--bg", `var(--c${t}-bg)`);
    node.style.setProperty("--bd", `var(--c${t}-bd)`);
    node.style.setProperty("--tx", `var(--c${t}-tx)`);
    node.style.top = `${minToPx(start)}px`;
    node.style.height = `${durToPx(dur) - 3}px`;
    node.dataset.blockId = blk.id;
    node.dataset.courseId = blk.courseId;
    node.dataset.jour = eff.jour;
    node.dataset.start = start;
    node.dataset.dur = dur;
    if (eff.anchor) node.dataset.anchor = eff.anchor;

    const kindLabel = blk.kind === "labo" ? "Labo" : "";
    const badge = eff.overridden
      ? `<span class="block__badge" title="Séance modifiée cette semaine">séance</span>`
      : eff.canceled
      ? `<span class="block__badge block__badge--off" title="Séance annulée cette semaine">annulée</span>`
      : "";
    const resetBtn =
      occMode && (eff.overridden || eff.canceled)
        ? `<button class="block__reset" title="Rétablir cette séance au modèle">↺</button>`
        : "";
    const delTitle = eff.canceled
      ? "Restaurer cette séance"
      : occMode
      ? "Annuler cette séance"
      : "Supprimer le cours";

    node.innerHTML = `
      <div class="block__handle block__handle--top"></div>
      <div class="block__inner">
        <div class="block__sigle"><span class="block__code">${blk.sigle}</span><span class="block__grp">gr ${blk.groupe}${kindLabel ? " · " + kindLabel : ""}</span>${badge}</div>
        <div class="block__title">${escapeHtml(blk.titre)}</div>
        <div class="block__meta"><span>${eff.heureDebut}–${eff.heureFin}</span><span>${blk.room || ""}</span></div>
      </div>
      ${resetBtn}
      <button class="block__del" title="${delTitle}">×</button>
      <div class="block__tag">${eff.heureDebut}</div>
      <div class="block__handle block__handle--bottom"></div>`;

    const resetEl = node.querySelector(".block__reset");
    if (resetEl) {
      resetEl.addEventListener("click", (e) => {
        e.stopPropagation();
        resetOccurrence(blk, node.dataset.anchor);
      });
    }
    node.querySelector(".block__del").addEventListener("click", (e) => {
      e.stopPropagation();
      if (eff.canceled) {
        resetOccurrence(blk, node.dataset.anchor);
      } else if (occMode) {
        cancelOccurrence(blk, node.dataset.anchor);
      } else {
        deleteCourse(blk.courseId);
      }
    });
    if (!eff.canceled) attachDrag(node, blk);
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
      li.textContent = "Vide, rien de supprimé.";
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
      if (e.target.classList.contains("block__reset")) return;
      let edge = null;
      if (e.target === topH) edge = "resize-top";
      else if (e.target === botH) edge = "resize-bottom";
      startGesture(e, node, blk, edge);
    });
  }

  // `resizeEdge` (from the top/bottom handle) is only a *hint*. The real
  // gesture is resolved on the first meaningful movement: a mostly-horizontal
  // drag is always a move (so grabbing near an edge never blocks dragging to
  // another day), while a mostly-vertical drag on a handle is a resize.
  function startGesture(e, node, blk, resizeEdge) {
    if (state.busy) return;
    e.preventDefault();
    node.setPointerCapture(e.pointerId);

    const gridRect = el.grid.getBoundingClientRect();
    const colWidth = gridRect.width / state.days.length;
    const startMin0 = Number(node.dataset.start);
    const dur0 = Number(node.dataset.dur);
    const jour0 = node.dataset.jour;
    const origIdx = Math.max(
      0,
      state.days.findIndex((d) => String(d.jour) === String(jour0))
    );
    const anchor0 = node.dataset.anchor || null;
    const startY = e.clientY;
    const startX = e.clientX;
    let moved = false;
    let mode = resizeEdge ? null : "move";
    let cur = { jour: jour0, start: startMin0, dur: dur0 };
    const tag = node.querySelector(".block__tag");

    node.classList.add("is-dragging");
    // Span the full column while dragging so lane-splitting doesn't interfere.
    clearLaneLayout(node);

    const onMove = (ev) => {
      const dy = ev.clientY - startY;
      const dx = ev.clientX - startX;
      const dMin = dy / state.pxPerMin;
      if (Math.abs(dy) > 2 || Math.abs(dx) > 2) moved = true;

      // Resolve a handle-hint gesture once the drag direction is clear:
      // horizontal intent wins as a move, vertical intent stays a resize.
      if (mode === null) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 5) return;
        mode = Math.abs(dx) > Math.abs(dy) ? "move" : resizeEdge;
      }


      if (mode === "move") {
        let ns = snap(startMin0 + dMin);
        ns = Math.max(state.dayStartMin, Math.min(ns, state.dayEndMin - dur0));
        // Which column is the pointer over?
        let idx = Math.floor((ev.clientX - gridRect.left) / colWidth);
        idx = Math.max(0, Math.min(idx, state.days.length - 1));
        const jour = state.days[idx].jour;
        cur = { jour, start: ns, dur: dur0 };
        // Translate across columns instead of re-parenting: re-parenting a
        // node with pointer capture releases the capture and aborts the drag,
        // which used to make dragging stop at the next weekday.
        node.style.top = `${minToPx(ns)}px`;
        node.style.transform = `translateX(${(idx - origIdx) * colWidth}px)`;
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
        cur.jour !== jour0 ||
        cur.start !== startMin0 ||
        cur.dur !== dur0;
      if (!moved || !changed) {
        renderBlocks(false); // snap back
        if (!moved) selectCourse(blk.courseId);
        return;
      }
      commitGesture(mode, blk, cur, anchor0);
    };

    node.addEventListener("pointermove", onMove);
    node.addEventListener("pointerup", onUp);
    node.addEventListener("pointercancel", onUp);
  }

  function highlightColumn(jour) {
    clearHighlight();
    const col = columnFor(jour);
    if (col) col.classList.add("daycol--drop");
  }
  function clearHighlight() {
    document.querySelectorAll(".daycol--drop").forEach((c) => c.classList.remove("daycol--drop"));
  }

  function commitGesture(mode, blk, cur, anchor) {
    if (occurrenceMode() && anchor) {
      // Edit only the selected week's occurrence.
      const heureDebut = toHHMM(cur.start);
      const heureFin =
        mode === "move"
          ? toHHMM(cur.start + cur.dur)
          : toHHMM(cur.start + cur.dur);
      apiPost("/occurrence/set", {
        session: state.session,
        blockId: blk.id,
        date: anchor,
        jour: cur.jour,
        heureDebut,
        heureFin,
      }).then(() => toast("Séance modifiée cette semaine"));
      return;
    }
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

  function cancelOccurrence(blk, anchor) {
    if (!anchor) return;
    apiPost("/occurrence/cancel", {
      session: state.session,
      blockId: blk.id,
      date: anchor,
    }).then(() => toast("Séance annulée cette semaine"));
  }

  function resetOccurrence(blk, anchor) {
    if (!anchor) return;
    apiPost("/occurrence/reset", {
      session: state.session,
      blockId: blk.id,
      date: anchor,
    }).then(() => toast("Séance rétablie au modèle"));
  }

  function setScope(scope) {
    if (scope !== "series" && scope !== "occurrence") return;
    state.editScope = scope;
    el.scopeToggle.querySelectorAll(".scope__btn").forEach((b) =>
      b.classList.toggle("is-active", b.dataset.scope === scope)
    );
    renderBlocks(false);
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
  el.scopeToggle.querySelectorAll(".scope__btn").forEach((b) =>
    b.addEventListener("click", () => setScope(b.dataset.scope))
  );
  el.weekSelect.addEventListener("change", (e) => {
    sizeWeekSelect();
    selectWeek(Number(e.target.value));
  });
  el.weekPrev.addEventListener("click", () => selectWeek(state.weekIndex - 1));
  el.weekNext.addEventListener("click", () => selectWeek(state.weekIndex + 1));
  el.weekToday.addEventListener("click", () => {
    const idx = todayWeekIndex(state.semester);
    if (idx != null) selectWeek(idx);
  });
  el.addBtn.addEventListener("click", openModal);  el.undoBtn.addEventListener("click", () =>
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
    } else if (e.key === "ArrowLeft" && !typing && !mod) {
      if (!el.weekPrev.disabled) {
        e.preventDefault();
        selectWeek(state.weekIndex - 1);
      }
    } else if (e.key === "ArrowRight" && !typing && !mod) {
      if (!el.weekNext.disabled) {
        e.preventDefault();
        selectWeek(state.weekIndex + 1);
      }
    }
  });

  el.board.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".block")) selectCourse(null);
  });

  window.addEventListener("resize", () => {
    if (state.data) {
      renderScaffold();
      renderBlocks(false);
    }
  });

  // Re-measure the week select once webfonts finish loading, so its width
  // matches the final rendered text rather than the fallback font.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (!el.weekPicker.hidden) sizeWeekSelect();
    });
  }

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
