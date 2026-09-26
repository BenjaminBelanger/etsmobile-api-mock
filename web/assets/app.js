import "./vendor/fluent.js";
import { icon } from "./vendor/fluent-icons.js";

const API = "/editor/api";
const TINTS = 12;

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
  selectedOccurrence: null,
  detailCourseId: null,
  evalIndex: null,
  statsOpen: false,
  semester: null,
  weekIndex: null,
  editScope: "series",
  catalog: [],
  view: "schedule",
  failures: null,
  failuresPast: [],
  failuresFuture: [],
  failureKind: "latency",
  staged: [],
  endpoints: [],
  presets: [],
  calls: [],
  callsSeq: 0,
  callsFailed: false,
  callsGroup: null,
};

const el = {
  viewToggle: document.getElementById("viewToggle"),
  scheduleView: document.getElementById("scheduleView"),
  scheduleControls: document.getElementById("scheduleControls"),
  scheduleToolbar: document.getElementById("scheduleToolbar"),
  failuresView: document.getElementById("failuresView"),
  failuresToolbar: document.getElementById("failuresToolbar"),
  failuresDot: document.getElementById("failuresDot"),
  failuresUndoBtn: document.getElementById("failuresUndoBtn"),
  failuresRedoBtn: document.getElementById("failuresRedoBtn"),
  failuresResetBtn: document.getElementById("failuresResetBtn"),
  failureAddBtn: document.getElementById("failureAddBtn"),
  failureDialog: document.getElementById("failureDialog"),
  failureForm: document.getElementById("failureForm"),
  failureParams: document.getElementById("failureParams"),
  failureHint: document.getElementById("failureHint"),
  failureSubmit: document.getElementById("failureSubmit"),
  fFailureKind: document.getElementById("fFailureKind"),
  injectionList: document.getElementById("injectionList"),
  injectionEmpty: document.getElementById("injectionEmpty"),
  presetList: document.getElementById("presetList"),
  callsView: document.getElementById("callsView"),
  callsToolbar: document.getElementById("callsToolbar"),
  callsBoard: document.getElementById("callsBoard"),
  callsTable: document.getElementById("callsTable"),
  callRows: document.getElementById("callRows"),
  callsEmpty: document.getElementById("callsEmpty"),
  callsClearBtn: document.getElementById("callsClearBtn"),
  callsExportBtn: document.getElementById("callsExportBtn"),
  callsTotal: document.getElementById("callsTotal"),
  endpointStats: document.getElementById("endpointStats"),
  endpointStatsRows: document.getElementById("endpointStatsRows"),
  endpointStatsEmpty: document.getElementById("endpointStatsEmpty"),
  markerLabel: document.getElementById("markerLabel"),
  markerAddBtn: document.getElementById("markerAddBtn"),
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
  detailPanel: document.getElementById("detailPanel"),
  detailSelect: document.getElementById("detailSelect"),
  detail: document.getElementById("detail"),
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

const tints = new Map();

function assignTints(courses) {
  const sigles = [...new Set(courses.map((c) => c.sigle))];
  const live = new Set(sigles);
  tints.forEach((_, sigle) => {
    if (!live.has(sigle)) tints.delete(sigle);
  });
  const taken = new Set(tints.values());
  sigles.forEach((sigle) => {
    if (tints.has(sigle)) return;
    let t = 0;
    while (t < TINTS && taken.has(t)) t++;
    if (t === TINTS) t = hashTint(sigle);
    taken.add(t);
    tints.set(sigle, t);
  });
}

function hashTint(sigle) {
  let h = 0;
  for (let i = 0; i < sigle.length; i++) h = (h * 31 + sigle.charCodeAt(i)) >>> 0;
  return h % TINTS;
}

const tintFor = (sigle) => tints.get(sigle) ?? hashTint(sigle);

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
  return (state.data.occurrences || []).filter((occ) => dates.has(occ.date));
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
    setStatus(data.notices?.length ? data.notices.join(" ") : "Enregistré.", false);
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
  assignTints(data.courses || []);
  state.semester = meta.semester || null;
  if (
    prevSession !== data.session ||
    state.weekIndex == null ||
    !weekExists(state.weekIndex)
  ) {
    state.weekIndex = defaultWeekIndex(state.semester);
  }
  if (prevSession !== data.session) {
    state.detailCourseId = null;
    state.evalIndex = null;
  }
  renderSessions(data);
  renderWeekPicker();
  renderScaffold();
  renderBlocks(opts && opts.animate);
  renderDetail();
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
  const key = data.sessions.join(",");
  if (
    el.sessionSelect.dataset.key === key &&
    dropdownValue(el.sessionSelect) === data.session
  )
    return;
  fillDropdown(
    el.sessionSelect,
    data.sessions.map((code) => ({ value: code, text: code })),
    data.session,
  );
  el.sessionSelect.dataset.key = key;
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

  if (!selectionAlive) selectCourse(null);
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

function selectCourse(courseId, occ) {
  state.selectedCourseId = courseId;
  state.selectedOccurrence = occ ? { blockId: occ.blockId, date: occ.date } : null;
  document.querySelectorAll(".block").forEach((n) =>
    n.classList.toggle("is-selected", n.dataset.courseId === courseId)
  );
  if (courseId && courseId !== state.detailCourseId) showDetail(courseId);
}

function selectedOccurrence() {
  const sel = state.selectedOccurrence;
  if (!sel) return null;
  return (
    (state.data.occurrences || []).find(
      (occ) => occ.blockId === sel.blockId && occ.date === sel.date
    ) || null
  );
}

function showDetail(courseId) {
  state.detailCourseId = courseId;
  state.evalIndex = null;
  renderDetail();
}

function renderEmpty(isEmpty) {
  const existing = el.board.querySelector(".board__empty");
  if (existing) existing.remove();
  if (!isEmpty) return;
  const hasAny = !!(state.data && (state.data.occurrences || []).length);
  const div = document.createElement("div");
  div.className = "board__empty";
  div.innerHTML = `<p>${
    hasAny ? "Aucune séance cette semaine." : "Aucun cours cette session."
  }</p>`;
  el.board.appendChild(div);
}

const BLOCK_MARKS = {
  exam: {
    icon: "hatGraduation",
    label: "Examen",
    tip: "Examen final",
    off: true,
  },
  canceled: {
    icon: "dismissCircle",
    label: "Annulée",
    tip: "Séance annulée cette semaine",
    off: true,
  },
  overridden: {
    icon: "edit",
    label: "Modifiée",
    tip: "Séance modifiée cette semaine",
  },
};

function blockMark(occ) {
  if (occ.kind === "exam") return BLOCK_MARKS.exam;
  if (occ.canceled) return BLOCK_MARKS.canceled;
  if (occ.overridden) return BLOCK_MARKS.overridden;
  return null;
}

function markBadge(mark) {
  const off = mark.off ? " block__badge--off" : "";
  return `<span class="block__badge${off}" title="${mark.tip}">${icon(
    mark.icon,
    12
  )}<span class="block__badge-text">${mark.label}</span></span>`;
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
  const mark = blockMark(occ);
  node.title = [
    `${occ.sigle}${occ.groupe ? "-" + occ.groupe : ""}`,
    occ.titre,
    mark && mark.tip,
  ]
    .filter(Boolean)
    .join(" — ");
  node.dataset.blockId = occ.blockId || "";
  node.dataset.courseId = occ.courseId;
  node.dataset.jour = occ.jour;
  node.dataset.start = start;
  node.dataset.dur = dur;

  const isExam = occ.kind === "exam";
  const kindLabel =
    occ.kind === "labo" ? `<span class="block__kind">(Labo)</span>` : "";
  const badge = mark ? markBadge(mark) : "";
  const resetBtn =
    editable && occ.overridden && (occMode || isExam)
      ? `<button class="block__reset" title="${
          isExam
            ? "Rétablir l'examen généré"
            : canceled
            ? "Rétablir cette séance"
            : "Rétablir cette séance au modèle"
        }">${icon("reset", 13)}</button>`
      : "";
  const delBtn =
    !editable || canceled || isExam
      ? ""
      : `<button class="block__del" title="${
          occMode ? "Annuler cette séance" : "Supprimer le cours"
        }">${icon("dismiss", 13)}</button>`;

  node.innerHTML = `
      <div class="block__handle block__handle--top"></div>
      <div class="block__inner">
        <div class="block__sigle"><span class="block__code">${escapeHtml(
          occ.sigle
        )}${occ.groupe ? "-" + escapeHtml(occ.groupe) : ""}</span>${kindLabel}${badge}</div>
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
    const label = `${c.sigle}${c.groupe ? "-" + c.groupe : ""}`;
    li.innerHTML = `
        <div class="trash__meta">
          <div class="trash__sigle">${escapeHtml(label)}</div>
          <div class="trash__title">${escapeHtml(c.titre)}</div>
        </div>
        <fluent-button class="trash__restore" appearance="subtle" size="small" icon-only
          title="Restaurer" aria-label="Restaurer ${escapeHtml(c.sigle)}">${icon("restore", 16)}</fluent-button>`;
    li.querySelector(".trash__restore").addEventListener("click", () =>
      apiPost("/course/restore", { session: state.session, courseId: c.courseId }).then(
        () => toast(`${c.sigle} restauré`)
      )
    );
    el.trashList.appendChild(li);
  });
}

const plain = (value) => String(value ?? "").replace(",", ".");
const fieldText = (value) => (value == null ? "" : plain(value));

function detailCourses() {
  return (state.data && state.data.courses) || [];
}

function currentDetail() {
  const courses = detailCourses();
  return (
    courses.find((c) => c.courseId === state.detailCourseId) || courses[0] || null
  );
}

let detailSelectKey = "";
function fillDetailSelect(courses, selected) {
  const key = `${courses.map((c) => c.courseId).join(",")}|${selected}`;
  if (key === detailSelectKey) return;
  detailSelectKey = key;
  fillDropdown(
    el.detailSelect,
    courses.map((c) => ({ value: c.courseId, text: `${c.sigle}-${c.groupe}` })),
    selected,
  );
}

function iconButton(action, iconName, label, disabled) {
  return `<fluent-button class="detail__act" data-act="${action}" appearance="subtle"
      size="small" icon-only${disabled ? " disabled" : ""} title="${label}"
      aria-label="${label}">${icon(iconName, 16)}</fluent-button>`;
}

function propInput(key, label, value, type, opts = {}) {
  const pinned = !!opts.pinned;
  const classes = `props__input${pinned ? " is-pinned" : ""}${
    opts.wide ? " props__input--wide" : ""
  }${opts.narrow ? " props__input--narrow" : ""}`;
  const title = pinned
    ? ' title="Valeur modifiée, videz le champ pour rétablir la valeur générée"'
    : "";
  return `<fluent-text-input class="${classes}" control-size="small" appearance="filled-lighter"
      type="${type}" data-key="${key}" value="${escapeHtml(value)}"${title}>${label}</fluent-text-input>`;
}

function checkBox(key, label, checked) {
  return `<label class="check">
        <input type="checkbox" data-key="${key}"${checked ? " checked" : ""} />
        <span>${label}</span>
      </label>`;
}

function summaryHtml(summary) {
  if (!summary || !summary.noteACeJour) {
    return `<p class="detail__empty">Aucune note publiée.</p>`;
  }
  return `<div class="detail__summary">
        <span>À ce jour <b>${plain(summary.noteACeJour)}</b></span>
        <span>Moyenne <b>${plain(summary.moyenneClasse)}</b></span>
        <span>Publié <b>${plain(summary.tauxPublication)} %</b></span>
      </div>`;
}

function warningsHtml(evals) {
  const lines = [];
  const total = evals.reduce((sum, ev) => sum + ev.ponderation, 0);
  if (evals.length && total !== 100) lines.push(`Pondération totale ${total} %`);
  const over = evals.filter((ev) => ev.note != null && ev.note > ev.corrigeSur);
  if (over.length) {
    lines.push(`Note hors barème : ${over.map((ev) => ev.nom).join(", ")}`);
  }
  if (!lines.length) return "";
  return `<div class="detail__warn">${lines
    .map((line) => `<span>${escapeHtml(line)}</span>`)
    .join("")}</div>`;
}

const STAT_FIELDS = ["rangCentile", "moyenne", "mediane", "ecartType"];

function propsHtml(ev) {
  const pinned = ev.pinned || [];
  const grade = (field, label, type = "text") =>
    propInput(`ev:${field}`, label, fieldText(ev[field]), type, {
      pinned: pinned.includes(field),
    });
  const open = state.statsOpen;
  const statsPinned = STAT_FIELDS.some((field) => pinned.includes(field));
  const statsTitle = statsPinned
    ? ' title="Contient des valeurs modifiées"'
    : "";
  return `<div class="props">
        <div class="props__grid">
          ${propInput("ev:nom", "Nom", ev.nom, "text", { wide: true })}
          ${grade("note", "Note")}
          ${propInput("ev:corrigeSur", "Corrigé sur", fieldText(ev.corrigeSur), "text")}
          ${propInput("ev:ponderation", "Pondération", fieldText(ev.ponderation), "text")}
          ${grade("dateCible", "Date cible", "date")}
        </div>
        <div class="props__checks">
          ${checkBox("ev:publie", "Publié", ev.publie)}
          ${checkBox("ev:isTeam", "Équipe", ev.isTeam)}
        </div>
        <button type="button" class="stats${open ? " is-open" : ""}${
          statsPinned ? " is-pinned" : ""
        }" data-act="toggleStats" aria-expanded="${open}"${statsTitle}>
          ${icon("chevronRight", 16)}<span>Statistiques</span>
        </button>
        ${
          open
            ? `<div class="props__grid">
          ${grade("rangCentile", "Rang centile")}
          ${grade("moyenne", "Moyenne")}
          ${grade("mediane", "Médiane")}
          ${grade("ecartType", "Écart type")}
        </div>`
            : ""
        }
        <div class="props__actions">
          <fluent-button class="props__del" data-act="delete" appearance="subtle" size="small">Supprimer</fluent-button>
        </div>
      </div>`;
}

function evalHtml(ev, isOpen) {
  const hasNote = ev.note != null;
  const note = hasNote
    ? `${plain(ev.note)}<span class="evals__sur">/${plain(ev.corrigeSur)}</span>`
    : "";
  const warn = hasNote && ev.note > ev.corrigeSur;
  return `<li class="evals__item${isOpen ? " is-open" : ""}">
        <button type="button" class="evals__row" data-index="${ev.index}" aria-expanded="${isOpen}">
          <span class="evals__name">${escapeHtml(ev.nom)}</span>
          <span class="evals__pond">${ev.ponderation} %</span>
          <span class="evals__note${warn ? " is-warn" : ""}">${note}</span>
          <span class="evals__pub${ev.publie ? " is-on" : ""}" title="${
            ev.publie ? "Publié" : "Non publié"
          }"></span>
        </button>
        ${isOpen ? propsHtml(ev) : ""}
      </li>`;
}

function examHtml(exam) {
  if (!exam) {
    return `<header class="detail__head"><h3>Examen final</h3></header>
      <p class="detail__empty">Aucun examen final.</p>`;
  }
  const pinned = exam.pinned || [];
  const field = (source, key, label, type, wide) =>
    propInput(`exam:${key}`, label, exam[source], type, {
      pinned: pinned.includes(source),
      wide,
    });
  return `<header class="detail__head">
        <h3>Examen final</h3>
        ${pinned.length ? iconButton("examReset", "reset", "Rétablir l'examen généré") : ""}
      </header>
      <div class="props__grid">
        ${field("dateExamen", "date", "Date", "date", true)}
        ${field("heureDebut", "heureDebut", "Début", "time")}
        ${field("heureFin", "heureFin", "Fin", "time")}
        ${field("local", "local", "Local", "text", true)}
      </div>`;
}

function detailHtml(course) {
  const evals = course.evaluations || [];
  const openIndex = state.evalIndex;
  const canResetGrades = !!course.canResetGrades;
  return `<p class="detail__title">${escapeHtml(course.titre)}</p>
      ${propInput("course:cote", "Cote", course.cote, "text", { narrow: true })}
      <section class="detail__section">
        <header class="detail__head">
          <h3>Évaluations</h3>
          ${iconButton("addEval", "add", "Ajouter un élément")}
          ${canResetGrades ? iconButton("resetGrades", "reset", "Régénérer les notes") : ""}
        </header>
        ${summaryHtml(course.summary)}
        <ul class="evals">${evals
          .map((ev) => evalHtml(ev, ev.index === openIndex))
          .join("")}</ul>
        ${evals.length ? "" : `<p class="detail__empty">Aucun élément d'évaluation.</p>`}
        ${warningsHtml(evals)}
      </section>
      <section class="detail__section">${examHtml(course.exam)}</section>`;
}

let renderingDetail = false;

function renderDetail() {
  const courses = detailCourses();
  const course = currentDetail();
  el.detailPanel.hidden = !course;
  if (!course) {
    el.detail.replaceChildren();
    return;
  }
  state.detailCourseId = course.courseId;
  const evals = course.evaluations || [];
  if (state.evalIndex != null && state.evalIndex >= evals.length) {
    state.evalIndex = evals.length ? evals.length - 1 : null;
  }
  fillDetailSelect(courses, course.courseId);

  const active = document.activeElement;
  const focusKey = el.detail.contains(active) ? active.dataset.key : null;
  const html = detailHtml(course);
  renderingDetail = true;
  el.detail.innerHTML = html;
  renderingDetail = false;
  wireDetail(course);
  if (focusKey) {
    const node = el.detail.querySelector(`[data-key="${focusKey}"]`);
    if (node) node.focus();
  }
}

function wireDetail(course) {
  const list = el.detail.querySelector(".evals");
  const count = (course.evaluations || []).length;
  el.detail.querySelectorAll(".evals__row").forEach((row) => {
    row.addEventListener("click", () => {
      if (evalClickBlocked) {
        evalClickBlocked = false;
        return;
      }
      const index = Number(row.dataset.index);
      state.evalIndex = state.evalIndex === index ? null : index;
      renderDetail();
      const next = el.detail.querySelector(`.evals__row[data-index="${index}"]`);
      if (next) next.focus();
    });
    row.addEventListener("pointerdown", (e) => {
      evalClickBlocked = false;
      startEvalDrag(e, course, list, row.closest(".evals__item"));
    });
    row.addEventListener("keydown", (e) => {
      const dir = e.altKey && (e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0);
      if (!dir) return;
      const from = Number(row.dataset.index);
      const to = from + dir;
      if (to < 0 || to >= count) return;
      e.preventDefault();
      moveEvaluation(course, from, to).then(() => {
        const moved = el.detail.querySelector(`.evals__row[data-index="${to}"]`);
        if (moved) moved.focus();
      });
    });
  });
  el.detail.querySelectorAll("[data-key]").forEach((node) => {
    const key = node.dataset.key;
    if (node.type === "checkbox") {
      node.addEventListener("change", () => commitField(course, key, node.checked));
      return;
    }
    wireTextField(node, (value) => commitField(course, key, value));
  });
  el.detail.querySelectorAll("[data-act]").forEach((node) => {
    node.addEventListener("click", () => runDetailAction(course, node.dataset.act));
  });
}

function wireTextField(node, commit) {
  let saved = node.value;
  let typing = false;
  let incomplete = false;
  const save = () => {
    typing = false;
    const value = incomplete ? "" : node.value;
    if (renderingDetail || value === saved) return;
    saved = value;
    commit(value);
  };
  node.addEventListener(
    "input",
    (e) => {
      incomplete = !!e.composedPath()[0].validity?.badInput;
      if (incomplete) e.stopPropagation();
    },
    true,
  );
  node.addEventListener("pointerdown", () => {
    typing = false;
  });
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter") node.blur();
    else typing = true;
  });
  node.addEventListener("change", () => {
    if (!typing) save();
  });
  node.addEventListener("focusout", save);
}

function commitField(course, key, value) {
  const [scope, field] = key.split(":");
  const courseId = course.courseId;
  const revert = () => renderDetail();
  if (scope === "course") {
    const body = { session: state.session, courseId, cote: value };
    apiPost("/course/cote", body).catch(revert);
    return;
  }
  if (scope === "exam") {
    const body = { session: state.session, courseId };
    body[field] = value;
    apiPost("/exam/set", body).catch(revert);
    return;
  }
  apiPost("/evaluation/set", {
    session: state.session,
    courseId,
    index: state.evalIndex,
    field,
    value,
  }).catch(revert);
}

function runDetailAction(course, action) {
  const courseId = course.courseId;
  const body = { session: state.session, courseId };
  if (action === "addEval") {
    apiPost("/evaluation/add", body).then((data) => {
      const next = (data.courses.find((c) => c.courseId === courseId) || {}).evaluations;
      state.evalIndex = next && next.length ? next.length - 1 : null;
      renderDetail();
      toast("Élément ajouté");
    });
  } else if (action === "delete") {
    apiPost("/evaluation/delete", { ...body, index: state.evalIndex }).then(() =>
      toast("Élément supprimé")
    );
  } else if (action === "toggleStats") {
    state.statsOpen = !state.statsOpen;
    renderDetail();
    const next = el.detail.querySelector(".stats");
    if (next) next.focus();
  } else if (action === "resetGrades") {
    apiPost("/grades/reset", body).then(() => toast("Notes régénérées"));
  } else if (action === "examReset") {
    apiPost("/exam/reset", body).then(() => toast("Examen final rétabli"));
  }
}

const EVAL_DRAG_PX = 4;
const EVAL_DROP_MS = 150;
let evalClickBlocked = false;

function shiftIndex(idx, from, to) {
  if (idx == null) return null;
  if (idx === from) return to;
  if (from < idx && idx <= to) return idx - 1;
  if (to <= idx && idx < from) return idx + 1;
  return idx;
}

function moveEvaluation(course, from, to, delay) {
  const previous = state.evalIndex;
  state.evalIndex = shiftIndex(previous, from, to);
  const send = () =>
    apiPost("/evaluation/move", {
      session: state.session,
      courseId: course.courseId,
      index: from,
      toIndex: to,
    }).catch(() => {
      state.evalIndex = previous;
      renderDetail();
    });
  if (!delay) return send();
  return new Promise((resolve) => setTimeout(() => resolve(send()), delay));
}

function startEvalDrag(e, course, list, item) {
  if (state.busy || e.button !== 0 || !list || !item) return;
  const items = Array.from(list.children);
  if (items.length < 2) return;

  const from = items.indexOf(item);
  const listTop = list.getBoundingClientRect().top;
  const gap = parseFloat(getComputedStyle(list).rowGap) || 0;
  const boxes = items.map((node) => {
    const rect = node.getBoundingClientRect();
    return { top: rect.top - listTop, height: rect.height };
  });
  const own = boxes[from];
  const middles = boxes.map((box) => box.top + box.height / 2);
  const step = own.height + gap;
  const last = boxes[items.length - 1];
  const minTop = boxes[0].top;
  const maxTop = last.top + last.height - own.height;
  const grab = e.clientY - listTop - own.top;

  const rest = [];
  items.forEach((node, i) => {
    if (i === from) return;
    const base = i > from ? -step : 0;
    rest.push({ node, base, top: boxes[i].top + base, height: boxes[i].height });
  });
  const slotTop = (k) =>
    k === 0 ? boxes[0].top : rest[k - 1].top + rest[k - 1].height + gap;

  let dragging = false;
  let to = from;

  const openSlot = (k) => {
    rest.forEach((r, m) => {
      const offset = r.base + (m >= k ? step : 0);
      r.node.style.transform = offset ? `translateY(${offset}px)` : "";
    });
  };

  const onMove = (ev) => {
    if (!dragging) {
      if (Math.abs(ev.clientY - e.clientY) < EVAL_DRAG_PX) return;
      dragging = true;
      item.classList.add("is-dragging");
    }
    const wanted = ev.clientY - list.getBoundingClientRect().top - grab;
    const top = Math.max(minTop, Math.min(wanted, maxTop));
    item.style.transform = `translateY(${top - own.top}px)`;

    const bottom = top + own.height;
    let k = from;
    for (let i = from + 1; i < items.length; i += 1) {
      if (bottom > middles[i]) k += 1;
    }
    for (let i = from - 1; i >= 0; i -= 1) {
      if (top < middles[i]) k -= 1;
    }
    if (k !== to) {
      to = k;
      openSlot(k);
    }
  };

  const finish = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", finish);
    window.removeEventListener("pointercancel", finish);
    if (!dragging) return;
    evalClickBlocked = true;
    if (!item.isConnected) return;
    item.classList.remove("is-dragging");
    item.classList.add("is-settling");
    item.style.transform = to === from ? "" : `translateY(${slotTop(to) - own.top}px)`;
    if (to === from) {
      openSlot(from);
      setTimeout(() => item.classList.remove("is-settling"), EVAL_DROP_MS);
      return;
    }
    moveEvaluation(course, from, to, EVAL_DROP_MS);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", finish);
  window.addEventListener("pointercancel", finish);
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
    try {
      node.releasePointerCapture(e.pointerId);
    } catch {
    }
    node.removeEventListener("pointermove", onMove);
    node.removeEventListener("pointerup", onUp);
    node.removeEventListener("pointercancel", onUp);
    node.classList.remove("is-dragging");
    clearHighlight();

    const changed =
      cur.jour !== jour0 ||
      cur.start !== startMin0 ||
      cur.dur !== dur0;
    if (!moved || !changed) {
      renderBlocks(false);
      if (!moved) selectCourse(occ.courseId, occ);
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
  if (occ.kind === "exam") {
    const week = currentWeek();
    apiPost("/exam/set", {
      session: state.session,
      courseId: occ.courseId,
      date: (week && week.dates[cur.jour]) || occ.date,
      heureDebut: toHHMM(cur.start),
      heureFin: toHHMM(cur.start + cur.dur),
    }).then(() => toast("Examen final déplacé"));
    return;
  }
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
  if (occ.overridden) {
    renderBlocks(false);
    setStatus("Prêt.", false);
    toast(
      "Cette séance a été modifiée pour cette semaine. Passez à « Cette séance » " +
        "pour la déplacer, ou rétablissez-la d'abord.",
      true,
    );
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
  if (occ.kind === "exam") {
    apiPost("/exam/reset", {
      session: state.session,
      courseId: occ.courseId,
    }).then(() => toast("Examen final rétabli"));
    return;
  }
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

const ADMIN = "/admin/failures";

const NO_FAILURES = {
  latencyMs: 0,
  errorRate: 0,
  failEndpoints: [],
  timeoutEndpoints: [],
  timeoutDurationS: 60,
  malformed: false,
  authRequired: false,
};

const latencyMax = (raw) => {
  const parts = String(raw ?? "").split("-");
  const hi = Number(parts[parts.length - 1]);
  return Number.isFinite(hi) ? hi : 0;
};

const percent = (rate) => Math.round(rate * 100);
const endpointLabel = (name) => (name === "*" ? "tous les endpoints" : name);

const countLabel = (names, one, many) =>
  names.includes("*")
    ? `tous les endpoints ${many}`
    : `${names.length} endpoint${names.length > 1 ? "s" : ""} ${names.length > 1 ? many : one}`;

function injectionInput(field, value, size, unit, label) {
  return `<fluent-text-input class="injection__input injection__input--${size}" control-size="small"
      appearance="filled-lighter" data-field="${field}" value="${escapeHtml(value)}"
      aria-label="${label}"></fluent-text-input>${
        unit ? `<span class="injection__unit">${unit}</span>` : ""
      }`;
}

function chipList(field, names) {
  const chips = names
    .map(
      (name) => `<span class="chip">${escapeHtml(endpointLabel(name))}
        <button type="button" class="chip__x" data-chip="${field}" data-name="${escapeHtml(name)}"
          aria-label="Retirer ${escapeHtml(name)}">${icon("dismiss", 12)}</button>
      </span>`
    )
    .join("");
  return `${chips}<button type="button" class="chip chip--add" data-add="${field}"
      aria-label="Ajouter un endpoint">${icon("add", 12)}Endpoint</button>`;
}

function endpointField(chipsId) {
  return `<fluent-field label-position="above">
      <fluent-label slot="label">Endpoints</fluent-label>
      <div slot="input" class="picker-row">
        <fluent-dropdown id="fEndpoint" type="combobox" appearance="filled-darker"
          placeholder="listeCours" aria-label="Endpoint"><fluent-listbox></fluent-listbox></fluent-dropdown>
        <fluent-button id="fEndpointAdd" appearance="subtle" icon-only
          title="Ajouter à la liste" aria-label="Ajouter à la liste">${icon("add", 16)}</fluent-button>
      </div>
    </fluent-field>
    <div class="chips chips--staged" id="${chipsId}"></div>`;
}

function numberField(id, label, value, placeholder) {
  return `<fluent-field label-position="above">
      <fluent-label slot="label">${label}</fluent-label>
      <fluent-text-input slot="input" id="${id}" type="number" appearance="filled-darker"
        value="${escapeHtml(value)}" placeholder="${placeholder}" aria-label="${label}"></fluent-text-input>
    </fluent-field>`;
}

const FAILURE_KINDS = [
  {
    id: "latency",
    label: "Latence",
    icon: "timer",
    hint: "Retarde chaque réponse de l'API.",
    active: (cfg) => latencyMax(cfg.latencyMs) > 0,
    summary: (cfg) => `${cfg.latencyMs} ms`,
    value: (cfg) =>
      injectionInput("latencyMs", cfg.latencyMs, "md", "ms", "Durée de la latence"),
    clear: () => ({ latencyMs: 0 }),
    form: () =>
      `<fluent-field label-position="above">
        <fluent-label slot="label">Durée en ms (fixe ou min-max)</fluent-label>
        <fluent-text-input slot="input" id="fLatency" appearance="filled-darker"
          placeholder="100-800" aria-label="Durée en ms"></fluent-text-input>
      </fluent-field>`,
    read: () => {
      const raw = el.failureParams.querySelector("#fLatency").value.trim();
      if (!raw) return { error: "Une durée est requise" };
      return { body: { latencyMs: raw } };
    },
  },
  {
    id: "errorRate",
    label: "Erreurs aléatoires",
    icon: "warning",
    hint: "Une part des appels répond 500.",
    active: (cfg) => cfg.errorRate > 0,
    summary: (cfg) => `${percent(cfg.errorRate)} % d'erreurs`,
    value: (cfg) =>
      injectionInput("errorRate", percent(cfg.errorRate), "sm", "%", "Taux d'erreur"),
    clear: () => ({ errorRate: 0 }),
    form: () => numberField("fErrorRate", "Taux en %", "", "30"),
    read: () => {
      const pct = Number(el.failureParams.querySelector("#fErrorRate").value);
      if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
        return { error: "Un taux entre 1 et 100 est requis" };
      }
      return { body: { errorRate: pct / 100 } };
    },
  },
  {
    id: "fail",
    label: "Endpoints en panne",
    icon: "plugDisconnected",
    hint: "Ces endpoints répondent 503.",
    active: (cfg) => cfg.failEndpoints.length > 0,
    summary: (cfg) => countLabel(cfg.failEndpoints, "en panne", "en panne"),
    value: (cfg) => chipList("failEndpoints", cfg.failEndpoints),
    clear: () => ({ failEndpoints: [] }),
    form: () => endpointField("fFailChips"),
    read: (cfg) => {
      const picked = stagedEndpoints();
      if (!picked.length) return { error: "Un endpoint est requis" };
      return { body: { failEndpoints: [...new Set([...cfg.failEndpoints, ...picked])] } };
    },
  },
  {
    id: "timeout",
    label: "Endpoints qui expirent",
    icon: "hourglass",
    hint: "Ces endpoints retiennent la requête, puis répondent 504.",
    active: (cfg) => cfg.timeoutEndpoints.length > 0,
    summary: (cfg) =>
      `${countLabel(cfg.timeoutEndpoints, "qui expire", "qui expirent")} (${cfg.timeoutDurationS} s)`,
    value: (cfg) =>
      `${chipList("timeoutEndpoints", cfg.timeoutEndpoints)}
      <span class="injection__after">après</span>
      ${injectionInput("timeoutDurationS", cfg.timeoutDurationS, "sm", "s", "Délai avant expiration")}`,
    clear: () => ({ timeoutEndpoints: [] }),
    form: (cfg) =>
      endpointField("fTimeoutChips") +
      numberField("fTimeoutDuration", "Délai en s", cfg.timeoutDurationS, "30"),
    read: (cfg) => {
      const picked = stagedEndpoints();
      if (!picked.length) return { error: "Un endpoint est requis" };
      const seconds = Number(el.failureParams.querySelector("#fTimeoutDuration").value);
      if (!Number.isFinite(seconds) || seconds < 0) {
        return { error: "Un délai en secondes est requis" };
      }
      return {
        body: {
          timeoutEndpoints: [...new Set([...cfg.timeoutEndpoints, ...picked])],
          timeoutDurationS: seconds,
        },
      };
    },
  },
  {
    id: "malformed",
    label: "Réponses tronquées",
    icon: "documentError",
    hint: "Le corps de chaque réponse 2xx est coupé en deux.",
    active: (cfg) => cfg.malformed,
    summary: () => "réponses tronquées",
    value: (kind) => `<span class="injection__note">${kind.hint}</span>`,
    clear: () => ({ malformed: false }),
    form: () => "",
    read: () => ({ body: { malformed: true } }),
  },
  {
    id: "auth",
    label: "Authentification requise",
    icon: "lockClosed",
    hint: "Un appel sans en-tête Authorization répond 401.",
    active: (cfg) => cfg.authRequired,
    summary: () => "authentification requise",
    value: (kind) => `<span class="injection__note">${kind.hint}</span>`,
    clear: () => ({ authRequired: false }),
    form: () => "",
    read: () => ({ body: { authRequired: true } }),
  },
];

