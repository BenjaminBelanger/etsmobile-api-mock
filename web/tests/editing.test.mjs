import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, flush, mount } from "./harness.mjs";

const OCCURRENCE_TAB = "scopeOccurrence";

async function occurrenceMode(app) {
  app.fire(app.byId("scopeToggle"), "change", { detail: app.byId(OCCURRENCE_TAB) });
  await flush();
}

async function withUndo() {
  const state = baseState();
  state.canUndo = true;
  state.canRedo = true;
  return mount({ state });
}

describe("dragging a block", () => {
  test("moves the whole series", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.deepEqual(app.server.lastCall("/block/move").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      jour: "3",
      heureDebut: "10:00",
    });
    assert.equal(app.status(), "Enregistré.");
    app.close();
  });

  test("moves only the shown séance in the séance scope", async () => {
    const app = await mount();
    await occurrenceMode(app);

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.server.lastCall("/block/move"), null);
    assert.deepEqual(app.server.lastCall("/occurrence/set").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      date: "2026-01-05",
      jour: "3",
      heureDebut: "10:00",
      heureFin: "13:00",
    });
    assert.equal(app.toast().text, "Séance modifiée cette semaine");
    app.close();
  });

  test("refuses to drag a séance that was edited for one week", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await flush();

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.server.lastCall("/block/move"), null);
    assert.equal(app.toast().hidden, false);
    assert.equal(app.toast().intent, "error");
    assert.match(app.toast().text, /Cette séance/);
    assert.equal(app.status(), "Prêt.");
    app.close();
  });

  test("moves the final exam to the day it was dropped on", async () => {
    const app = await mount();
    app.select(app.byId("weekSelect"), "3");
    await flush();

    await app.drag("LOG430-02:exam", { dx: 40, dy: 64.8 });

    assert.deepEqual(app.server.lastCall("/exam/set").body, {
      session: "H2026",
      courseId: "LOG430-02",
      date: "2026-01-19",
      heureDebut: "14:30",
      heureFin: "17:30",
    });
    assert.equal(app.toast().text, "Examen final déplacé");
    app.close();
  });

  test("resizes from the bottom handle", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dy: 64.8, handle: ".block__handle--bottom" });

    assert.deepEqual(app.server.lastCall("/block/resize").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      heureDebut: "09:00",
      heureFin: "13:00",
    });
    app.close();
  });

  test("resizes from the top handle", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dy: -64.8, handle: ".block__handle--top" });

    assert.deepEqual(app.server.lastCall("/block/resize").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      heureDebut: "08:00",
      heureFin: "12:00",
    });
    app.close();
  });

  test("never drags a block out of the day", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dy: -1000 });

    assert.equal(app.server.lastCall("/block/move").body.heureDebut, "08:00");
    app.close();
  });

  test("saves nothing when the block does not move", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    assert.equal(app.server.calls.length, 1);
    app.close();
  });

  test("selects the course when a block is clicked", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    assert.ok(app.blockFor("LOG430-02:0").classList.contains("is-selected"));
    assert.equal(app.text(".detail__title"), "Architecture logicielle");
    app.close();
  });

  test("clicking the board clears the selection", async () => {
    const app = await mount();
    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    app.mouse(app.byId("board"), "pointerdown", {});
    await flush();

    assert.equal(app.query(".block.is-selected"), null);
    app.close();
  });

  test("a cancelled séance cannot be dragged", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await flush();

    await app.drag("LOG410-01:0", { dx: 240, dy: 64.8 });

    assert.equal(app.server.calls.length, 1);
    app.close();
  });
});

describe("block buttons", () => {
  test("deletes the course from the block", async () => {
    const app = await mount();

    await app.click(app.blockFor("LOG430-02:0").querySelector(".block__del"));

    assert.deepEqual(app.server.lastCall("/course/delete").body, {
      session: "H2026",
      courseId: "LOG430-02",
    });
    assert.equal(app.toast().text, "Cours déplacé vers la corbeille");
    app.close();
  });

  test("cancels the séance in the séance scope", async () => {
    const app = await mount();
    await occurrenceMode(app);

    await app.click(app.blockFor("LOG430-02:0").querySelector(".block__del"));

    assert.equal(app.server.lastCall("/course/delete"), null);
    assert.deepEqual(app.server.lastCall("/occurrence/cancel").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      date: "2026-01-05",
    });
    assert.equal(app.toast().text, "Séance annulée cette semaine");
    app.close();
  });

  test("restores an edited séance to the series", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await occurrenceMode(app);

    await app.click(app.blockFor("LOG430-02:0").querySelector(".block__reset"));

    assert.deepEqual(app.server.lastCall("/occurrence/reset").body, {
      session: "H2026",
      blockId: "LOG430-02:0",
      date: "2026-01-13",
    });
    assert.equal(app.toast().text, "Séance rétablie au modèle");
    app.close();
  });

  test("restores a cancelled séance", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await occurrenceMode(app);

    await app.click(app.blockFor("LOG410-01:0").querySelector(".block__reset"));

    assert.equal(app.toast().text, "Séance rétablie");
    app.close();
  });

  test("restores the generated exam", async () => {
    const state = baseState();
    for (const row of state.occurrences) {
      if (row.kind === "exam") row.overridden = true;
    }
    const app = await mount({ state });
    app.select(app.byId("weekSelect"), "3");
    await flush();

    await app.click(app.blockFor("LOG430-02:exam").querySelector(".block__reset"));

    assert.deepEqual(app.server.lastCall("/exam/reset").body, {
      session: "H2026",
      courseId: "LOG430-02",
    });
    assert.equal(app.toast().text, "Examen final rétabli");
    app.close();
  });
});

