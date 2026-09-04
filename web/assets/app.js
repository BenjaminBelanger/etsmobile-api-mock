import "./vendor/fluent.js";
import { icon } from "./vendor/fluent-icons.js";

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
  catalog: [],
};

const el = {
  sessionSelect: document.getElementById("sessionSelect"),
  scopeToggle: document.getElementById("scopeToggle"),
  scopeOccurrence: document.getElementById("scopeOccurrence"),
  weekPicker: document.getElementById("weekPicker"),
  weekSelect: document.getElementById("weekSelect"),
  weekPrev: document.getElementById("weekPrev"),
  weekNext: document.getElementById("weekNext"),
  weekToday: document.getElementById("weekToday"),
  dayHeads: document.getElementById("dayHeads"),
  gutter: document.getElementById("gutter"),
  grid: document.getElementById("grid"),
  board: document.getElementById("board"),
  week: document.getElementById("week"),
  trashList: document.getElementById("trashList"),
  undoBtn: document.getElementById("undoBtn"),
  redoBtn: document.getElementById("redoBtn"),
  resetBtn: document.getElementById("resetBtn"),
  addBtn: document.getElementById("addBtn"),
  statusbar: document.querySelector(".statusbar"),
  statusText: document.getElementById("statusText"),
  statusProgress: document.getElementById("statusProgress"),
  addDialog: document.getElementById("addDialog"),
  addForm: document.getElementById("addForm"),
  addSubmit: document.getElementById("addSubmit"),
  resetDialog: document.getElementById("resetDialog"),
  resetSession: document.getElementById("resetSession"),
  resetConfirm: document.getElementById("resetConfirm"),
  fJour: document.getElementById("fJour"),
  fKind: document.getElementById("fKind"),
  fSigle: document.getElementById("fSigle"),
  fTitre: document.getElementById("fTitre"),
  fStart: document.getElementById("fStart"),
  fEnd: document.getElementById("fEnd"),
  toastHost: document.getElementById("toastHost"),
  toast: document.getElementById("toast"),
  toastText: document.getElementById("toastText"),
};

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

function paintIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    const size = Number(node.dataset.iconSize) || 20;
    node.innerHTML = icon(node.dataset.icon, size);
  });
}

function fillDropdown(dropdown, items, selected, { freeform = false } = {}) {
  const listbox = dropdown.querySelector("fluent-listbox");
  listbox.replaceChildren();
  if (freeform) {
    const option = document.createElement("fluent-option");
    option.setAttribute("freeform", "");
    option.hidden = true;
    listbox.appendChild(option);
  }
  items.forEach((item) => {
    const option = document.createElement("fluent-option");
    option.setAttribute("value", item.value);
    option.textContent = item.text;
    if (item.value === selected) option.setAttribute("selected", "");
    listbox.appendChild(option);
  });
}

function dropdownValue(dropdown) {
  return dropdown.value ?? dropdown.control?.value ?? "";
}

function currentWeek() {
  if (!state.semester) return null;
  return state.semester.weeks.find((w) => w.index === state.weekIndex) || null;
}
function weekExists(index) {
  return !!state.semester && state.semester.weeks.some((w) => w.index === index);
}
function todayWeekIndex(semester) {
  if (!semester || !semester.weeks.length) return null;
  const today = todayISO();
  for (const w of semester.weeks) {
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

function occurrencesForWeek(week) {
  const dates = new Set(Object.values(week.dates));
  const occMode = occurrenceMode();
  return (state.data.occurrences || []).filter(
    (occ) => dates.has(occ.date) && (occMode || !occ.canceled)
  );
}

function setStatus(text, busy, isError) {
  el.statusText.textContent = text;
  state.busy = !!busy;
  el.statusProgress.hidden = !busy;
  el.statusbar.dataset.state = isError ? "error" : busy ? "busy" : "idle";
}

let toastTimer = null;
function toast(msg, isError) {
  el.toastText.textContent = msg;
  el.toast.setAttribute("intent", isError ? "error" : "success");
  el.toastHost.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.toastHost.hidden = true), 2600);
}

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
    setStatus("Erreur.", false, true);
    toast(err.message || "Échec de l'opération", true);
    throw err;
  }
}

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
  if (!semester || !semester.weeks.length) {
    el.weekPicker.hidden = true;
    el.scopeOccurrence.disabled = true;
    if (state.editScope === "occurrence") setScope("series");
    return;
  }
  el.scopeOccurrence.disabled = false;
  el.weekPicker.hidden = false;
  fillDropdown(
    el.weekSelect,
    semester.weeks.map((w) => ({ value: String(w.index), text: `S${w.index} (${w.range})` })),
    String(state.weekIndex),
  );

  const first = semester.weeks[0].index;
  const last = semester.weeks[semester.weeks.length - 1].index;
  el.weekPrev.disabled = state.weekIndex <= first;
  el.weekNext.disabled = state.weekIndex >= last;

  const todayIdx = todayWeekIndex(semester);
  el.weekToday.hidden = todayIdx == null || todayIdx === state.weekIndex;
}