const kindById = (id) => FAILURE_KINDS.find((k) => k.id === id);
const activeKinds = (cfg) => (cfg ? FAILURE_KINDS.filter((k) => k.active(cfg)) : []);
const parameterless = (kind) => kind.id === "malformed" || kind.id === "auth";

function failureError(data, res) {
  const detail = typeof data.detail === "string" ? data.detail : null;
  return detail || data.error || res.statusText || "Échec de l'opération";
}

async function adminFetch(path, options, message, record = true) {
  const before = state.failures;
  setStatus("Enregistrement…", true);
  try {
    const res = await fetch(`${ADMIN}${path}`, options);
    const data = await res.json();
    if (!res.ok) throw new Error(failureError(data, res));
    if (record && before && !sameFailures(before, data)) {
      state.failuresPast.push({ before, after: data });
      state.failuresFuture = [];
    }
    applyFailures(data);
    setStatus("Enregistré.", false);
    if (message) toast(message);
    return data;
  } catch (err) {
    setStatus("Erreur.", false, true);
    toast(err.message || "Échec de l'opération", true);
    renderFailures();
    throw err;
  }
}

const patchFailures = (body, message, record) =>
  adminFetch(
    "",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    message,
    record
  );

function applyFailures(cfg) {
  state.failures = cfg;
  el.failuresDot.hidden = !activeKinds(cfg).length;
  renderFailures();
}

