import assert from "node:assert/strict";
import { after, describe, test } from "node:test";

import {
  DAY_START_MIN,
  PX_PER_MIN,
  baseState,
  flush,
  heightPx,
  mount,
  topPx,
} from "./harness.mjs";

const WEEK1_MONDAY = "2026-01-05";

async function ui(state) {
  return mount(state ? { state } : {});
}

describe("initial render", () => {
  test("asks the server for the default session", async () => {
    const app = await ui();
    assert.deepEqual(app.server.calls, [
      { path: "/state", query: "session=&lang=fr", method: "GET", body: null },
    ]);
    assert.equal(app.status(), "Prêt.");
    app.close();
  });

  test("draws one column per editable day", async () => {
    const app = await ui();
    const columns = app.queryAll(".daycol");

    assert.deepEqual(
      columns.map((column) => column.dataset.jour),
      ["1", "2", "3", "4", "5", "6"],
    );
    assert.deepEqual(
      app.queryAll(".dayhead__name").map((node) => node.textContent),
      ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
    );
    app.close();
  });

  test("labels each day with the date of the shown week", async () => {
    const app = await ui();
    assert.deepEqual(
      app.queryAll(".dayhead__date").map((node) => node.textContent),
      ["5 janv.", "6 janv.", "7 janv.", "8 janv.", "9 janv.", "10 janv."],
    );
    app.close();
  });

  test("rules the day from the first hour to the last", async () => {
    const app = await ui();
    const labels = app.queryAll(".hourlabel");

    assert.equal(labels[0].textContent, "08:00");
    assert.equal(labels[labels.length - 1].textContent, "22:00");
    assert.equal(labels.length, 29);
    assert.equal(app.queryAll(".hourlabel--on").length, 15);
    app.close();
  });

  test("sizes the grid to the whole day", async () => {
    const app = await ui();
    const expected = (22 * 60 - DAY_START_MIN) * PX_PER_MIN;

    assert.equal(app.byId("grid").style.height, `${expected}px`);
    assert.equal(app.byId("gutter").style.height, `${expected}px`);
    app.close();
  });

  test("lists the sessions that have courses", async () => {
    const app = await ui();
    const options = app.queryAll("#sessionSelect fluent-option");

    assert.deepEqual(
      options.map((option) => option.getAttribute("value")),
      ["A2026", "H2026", "H2025"],
    );
    assert.equal(app.byId("sessionSelect").value, "H2026");
    app.close();
  });

  test("paints the toolbar icons", async () => {
    const app = await ui();
    const painted = app.queryAll("[data-icon]");

    assert.ok(painted.length > 0);
    for (const node of painted) {
      assert.equal(node.querySelector("svg").dataset.name, node.dataset.icon);
    }
    app.close();
  });

  test("mirrors the undo and redo availability", async () => {
    const app = await ui();
    assert.equal(app.byId("undoBtn").disabled, true);
    assert.equal(app.byId("redoBtn").disabled, true);

    const state = baseState();
    state.canUndo = true;
    await app.reload(state);

    assert.equal(app.byId("undoBtn").disabled, false);
    assert.equal(app.byId("redoBtn").disabled, true);
    app.close();
  });
});