describe("keyboard", () => {
  test("undoes with ctrl+z", async () => {
    const app = await withUndo();

    app.key("z", { ctrlKey: true });
    await flush();

    assert.equal(app.server.called("/undo").length, 1);
    app.close();
  });

  test("redoes with ctrl+shift+z and ctrl+y", async () => {
    const app = await withUndo();

    app.key("z", { ctrlKey: true, shiftKey: true });
    app.key("y", { ctrlKey: true });
    await flush();

    assert.equal(app.server.called("/redo").length, 2);
    app.close();
  });

  test("does nothing when there is nothing to undo", async () => {
    const app = await mount();

    app.key("z", { ctrlKey: true });
    app.key("y", { ctrlKey: true });
    await flush();

    assert.equal(app.server.calls.length, 1);
    app.close();
  });

  test("deletes the selected course with the delete key", async () => {
    const app = await mount();
    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    app.key("Delete");
    await flush();

    assert.deepEqual(app.server.lastCall("/course/delete").body, {
      session: "H2026",
      courseId: "LOG430-02",
    });
    app.close();
  });

  test("cancels the selected séance in the séance scope", async () => {
    const app = await mount();
    await occurrenceMode(app);
    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    app.key("Backspace");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    assert.equal(app.server.lastCall("/occurrence/cancel").body.date, "2026-01-05");
    app.close();
  });

  test("ignores the delete key while typing", async () => {
    const app = await mount();
    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });
    app.byId("fStart").focus();

    app.key("Delete");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    app.close();
  });

  test("clears the selection with escape", async () => {
    const app = await mount();
    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    app.key("Escape");
    await flush();

    assert.equal(app.query(".block.is-selected"), null);
    app.close();
  });
});

describe("toolbar", () => {
  test("undo and redo talk to the server", async () => {
    const app = await withUndo();

    await app.click(app.byId("undoBtn"));
    await app.click(app.byId("redoBtn"));

    assert.equal(app.server.called("/undo").length, 1);
    assert.equal(app.server.called("/redo").length, 1);
    assert.deepEqual(app.server.lastCall("/undo").body, { session: "H2026" });
    app.close();
  });

  test("resetting the session is confirmed first", async () => {
    const app = await mount();

    await app.click(app.byId("resetBtn"));

    assert.equal(app.byId("resetDialog").open, true);
    assert.equal(app.query("#resetText b").textContent, "H2026");
    assert.equal(app.server.lastCall("/reset"), null);

    await app.click(app.byId("resetConfirm"));

    assert.equal(app.byId("resetDialog").open, false);
    assert.deepEqual(app.server.lastCall("/reset").body, { session: "H2026" });
    assert.equal(app.toast().text, "Session réinitialisée");
    app.close();
  });

  test("the reset can be called off", async () => {
    const app = await mount();
    await app.click(app.byId("resetBtn"));

    await app.click(app.query("#resetDialog [data-close-reset]"));

    assert.equal(app.byId("resetDialog").open, false);
    assert.equal(app.server.lastCall("/reset"), null);
    app.close();
  });
});

describe("adding a course", () => {
  test("offers the catalog in the dialog", async () => {
    const app = await mount();

    await app.click(app.byId("addBtn"));

    assert.equal(app.byId("addDialog").open, true);
    assert.deepEqual(
      app.queryAll("#fSigle fluent-option:not([freeform])").map((o) =>
        o.getAttribute("value"),
      ),
      ["ATE100", "COM120", "COM410", "ENT201", "ENT202"],
    );
    assert.deepEqual(
      app.queryAll("#fJour fluent-option").map((o) => o.textContent),
      ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
    );
    app.close();
  });

  test("fills the title of a known course", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));

    app.type(app.byId("fSigle"), "ate100");
    await flush();

    assert.equal(app.byId("fTitre").value, "Intégrité intellectuelle");
    app.close();
  });

  test("sends what the form holds", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));

    app.select(app.byId("fSigle"), "ATE100");
    app.byId("fTitre").value = "Mon cours";
    app.select(app.byId("fJour"), "4");
    app.select(app.byId("fKind"), "labo");
    app.byId("fStart").value = "13:30";
    app.byId("fEnd").value = "16:30";
    await app.click(app.byId("addSubmit"));

    assert.deepEqual(app.server.lastCall("/course/add").body, {
      session: "H2026",
      sigle: "ATE100",
      titre: "Mon cours",
      jour: "4",
      heureDebut: "13:30",
      heureFin: "16:30",
      kind: "labo",
    });
    assert.equal(app.byId("addDialog").open, false);
    assert.equal(app.toast().text, "ATE100 ajouté");
    app.close();
  });

  test("submitting the form adds the course too", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));
    app.select(app.byId("fSigle"), "COM120");

    app.fire(app.byId("addForm"), "submit", { cancelable: true });
    await flush();

    assert.equal(app.server.lastCall("/course/add").body.sigle, "COM120");
    app.close();
  });

  test("refuses a course without a sigle", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));

    await app.click(app.byId("addSubmit"));

    assert.equal(app.server.lastCall("/course/add"), null);
    assert.equal(app.toast().intent, "error");
    assert.equal(app.toast().text, "Un sigle est requis");
    assert.equal(app.byId("addDialog").open, true);
    app.close();
  });

  test("the dialog can be dismissed", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));

    await app.click(app.query("#addDialog [data-close]"));

    assert.equal(app.byId("addDialog").open, false);
    app.close();
  });

  test("the dialog starts empty every time", async () => {
    const app = await mount();
    await app.click(app.byId("addBtn"));
    app.type(app.byId("fSigle"), "ATE100");
    await app.click(app.query("#addDialog [data-close]"));

    await app.click(app.byId("addBtn"));

    assert.equal(app.byId("fTitre").value, "");
    app.close();
  });
});