const failureFields = (cfg) =>
  Object.fromEntries(Object.keys(NO_FAILURES).map((key) => [key, cfg[key]]));

const sameFailures = (a, b) =>
  JSON.stringify(failureFields(a)) === JSON.stringify(failureFields(b));

const canUndoFailures = () => {
  const change = state.failuresPast.at(-1);
  return !!change && !!state.failures && sameFailures(change.after, state.failures);
};

const canRedoFailures = () => {
  const change = state.failuresFuture.at(-1);
  return !!change && !!state.failures && sameFailures(change.before, state.failures);
};

function renderFailureHistory() {
  el.failuresUndoBtn.disabled = !canUndoFailures();
  el.failuresRedoBtn.disabled = !canRedoFailures();
}

function stepFailures(from, to, target, message) {
  const change = from.pop();
  renderFailureHistory();
  patchFailures(failureFields(change[target]), message, false).then(
    () => {
      to.push(change);
      renderFailureHistory();
    },
    () => {
      from.push(change);
      renderFailureHistory();
    }
  );
}

function undoFailures() {
  if (!canUndoFailures()) return;
  stepFailures(state.failuresPast, state.failuresFuture, "before", "Modification annulée");
}

function redoFailures() {
  if (!canRedoFailures()) return;
  stepFailures(state.failuresFuture, state.failuresPast, "after", "Modification rétablie");
}