describe("blocks", () => {
  test("draws every séance of the shown week", async () => {
    const app = await ui();
    assert.deepEqual(
      app.blocks().map((block) => block.dataset.blockId),
      ["LOG430-02:0", "LOG410-01:0", "LOG410-01:1", "LOG430-02:1"],
    );
    app.close();
  });

  test("places a block at its hour", async () => {
    const app = await ui();
    const block = app.blockFor("LOG430-02:0");

    assert.equal(block.style.top, `${topPx("09:00")}px`);
    assert.equal(block.style.height, `${heightPx("09:00", "12:00") - 3}px`);
    assert.equal(block.closest(".daycol").dataset.jour, "1");
    app.close();
  });

  test("puts a block in the column of its day", async () => {
    const app = await ui();
    assert.equal(
      app.blockFor("LOG410-01:1").closest(".daycol").dataset.jour,
      "3",
    );
    app.close();
  });

  test("names the course, the hours and the room", async () => {
    const app = await ui();
    const block = app.blockFor("LOG430-02:0");

    assert.equal(block.querySelector(".block__code").textContent, "LOG430-02");
    assert.equal(
      block.querySelector(".block__title").textContent,
      "Architecture logicielle",
    );
    assert.equal(
      block.querySelector(".block__time").textContent,
      "09:00 - 12:00",
    );
    assert.equal(block.querySelector(".block__room").textContent, "A-1502");
    app.close();
  });

  test("marks a lab as one", async () => {
    const app = await ui();
    const block = app.blockFor("LOG430-02:1");

    assert.ok(block.classList.contains("is-labo"));
    assert.equal(block.querySelector(".block__kind").textContent, "(Labo)");
    app.close();
  });

  test("gives every séance of one course the same tint", async () => {
    const app = await ui();
    const lecture = app.blockFor("LOG430-02:0").style.getPropertyValue("--bg");
    const lab = app.blockFor("LOG430-02:1").style.getPropertyValue("--bg");
    const other = app.blockFor("LOG410-01:0").style.getPropertyValue("--bg");

    assert.equal(lecture, lab);
    assert.notEqual(lecture, other);
    app.close();
  });

  test("shows the exam of the week as an exam", async () => {
    const app = await ui();
    app.byId("weekNext").click();
    app.byId("weekNext").click();
    await flush();

    const exam = app.blockFor("LOG430-02:exam");
    assert.ok(exam.classList.contains("is-exam"));
    assert.equal(exam.querySelector(".block__badge").textContent, "Examen");
    assert.equal(exam.querySelector(".block__del"), null);
    app.close();
  });

  test("flags a séance moved for one week", async () => {
    const app = await ui();
    app.byId("weekNext").click();
    await flush();

    const moved = app.blockFor("LOG430-02:0");
    assert.ok(moved.classList.contains("is-overridden"));
    assert.equal(moved.querySelector(".block__badge").textContent, "Modifiée");
    assert.equal(moved.closest(".daycol").dataset.jour, "2");
    app.close();
  });

  test("flags a cancelled séance and takes its delete button away", async () => {
    const app = await ui();
    app.byId("weekNext").click();
    await flush();

    const cancelled = app.blockFor("LOG410-01:0");
    assert.ok(cancelled.classList.contains("is-canceled"));
    assert.equal(cancelled.querySelector(".block__badge").textContent, "Annulée");
    assert.equal(cancelled.querySelector(".block__del"), null);
    app.close();
  });

  test("lays overlapping séances side by side", async () => {
    const app = await ui();
    app.byId("weekNext").click();
    await flush();

    const [first, second] = ["LOG430-02:0", "LOG410-01:0"].map(app.blockFor);

    assert.match(first.style.left, /0 \* \(100% - 10px\)/);
    assert.match(second.style.left, /0\.5 \* \(100% - 10px\)/);
    for (const block of [first, second]) {
      assert.match(block.style.width, /0\.5 \* \(100% - 10px\)/);
      assert.equal(block.style.right, "auto");
    }
    app.close();
  });

  test("leaves a lone séance full width", async () => {
    const app = await ui();
    assert.equal(app.blockFor("LOG430-02:0").style.left, "");
    app.close();
  });

  test("escapes course titles", async () => {
    const state = baseState();
    state.courses[0].titre = '<img src=x onerror="boom()">';
    for (const row of state.occurrences) {
      if (row.courseId === state.courses[0].courseId) row.titre = state.courses[0].titre;
    }

    const app = await ui(state);
    const block = app.blockFor("LOG410-01:0");

    assert.equal(block.querySelector("img"), null);
    assert.equal(
      block.querySelector(".block__title").textContent,
      '<img src=x onerror="boom()">',
    );
    app.close();
  });

  test("says when a week is empty", async () => {
    const state = baseState();
    const firstWeek = new Set(Object.values(state.meta.semester.weeks[0].dates));
    state.occurrences = state.occurrences.filter((row) => !firstWeek.has(row.date));
    const app = await ui(state);

    assert.equal(app.blocks().length, 0);
    assert.equal(app.text(".board__empty"), "Aucune séance cette semaine.");
    app.close();
  });

  test("says when the session has no courses at all", async () => {
    const state = baseState();
    state.occurrences = [];
    state.courses = [];
    state.blocks = [];
    const app = await ui(state);

    assert.equal(app.text(".board__empty"), "Aucun cours cette session.");
    app.close();
  });
});