function selectWeek(index) {
  if (!weekExists(index)) return;
  state.weekIndex = index;
  renderWeekPicker();
  renderScaffold();
  renderBlocks(false);
}

function renderSessions(data) {
  if (el.sessionSelect.dataset.filled === "1" && dropdownValue(el.sessionSelect) === data.session)
    return;
  fillDropdown(
    el.sessionSelect,
    data.sessions.map((code) => ({ value: code, text: code })),
    data.session,
  );
  el.sessionSelect.dataset.filled = "1";
}

function renderScaffold() {
  const week = currentWeek();
  const today = todayISO();

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

  fitPxPerMin();
  const height = durToPx(totalMin());

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

function fitPxPerMin() {
  const total = totalMin();
  if (total <= 0) return;

  el.gutter.style.height = "0px";
  el.grid.style.height = "0px";

  const avail = el.board.clientHeight - el.week.offsetHeight - 1;

  if (avail > 0) state.pxPerMin = Math.max(0.4, avail / total);
}

function renderBlocks(animate) {
  document.querySelectorAll(".block").forEach((b) => b.remove());
  const week = currentWeek();
  let count = 0;
  let selectionAlive = false;
  const occMode = occurrenceMode();
  el.board.classList.toggle("is-occurrence", occMode);

  const byDay = new Map();
  (week ? occurrencesForWeek(week) : []).forEach((occ) => {
    const col = columnFor(occ.jour);
    if (!col) return;
    const start = toMin(occ.heureDebut);
    const end = toMin(occ.heureFin);
    const item = { occ, col, start, end, lane: 0, lanes: 1 };
    if (!byDay.has(occ.jour)) byDay.set(occ.jour, []);
    byDay.get(occ.jour).push(item);
  });

  byDay.forEach((items) => {
    assignLanes(items);
    items.forEach((it) => {
      const node = buildBlock(it.occ, animate, occMode);
      if (it.lanes > 1) applyLaneLayout(node, it.lane, it.lanes);
      if (it.occ.courseId === state.selectedCourseId) {
        node.classList.add("is-selected");
        selectionAlive = true;
      }
      it.col.appendChild(node);
      count++;
    });
  });

  if (!selectionAlive) state.selectedCourseId = null;
  fitBlockTitles();
  renderEmpty(count === 0);
}

function fitBlockTitles() {
  document.querySelectorAll(".block").forEach((node) => {
    const title = node.querySelector(".block__title");
    if (!title) return;
    const lineHeight = parseFloat(getComputedStyle(title).lineHeight) || 20;
    const lines = Math.min(2, Math.floor(title.clientHeight / lineHeight));
    if (lines < 1) {
      node.classList.add("is-compact");
      return;
    }

    title.style.maxHeight = `${lines * lineHeight}px`;
    title.style.webkitLineClamp = String(lines);
  });
}

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
  div.innerHTML = `<p>Aucun cours cette session.</p>`;
  el.board.appendChild(div);
}