async function loadFailures() {
  try {
    if (!state.endpoints.length) {
      const res = await fetch(`${ADMIN}/options`);
      if (res.ok) {
        const options = await res.json();
        state.endpoints = options.endpoints || [];
        state.presets = options.presets || [];
        renderPresets();
      }
    }
    const res = await fetch(ADMIN);
    if (!res.ok) throw new Error(res.statusText);
    applyFailures(await res.json());
  } catch (err) {
    if (state.view === "failures") {
      setStatus("Impossible de lire les pannes.", false, true);
      toast(err.message || "Serveur injoignable", true);
    }
  }
}

function injectionHtml(kind, cfg) {
  return `<li class="injection" data-kind="${kind.id}">
      <span class="injection__icon">${icon(kind.icon, 16)}</span>
      <span class="injection__name" title="${escapeHtml(kind.hint)}">${kind.label}</span>
      <span class="injection__value">${kind.value(parameterless(kind) ? kind : cfg)}</span>
      <fluent-button class="injection__x" appearance="subtle" size="small" icon-only
        data-remove="${kind.id}" title="Retirer la panne"
        aria-label="Retirer : ${escapeHtml(kind.label)}">${icon("delete", 16)}</fluent-button>
    </li>`;
}

function renderInjections(cfg) {
  const kinds = activeKinds(cfg);
  el.failuresResetBtn.disabled = !kinds.length;
  el.injectionEmpty.hidden = kinds.length > 0;
  el.injectionList.innerHTML = kinds.map((kind) => injectionHtml(kind, cfg)).join("");
  wireInjections(cfg);
}