describe("resizing the window", () => {
  test("redraws the week", async () => {
    const app = await mount();
    const before = app.blockFor("LOG430-02:0");

    app.window.dispatchEvent(new app.window.Event("resize"));
    await flush();

    assert.equal(app.queryAll(".daycol").length, 6);
    assert.equal(app.blocks().length, 4);
    assert.notEqual(app.blockFor("LOG430-02:0"), before);
    assert.equal(app.server.calls.length, 1);
    app.close();
  });
});

describe("more courses than tints", () => {
  test("still gives every course a colour", async () => {
    const state = baseState();
    const day = state.meta.semester.weeks[0].dates["1"];
    state.courses = Array.from({ length: 13 }, (_, index) => ({
      courseId: `SIG${index}-01`,
      sigle: `SIG${index}`,
      groupe: "01",
      titre: `Cours ${index}`,
      room: "A-1302",
      cote: "",
      hasSchedule: true,
      blocks: [],
      evaluations: [],
      summary: state.courses[0].summary,
      canResetGrades: false,
      exam: null,
    }));
    state.blocks = [];
    state.occurrences = Array.from({ length: 13 }, (_, index) => ({
      date: day,
      jour: "1",
      blockId: `SIG${index}-01:0`,
      courseId: `SIG${index}-01`,
      sigle: `SIG${index}`,
      groupe: "01",
      titre: `Cours ${index}`,
      room: "A-1302",
      kind: "cours",
      heureDebut: "09:00",
      heureFin: "10:00",
      overridden: false,
      canceled: false,
    }));
    const app = await mount({ state });

    const tints = app.blocks().map((block) => block.style.getPropertyValue("--bg"));
    assert.equal(tints.length, 13);
    for (const tint of tints) assert.match(tint, /^var\(--c\d+-bg\)$/);
    assert.equal(new Set(tints.slice(0, 12)).size, 12);
    app.close();
  });
});

describe("trash", () => {
  test("says when nothing was deleted", async () => {
    const app = await ui();
    assert.equal(app.text(".trash__empty"), "Aucun cours supprimé.");
    app.close();
  });

  test("lists deleted courses with a restore button", async () => {
    const state = baseState();
    state.trash = [
      { courseId: "GTI510-01", sigle: "GTI510", groupe: "01", titre: "Sécurité" },
    ];
    const app = await ui(state);

    assert.equal(app.text(".trash__sigle"), "GTI510-01");
    assert.equal(app.text(".trash__title"), "Sécurité");
    assert.ok(app.query(".trash__restore"));
    app.close();
  });

  test("restores a course from the trash", async () => {
    const state = baseState();
    state.trash = [
      { courseId: "GTI510-01", sigle: "GTI510", groupe: "01", titre: "Sécurité" },
    ];
    const app = await ui(state);

    await app.click(app.query(".trash__restore"));

    assert.deepEqual(app.server.lastCall("/course/restore").body, {
      session: "H2026",
      courseId: "GTI510-01",
    });
    assert.equal(app.toast().text, "GTI510 restauré");
    app.close();
  });
});