function buildBlock(occ, animate, occMode) {
  const start = toMin(occ.heureDebut);
  const end = toMin(occ.heureFin);
  const dur = end - start;
  const editable = !!occ.blockId;
  const canceled = !!occ.canceled;
  const node = document.createElement("div");
  node.className = "block";
  if (occ.kind === "labo") node.classList.add("is-labo");
  if (occ.kind === "exam") node.classList.add("is-exam");
  if (canceled) node.classList.add("is-canceled");
  if (animate) node.classList.add("is-entering");

  if (durToPx(dur) < 82) node.classList.add("is-compact");

  if (durToPx(dur) < 68) node.classList.add("is-tight");
  if (occ.overridden) node.classList.add("is-overridden");
  const t = tintFor(occ.sigle);
  node.style.setProperty("--bg", `var(--c${t}-bg)`);
  node.style.setProperty("--bd", `var(--c${t}-bd)`);
  node.style.setProperty("--tx", `var(--c${t}-tx)`);
  node.style.top = `${minToPx(start)}px`;
  node.style.height = `${durToPx(dur) - 3}px`;
  node.dataset.blockId = occ.blockId || "";
  node.dataset.courseId = occ.courseId;
  node.dataset.jour = occ.jour;
  node.dataset.start = start;
  node.dataset.dur = dur;

  const kindLabel =
    occ.kind === "labo" ? `<span class="block__kind">(Labo)</span>` : "";
  const badge =
    occ.kind === "exam"
      ? `<span class="block__badge block__badge--off" title="Examen final">Examen</span>`
      : canceled
      ? `<span class="block__badge block__badge--off" title="Séance annulée cette semaine">Annulée</span>`
      : occ.overridden
      ? `<span class="block__badge" title="Séance modifiée cette semaine">Modifiée</span>`
      : "";
  const resetBtn =
    occMode && editable && occ.overridden
      ? `<button class="block__reset" title="${
          canceled ? "Rétablir cette séance" : "Rétablir cette séance au modèle"
        }">${icon("reset", 13)}</button>`
      : "";
  const delBtn =
    !editable || canceled
      ? ""
      : `<button class="block__del" title="${
          occMode ? "Annuler cette séance" : "Supprimer le cours"
        }">${icon("dismiss", 13)}</button>`;

  node.innerHTML = `
      <div class="block__handle block__handle--top"></div>
      <div class="block__inner">
        <div class="block__sigle"><span class="block__code">${occ.sigle}${occ.groupe ? "-" + occ.groupe : ""}</span>${kindLabel}${badge}</div>
        <div class="block__title">${escapeHtml(occ.titre)}</div>
        <div class="block__meta"><span class="block__time">${occ.heureDebut} - ${occ.heureFin}</span>${occ.room ? `<span class="block__room">${escapeHtml(occ.room)}</span>` : ""}</div>
      </div>
      ${resetBtn}
      ${delBtn}
      <div class="block__tag">${occ.heureDebut}</div>
      <div class="block__handle block__handle--bottom"></div>`;

  const resetEl = node.querySelector(".block__reset");
  if (resetEl) {
    resetEl.addEventListener("click", (e) => {
      e.stopPropagation();
      resetOccurrence(occ);
    });
  }
  const delEl = node.querySelector(".block__del");
  if (delEl) {
    delEl.addEventListener("click", (e) => {
      e.stopPropagation();
      if (occMode) {
        cancelOccurrence(occ);
      } else {
        deleteCourse(occ.courseId);
      }
    });
  }
  if (editable && !canceled) attachDrag(node, occ);
  return node;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

function renderTrash(trash) {
  el.trashList.replaceChildren();
  if (!trash.length) {
    const li = document.createElement("li");
    li.className = "trash__empty";
    li.textContent = "Aucun cours supprimé.";
    el.trashList.appendChild(li);
    return;
  }
  trash.forEach((c) => {
    const li = document.createElement("li");
    li.className = "trash__item";
    li.innerHTML = `
        <div class="trash__meta">
          <div class="trash__sigle">${c.sigle}${c.groupe ? "-" + c.groupe : ""}</div>
          <div class="trash__title">${escapeHtml(c.titre)}</div>
        </div>
        <fluent-button class="trash__restore" appearance="subtle" size="small" icon-only
          title="Restaurer" aria-label="Restaurer ${c.sigle}">${icon("restore", 16)}</fluent-button>`;
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
  state.catalog = catalog;
  if (catalogFilled) return;
  fillDropdown(
    el.fJour,
    state.days.map((d) => ({ value: d.jour, text: d.name })),
    state.days.length ? state.days[0].jour : undefined,
  );
  catalogFilled = true;
}

function attachDrag(node, occ) {
  const topH = node.querySelector(".block__handle--top");
  const botH = node.querySelector(".block__handle--bottom");
  node.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".block__del")) return;
    if (e.target.closest(".block__reset")) return;
    let edge = null;
    if (e.target === topH) edge = "resize-top";
    else if (e.target === botH) edge = "resize-bottom";
    startGesture(e, node, occ, edge);
  });
}