function wireInjections(cfg) {
  el.injectionList.querySelectorAll("[data-remove]").forEach((node) => {
    const kind = kindById(node.dataset.remove);
    node.addEventListener("click", () => patchFailures(kind.clear(), "Panne retirée"));
  });
  el.injectionList.querySelectorAll("[data-chip]").forEach((node) => {
    const { chip: fieldName, name } = node.dataset;
    node.addEventListener("click", () =>
      patchFailures(
        { [fieldName]: cfg[fieldName].filter((endpoint) => endpoint !== name) },
        `${endpointLabel(name)} retiré`
      )
    );
  });
  el.injectionList.querySelectorAll("[data-add]").forEach((node) => {
    const kind = node.dataset.add === "failEndpoints" ? "fail" : "timeout";
    node.addEventListener("click", () => openFailureDialog(kind));
  });
  el.injectionList.querySelectorAll("[data-field]").forEach((node) => {
    node.addEventListener("change", () =>
      commitFailureField(node.dataset.field, node.value)
    );
    node.addEventListener("keydown", (e) => {
      if (e.key === "Enter") node.blur();
    });
  });
}

function commitFailureField(fieldName, value) {
  if (fieldName === "errorRate") {
    const pct = Number(value);
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
      toast("Un taux entre 0 et 100 est requis", true);
      renderFailures();
      return;
    }
    patchFailures({ errorRate: pct / 100 }, "Panne modifiée");
    return;
  }
  if (fieldName === "timeoutDurationS") {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) {
      toast("Un délai en secondes est requis", true);
      renderFailures();
      return;
    }
    patchFailures({ timeoutDurationS: seconds }, "Panne modifiée");
    return;
  }
  patchFailures({ [fieldName]: String(value).trim() }, "Panne modifiée");
}

function presetSummary(config) {
  const cfg = { ...NO_FAILURES, ...config };
  return FAILURE_KINDS.filter((kind) => kind.active(cfg))
    .map((kind) => kind.summary(cfg))
    .join(" · ");
}

function samePreset(config, cfg) {
  if (!cfg) return false;
  const wanted = { ...NO_FAILURES, ...config };
  return FAILURE_KINDS.every(
    (kind) => kind.active(wanted) === kind.active(cfg) && kind.summary(wanted) === kind.summary(cfg)
  );
}

function renderPresets() {
  el.presetList.innerHTML = state.presets
    .map(
      (preset) => `<li>
        <button type="button" class="preset${
          samePreset(preset.config, state.failures) ? " is-active" : ""
        }" data-preset="${escapeHtml(preset.name)}" title="${escapeHtml(preset.description)}">
          <span class="preset__name">${escapeHtml(preset.name)}</span>
          <span class="preset__summary">${escapeHtml(presetSummary(preset.config))}</span>
        </button>
      </li>`
    )
    .join("");
  el.presetList.querySelectorAll("[data-preset]").forEach((node) => {
    const name = node.dataset.preset;
    node.addEventListener("click", () =>
      adminFetch(
        "/preset",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        },
        `Scénario ${name} appliqué`
      )
    );
  });
}

function renderFailures() {
  const cfg = state.failures;
  if (!cfg) return;
  renderInjections(cfg);
  renderFailureHistory();
  if (state.presets.length) renderPresets();
}

const stagedEndpoints = () => {
  const picker = el.failureParams.querySelector("#fEndpoint");
  const typed = String(dropdownValue(picker) || "").trim();
  return [...new Set(typed ? [...state.staged, typed] : state.staged)];
};

function renderStagedChips() {
  const host = el.failureParams.querySelector(".chips--staged");
  if (!host) return;
  host.innerHTML = state.staged
    .map(
      (name) => `<span class="chip">${escapeHtml(endpointLabel(name))}
        <button type="button" class="chip__x" data-staged="${escapeHtml(name)}"
          aria-label="Retirer ${escapeHtml(name)}">${icon("dismiss", 12)}</button>
      </span>`
    )
    .join("");
  host.querySelectorAll("[data-staged]").forEach((node) => {
    node.addEventListener("click", () => {
      state.staged = state.staged.filter((name) => name !== node.dataset.staged);
      renderStagedChips();
    });
  });
}

function stageEndpoint() {
  const picker = el.failureParams.querySelector("#fEndpoint");
  const name = String(dropdownValue(picker) || "").trim();
  if (!name) return;
  if (!state.staged.includes(name)) state.staged.push(name);
  picker.value = "";
  if (picker.control) picker.control.value = "";
  renderStagedChips();
  picker.focus();
}

function renderFailureForm() {
  const kind = kindById(state.failureKind);
  const cfg = state.failures || NO_FAILURES;
  el.failureParams.innerHTML = kind.form(cfg);
  el.failureHint.textContent = kind.hint;
  const picker = el.failureParams.querySelector("#fEndpoint");
  if (!picker) return;
  fillDropdown(
    picker,
    ["*", ...state.endpoints].map((name) => ({ value: name, text: endpointLabel(name) })),
    undefined,
    { freeform: true }
  );
  el.failureParams.querySelector("#fEndpointAdd").addEventListener("click", stageEndpoint);
  picker.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    stageEndpoint();
  });
  renderStagedChips();
}

function openFailureDialog(kindId) {
  state.failureKind = kindId || state.failureKind;
  state.staged = [];
  fillDropdown(
    el.fFailureKind,
    FAILURE_KINDS.map((kind) => ({ value: kind.id, text: kind.label })),
    state.failureKind
  );
  renderFailureForm();
  el.failureDialog.show();
  setTimeout(() => {
    const first = el.failureParams.querySelector("fluent-dropdown, fluent-text-input");
    if (first) first.focus();
  }, 40);
}

function submitFailure() {
  const kind = kindById(state.failureKind);
  const { body, error } = kind.read(state.failures || NO_FAILURES);
  if (error) {
    toast(error, true);
    return;
  }
  patchFailures(body, "Panne enregistrée").then(() => el.failureDialog.hide());
}

const CALLS = "/admin/calls";
const CALLS_POLL_MS = 1000;

const CALL_FAILURES = {
  latency: (failure) => `Latence ${fmtDuration(failure.ms)}`,
  errorRate: () => "Erreur aléatoire",
  fail: () => "Endpoint en panne",
  timeout: (failure) => `Expiration après ${decimal(failure.seconds)} s`,
  malformed: () => "Réponse tronquée",
  auth: () => "Authentification manquante",
};

const decimal = (value, digits = 1) =>
  String(Number(value.toFixed(digits))).replace(".", ",");

function fmtDuration(ms) {
  if (ms < 10) return `${decimal(ms)} ms`;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${decimal(ms / 1000)} s`;
}

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${decimal(bytes / 1024)} ko`;
  return `${decimal(bytes / (1024 * 1024))} Mo`;
}

const pad = (value, width = 2) => String(value).padStart(width, "0");