function startGesture(e, node, occ, resizeEdge) {
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
  const startY = e.clientY;
  const startX = e.clientX;
  let moved = false;
  let mode = resizeEdge ? null : "move";
  let cur = { jour: jour0, start: startMin0, dur: dur0 };
  const tag = node.querySelector(".block__tag");

  node.classList.add("is-dragging");

  clearLaneLayout(node);

  const onMove = (ev) => {
    const dy = ev.clientY - startY;
    const dx = ev.clientX - startX;
    const dMin = dy / state.pxPerMin;
    if (Math.abs(dy) > 2 || Math.abs(dx) > 2) moved = true;

    if (mode === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 5) return;
      mode = Math.abs(dx) > Math.abs(dy) ? "move" : resizeEdge;
    }

    if (mode === "move") {
      let ns = snap(startMin0 + dMin);
      ns = Math.max(state.dayStartMin, Math.min(ns, state.dayEndMin - dur0));

      let idx = Math.floor((ev.clientX - gridRect.left) / colWidth);
      idx = Math.max(0, Math.min(idx, state.days.length - 1));
      const jour = state.days[idx].jour;
      cur = { jour, start: ns, dur: dur0 };

      node.style.top = `${minToPx(ns)}px`;
      node.style.transform = `translateX(${(idx - origIdx) * colWidth}px)`;
      highlightColumn(jour);
      tag.textContent = `${state.days[idx].short} ${toHHMM(ns)}`;
    } else if (mode === "resize-bottom") {
      let ne = snap(startMin0 + dur0 + dMin);
      ne = Math.min(state.dayEndMin, Math.max(ne, startMin0 + state.minDuration));
      cur.dur = ne - startMin0;
      node.style.height = `${durToPx(cur.dur) - 3}px`;
      tag.textContent = `${toHHMM(startMin0)} - ${toHHMM(ne)}`;
    } else if (mode === "resize-top") {
      let ns = snap(startMin0 + dMin);
      ns = Math.max(state.dayStartMin, Math.min(ns, startMin0 + dur0 - state.minDuration));
      cur.start = ns;
      cur.dur = startMin0 + dur0 - ns;
      node.style.top = `${minToPx(ns)}px`;
      node.style.height = `${durToPx(cur.dur) - 3}px`;
      tag.textContent = `${toHHMM(ns)} - ${toHHMM(startMin0 + dur0)}`;
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
      renderBlocks(false);
      if (!moved) selectCourse(occ.courseId);
      return;
    }
    commitGesture(mode, occ, cur);
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

function commitGesture(mode, occ, cur) {
  if (occurrenceMode()) {
    apiPost("/occurrence/set", {
      session: state.session,
      blockId: occ.blockId,
      date: occ.date,
      jour: cur.jour,
      heureDebut: toHHMM(cur.start),
      heureFin: toHHMM(cur.start + cur.dur),
    }).then(() => toast("Séance modifiée cette semaine"));
    return;
  }
  if (mode === "move") {
    apiPost("/block/move", {
      session: state.session,
      blockId: occ.blockId,
      jour: cur.jour,
      heureDebut: toHHMM(cur.start),
    });
  } else {
    apiPost("/block/resize", {
      session: state.session,
      blockId: occ.blockId,
      heureDebut: toHHMM(cur.start),
      heureFin: toHHMM(cur.start + cur.dur),
    });
  }
}

function deleteCourse(courseId) {
  apiPost("/course/delete", { session: state.session, courseId }).then(() =>
    toast("Cours déplacé vers la corbeille")
  );
}

function cancelOccurrence(occ) {
  apiPost("/occurrence/cancel", {
    session: state.session,
    blockId: occ.blockId,
    date: occ.date,
  }).then(() => toast("Séance annulée cette semaine"));
}

function resetOccurrence(occ) {
  apiPost("/occurrence/reset", {
    session: state.session,
    blockId: occ.blockId,
    date: occ.date,
  }).then(() => toast(occ.canceled ? "Séance rétablie" : "Séance rétablie au modèle"));
}

function setScope(scope) {
  if (scope !== "series" && scope !== "occurrence") return;
  if (el.scopeToggle.activeid !== `scope${scope === "series" ? "Series" : "Occurrence"}`) {
    el.scopeToggle.activeid = scope === "series" ? "scopeSeries" : "scopeOccurrence";
  }
  if (state.editScope === scope) return;
  state.editScope = scope;
  if (state.data) renderBlocks(false);
}

async function loadSession(session, animate) {
  setStatus("Chargement…", true);
  try {
    const data = await apiGet(session);
    applyState(data, { animate });
    setStatus("Prêt.", false);
  } catch (err) {
    setStatus("Erreur.", false, true);
    toast(err.message, true);
  }
}

function openAddDialog() {
  fillDropdown(
    el.fSigle,
    state.catalog.map((c) => ({ value: c.sigle, text: c.sigle })),
    undefined,
    { freeform: true },
  );
  if (el.fSigle.control) el.fSigle.control.value = "";
  el.fTitre.value = "";
  el.addDialog.show();
  setTimeout(() => el.fSigle.focus(), 40);
}

function submitAddCourse() {
  const sigle = String(dropdownValue(el.fSigle) || "").trim();
  if (!sigle) {
    toast("Un sigle est requis", true);
    el.fSigle.focus();
    return;
  }
  apiPost("/course/add", {
    session: state.session,
    sigle,
    titre: el.fTitre.value,
    jour: dropdownValue(el.fJour),
    heureDebut: el.fStart.value,
    heureFin: el.fEnd.value,
    kind: dropdownValue(el.fKind),
  }).then(() => {
    el.addDialog.hide();
    toast(`${sigle.toUpperCase()} ajouté`);
  });
}

paintIcons();

el.fSigle.addEventListener("input", () => {
  const typed = String(dropdownValue(el.fSigle) || "").trim().toLowerCase();
  const match = state.catalog.find((c) => c.sigle.toLowerCase() === typed);
  if (match && !el.fTitre.value) el.fTitre.value = match.titre;
});
el.fSigle.addEventListener("change", () => {
  const match = state.catalog.find((c) => c.sigle === dropdownValue(el.fSigle));
  if (match) el.fTitre.value = match.titre;
});

el.addForm.addEventListener("submit", (e) => {
  e.preventDefault();
  submitAddCourse();
});
el.addSubmit.addEventListener("click", submitAddCourse);
el.addDialog
  .querySelectorAll("[data-close]")
  .forEach((n) => n.addEventListener("click", () => el.addDialog.hide()));

el.resetDialog
  .querySelectorAll("[data-close-reset]")
  .forEach((n) => n.addEventListener("click", () => el.resetDialog.hide()));
el.resetConfirm.addEventListener("click", () => {
  el.resetDialog.hide();
  apiPost("/reset", { session: state.session }).then(() =>
    toast("Session réinitialisée")
  );
});

el.sessionSelect.addEventListener("change", () =>
  loadSession(dropdownValue(el.sessionSelect), true)
);
el.scopeToggle.addEventListener("change", (e) => {
  const scope = e.detail && e.detail.dataset ? e.detail.dataset.scope : null;
  if (scope) setScope(scope);
});
el.weekSelect.addEventListener("change", () =>
  selectWeek(Number(dropdownValue(el.weekSelect)))
);
el.weekPrev.addEventListener("click", () => selectWeek(state.weekIndex - 1));
el.weekNext.addEventListener("click", () => selectWeek(state.weekIndex + 1));
el.weekToday.addEventListener("click", () => {
  const idx = todayWeekIndex(state.semester);
  if (idx != null) selectWeek(idx);
});
el.addBtn.addEventListener("click", openAddDialog);
el.undoBtn.addEventListener("click", () =>
  apiPost("/undo", { session: state.session })
);
el.redoBtn.addEventListener("click", () =>
  apiPost("/redo", { session: state.session })
);
el.resetBtn.addEventListener("click", () => {
  el.resetSession.textContent = state.session || "";
  el.resetDialog.show();
});

document.addEventListener("keydown", (e) => {
  const inDialog = !!document.activeElement?.closest?.("fluent-dialog");
  const typing =
    inDialog ||
    /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName) ||
    !!document.activeElement?.closest?.("fluent-dropdown, fluent-text-input");
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
    setStatus("Impossible de contacter le serveur.", false, true);
    toast(err.message || "Serveur injoignable", true);
  }
})();