function fmtClock(iso) {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(
    d.getMilliseconds(),
    3
  )}`;
}

const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

const isCall = (entry) => entry.kind === "call";
const isPending = (entry) => isCall(entry) && entry.status == null;

const callKey = (call) => JSON.stringify([call.endpoint, Object.entries(call.params).sort()]);

function repeatsOf(calls) {
  const totals = new Map();
  calls.forEach((call) => {
    const key = callKey(call);
    totals.set(key, (totals.get(key) || 0) + 1);
  });
  const seen = new Map();
  const firsts = new Map();
  return new Map(
    calls.map((call) => {
      const key = callKey(call);
      const nth = (seen.get(key) || 0) + 1;
      seen.set(key, nth);
      if (nth === 1) firsts.set(key, call.id);
      return [call.id, { nth, total: totals.get(key), group: String(firsts.get(key)) }];
    })
  );
}

function markerSections(entries) {
  const sections = new Map();
  let current = null;
  entries.forEach((entry) => {
    if (!isCall(entry)) {
      current = { calls: 0, bytes: 0 };
      sections.set(entry.id, current);
    } else if (current) {
      current.calls += 1;
      current.bytes += entry.bytes || 0;
    }
  });
  return sections;
}

function statusHtml(status) {
  if (status == null) return `<span class="status is-pending">en cours</span>`;
  const tone = status >= 500 ? "error" : status >= 400 ? "warn" : "ok";
  return `<span class="status status--${tone}">${status}</span>`;
}

const paramsHtml = (params) =>
  Object.entries(params)
    .map(
      ([key, value]) =>
        `<span class="param"><span class="param__key">${escapeHtml(key)}=</span>${escapeHtml(
          value
        )}</span>`
    )
    .join(" ");

function callFailureHtml(failure) {
  const label = CALL_FAILURES[failure.kind]?.(failure) ?? failure.kind;
  return `<span class="call-failure">${escapeHtml(label)}</span>`;
}

function repeatHtml({ nth, total }) {
  return `<span class="repeat" title="Appel identique ${nth} sur ${total} (même endpoint, mêmes paramètres)">${nth}/${total}</span>`;
}

function callRowHtml(call, repeat) {
  const pending = call.status == null;
  const classes = ["call", repeat.nth > 1 ? "is-repeat" : "", pending ? "is-pending" : ""];
  const group = repeat.total > 1 ? ` data-group="${repeat.group}"` : "";
  return `<tr class="${classes.join(" ").trim()}" data-id="${call.id}"${group}>
      <td class="calls__time">${fmtClock(call.time)}</td>
      <td class="calls__endpoint" title="${escapeHtml(call.path)}"><span class="calls__name">${escapeHtml(
        call.endpoint || call.path
      )}</span>${repeat.total > 1 ? repeatHtml(repeat) : ""}</td>
      <td class="calls__params">${paramsHtml(call.params)}</td>
      <td class="calls__num calls__status">${statusHtml(call.status)}</td>
      <td class="calls__num calls__duration">${pending ? "" : fmtDuration(call.durationMs)}</td>
      <td class="calls__num calls__size">${pending ? "" : fmtBytes(call.bytes)}</td>
      <td class="calls__failures">${call.failures.map(callFailureHtml).join(", ")}</td>
    </tr>`;
}

function markerRowHtml(marker, section) {
  const summary = section.calls
    ? `${plural(section.calls, "appel")} · ${fmtBytes(section.bytes)}`
    : "aucun appel";
  return `<tr class="marker" data-id="${marker.id}">
      <td class="calls__time">${fmtClock(marker.time)}</td>
      <td colspan="5"><span class="marker__label">${escapeHtml(
        marker.label
      )}</span><span class="marker__summary">${summary}</span></td>
      <td class="marker__actions"><button type="button" class="marker__x" data-remove-marker="${
        marker.id
      }" title="Retirer le marqueur" aria-label="Retirer ${escapeHtml(marker.label)}">${icon(
        "dismiss",
        12
      )}</button></td>
    </tr>`;
}

function endpointStats(calls, repeats) {
  const rows = new Map();
  calls.forEach((call) => {
    const row = rows.get(call.endpoint) || {
      endpoint: call.endpoint,
      calls: 0,
      repeated: 0,
      done: 0,
      bytes: 0,
    };
    row.calls += 1;
    if (repeats.get(call.id).nth > 1) row.repeated += 1;
    if (call.status != null) {
      row.done += 1;
      row.bytes += call.bytes;
    }
    rows.set(call.endpoint, row);
  });
  return [...rows.values()].sort(
    (a, b) => b.calls - a.calls || a.endpoint.localeCompare(b.endpoint)
  );
}

const statCells = (row) => `
      <td class="endpoint-stats__num">${row.calls}</td>
      <td class="endpoint-stats__num endpoint-stats__repeated">${row.repeated || ""}</td>
      <td class="endpoint-stats__num">${row.done ? fmtBytes(row.bytes) : ""}</td>`;

function renderEndpointStats(calls, repeats) {
  const rows = endpointStats(calls, repeats);
  const total = rows.reduce(
    (sum, row) => ({
      calls: sum.calls + row.calls,
      repeated: sum.repeated + row.repeated,
      done: sum.done + row.done,
      bytes: sum.bytes + row.bytes,
    }),
    { calls: 0, repeated: 0, done: 0, bytes: 0 }
  );
  el.endpointStats.hidden = !total.calls;
  el.endpointStatsEmpty.hidden = total.calls > 0;
  el.endpointStatsRows.innerHTML = rows
    .map(
      (row) => `<tr data-endpoint="${escapeHtml(row.endpoint)}">
        <th scope="row" title="${escapeHtml(row.endpoint)}">${escapeHtml(row.endpoint)}</th>${statCells(
          row
        )}
      </tr>`
    )
    .join("");
  el.callsTotal.innerHTML = `<th scope="row">Total</th>${statCells(total)}`;
}

function markCallGroup() {
  el.callRows
    .querySelectorAll("tr[data-group]")
    .forEach((row) => row.classList.toggle("is-grouped", row.dataset.group === state.callsGroup));
}

function hoverCallGroup(group) {
  if (state.callsGroup === group) return;
  state.callsGroup = group;
  markCallGroup();
}

function renderCalls(stick) {
  const board = el.callsBoard;
  const atBottom = stick || board.scrollHeight - board.scrollTop - board.clientHeight < 24;
  const entries = state.calls;
  const calls = entries.filter(isCall);
  const repeats = repeatsOf(calls);
  const sections = markerSections(entries);
  el.callRows.innerHTML = entries
    .map((entry) =>
      isCall(entry)
        ? callRowHtml(entry, repeats.get(entry.id))
        : markerRowHtml(entry, sections.get(entry.id))
    )
    .join("");
  markCallGroup();
  el.callsTable.hidden = !entries.length;
  el.callsEmpty.hidden = entries.length > 0;
  el.callsClearBtn.disabled = !entries.length;
  el.callsExportBtn.disabled = !entries.length;
  renderEndpointStats(calls, repeats);
  if (atBottom) board.scrollTop = board.scrollHeight;
}

function applyCalls({ entries, firstId }, after, stick) {
  const known = state.calls.filter((entry) => entry.id <= after);
  const kept = known.filter((entry) => entry.id >= firstId);
  const replaced = state.calls.slice(known.length);
  const changed =
    kept.length !== known.length || JSON.stringify(entries) !== JSON.stringify(replaced);
  state.calls = [...kept, ...entries];
  if (changed || stick) renderCalls(stick);
}

let callsTimer = null;

function scheduleCallsPoll() {
  clearTimeout(callsTimer);
  callsTimer =
    state.view === "calls" && !document.hidden
      ? setTimeout(() => loadCalls(), CALLS_POLL_MS)
      : null;
}

async function loadCalls(stick) {
  const seq = ++state.callsSeq;
  const pending = state.calls.find(isPending);
  const last = state.calls.at(-1);
  const after = pending ? pending.id - 1 : last ? last.id : 0;
  try {
    const res = await fetch(`${CALLS}?after=${after}`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    if (seq !== state.callsSeq) return;
    applyCalls(data, after, stick);
    if (state.callsFailed) {
      state.callsFailed = false;
      setStatus("Prêt.", false);
    }
  } catch (err) {
    if (seq !== state.callsSeq) return;
    if (!state.callsFailed) {
      state.callsFailed = true;
      setStatus("Impossible de lire le journal des appels.", false, true);
    }
  }
  scheduleCallsPoll();
}

async function changeCalls(path, options, message, stick = true) {
  setStatus("Enregistrement…", true);
  let saved = false;
  try {
    const res = await fetch(`${CALLS}${path}`, options);
    const data = await res.json();
    if (!res.ok) throw new Error(failureError(data, res));
    setStatus("Enregistré.", false);
    toast(message);
    saved = true;
  } catch (err) {
    setStatus("Erreur.", false, true);
    toast(err.message || "Échec de l'opération", true);
  }
  await loadCalls(stick);
  return saved;
}

function exportCalls() {
  if (!state.calls.length) return;
  const now = new Date();
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-${pad(
    now.getHours()
  )}${pad(now.getMinutes())}`;
  const body = JSON.stringify({ entries: state.calls, firstId: state.calls[0].id }, null, 2);
  const url = URL.createObjectURL(new Blob([body], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `api-calls-${stamp}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url));
}

function addMarker() {
  const typed = String(el.markerLabel.value || "").trim();
  const markers = state.calls.filter((entry) => !isCall(entry));
  const labels = new Set(markers.map((marker) => marker.label));
  let number = markers.length + 1;
  while (labels.has(`Marqueur ${number}`)) number += 1;
  const label = typed || `Marqueur ${number}`;
  changeCalls(
    "/marker",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    },
    "Marqueur ajouté"
  ).then((saved) => {
    if (saved) el.markerLabel.value = "";
  });
}

async function removeMarker(button) {
  const id = Number(button.dataset.removeMarker);
  button.disabled = true;
  const removed = await changeCalls(
    `/marker/${id}`,
    { method: "DELETE" },
    "Marqueur retiré",
    false
  );
  if (removed) state.calls = state.calls.filter((entry) => entry.id !== id);
  renderCalls();
}

const VIEWS = {
  schedule: {
    tab: "viewSchedule",
    title: "Horaire",
    panes: [el.scheduleView, el.scheduleControls, el.scheduleToolbar],
  },
  failures: {
    tab: "viewFailures",
    title: "Pannes",
    panes: [el.failuresView, el.failuresToolbar],
  },
  calls: {
    tab: "viewCalls",
    title: "Logs",
    panes: [el.callsView, el.callsToolbar],
  },
};

function setView(view) {
  const target = VIEWS[view];
  if (!target) return;
  if (el.viewToggle.activeid !== target.tab) el.viewToggle.activeid = target.tab;
  if (state.view === view) return;
  state.view = view;
  Object.entries(VIEWS).forEach(([name, { panes }]) =>
    panes.forEach((pane) => (pane.hidden = name !== view))
  );
  document.title = `${target.title} - ÉTS Mock`;
  if (view === "schedule" && state.data) {
    renderScaffold();
    renderBlocks(false);
  }
  if (view === "failures") loadFailures();
  if (view === "calls") loadCalls(true);
  else scheduleCallsPoll();
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
el.detailSelect.addEventListener("change", () =>
  selectCourse(dropdownValue(el.detailSelect))
);
el.viewToggle.addEventListener("change", (e) => {
  const view = e.detail && e.detail.dataset ? e.detail.dataset.view : null;
  if (view) setView(view);
});
el.fFailureKind.addEventListener("change", () => {
  state.failureKind = dropdownValue(el.fFailureKind) || "latency";
  state.staged = [];
  renderFailureForm();
});
el.failureAddBtn.addEventListener("click", () => openFailureDialog());
el.failureForm.addEventListener("submit", (e) => {
  e.preventDefault();
  submitFailure();
});
el.failureSubmit.addEventListener("click", submitFailure);
el.failureDialog
  .querySelectorAll("[data-close-failure]")
  .forEach((n) => n.addEventListener("click", () => el.failureDialog.hide()));
el.failuresResetBtn.addEventListener("click", () =>
  adminFetch("", { method: "DELETE" }, "Pannes réinitialisées")
);
el.failuresUndoBtn.addEventListener("click", undoFailures);
el.failuresRedoBtn.addEventListener("click", redoFailures);
el.callsClearBtn.addEventListener("click", () =>
  changeCalls("", { method: "DELETE" }, "Journal effacé")
);
el.callsExportBtn.addEventListener("click", exportCalls);
el.markerAddBtn.addEventListener("click", addMarker);
el.markerLabel.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  addMarker();
});
el.callRows.addEventListener("mouseover", (e) =>
  hoverCallGroup(e.target.closest("tr[data-group]")?.dataset.group ?? null)
);
el.callRows.addEventListener("mouseleave", () => hoverCallGroup(null));
el.callRows.addEventListener("click", (e) => {
  const button = e.target.closest("[data-remove-marker]");
  if (button) removeMarker(button);
});
document.addEventListener("visibilitychange", () => {
  if (state.view !== "calls") return;
  if (document.hidden) scheduleCallsPoll();
  else loadCalls();
});
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

const setInputModality = (modality) => {
  document.documentElement.dataset.modality = modality;
};

document.addEventListener("pointerdown", () => setInputModality("pointer"), true);

document.addEventListener(
  "keydown",
  (e) => {
    if (!e.ctrlKey && !e.altKey && !e.metaKey) setInputModality("keyboard");
  },
  true
);

const TEXT_ENTRY =
  'textarea, input:not([type="checkbox"]), fluent-text-input, fluent-dropdown[type="combobox"], fluent-dialog';

document.addEventListener("keydown", (e) => {
  if (state.view === "calls") return;
  const inDialog = !!document.activeElement?.closest?.("fluent-dialog");
  const typing =
    inDialog ||
    /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "") ||
    !!document.activeElement?.closest?.("fluent-dropdown, fluent-text-input");
  const editingText = !!document.activeElement?.closest?.(TEXT_ENTRY);
  const mod = e.ctrlKey || e.metaKey;
  const failures = state.view === "failures";
  const undoBtn = failures ? el.failuresUndoBtn : el.undoBtn;
  const redoBtn = failures ? el.failuresRedoBtn : el.redoBtn;
  if (mod && !editingText && e.key.toLowerCase() === "z") {
    e.preventDefault();
    if (e.shiftKey) {
      if (!redoBtn.disabled) redoBtn.click();
    } else if (!undoBtn.disabled) undoBtn.click();
  } else if (mod && !editingText && e.key.toLowerCase() === "y") {
    e.preventDefault();
    if (!redoBtn.disabled) redoBtn.click();
  } else if (failures) {
    return;
  } else if ((e.key === "Delete" || e.key === "Backspace") && !typing) {
    if (occurrenceMode()) {
      const occ = selectedOccurrence();
      if (occ && occ.blockId && occ.kind !== "exam" && !occ.canceled) {
        e.preventDefault();
        cancelOccurrence(occ);
      }
    } else if (state.selectedCourseId) {
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
  if (state.data && state.view === "schedule") {
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
    loadFailures();
  } catch (err) {
    setStatus("Impossible de contacter le serveur.", false, true);
    toast(err.message || "Serveur injoignable", true);
  }
})();
