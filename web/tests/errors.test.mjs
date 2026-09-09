import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, flush, mount } from "./harness.mjs";

describe("when the server says no", () => {
  test("an unreachable server is reported on load", async () => {
    const app = await mount({ failLoad: "Serveur en panne" });

    assert.equal(app.status(), "Impossible de contacter le serveur.");
    assert.equal(app.toast().hidden, false);
    assert.equal(app.toast().intent, "error");
    assert.equal(app.toast().text, "Serveur en panne");
    assert.equal(app.blocks().length, 0);
    app.close();
  });

  test("a refused edit is reported and changes nothing", async () => {
    const app = await mount();
    app.server.fail("/block/move", "Ce bloc est déjà sur Lundi");

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.status(), "Erreur.");
    assert.equal(app.toast().intent, "error");
    assert.equal(app.toast().text, "Ce bloc est déjà sur Lundi");
    assert.equal(app.query(".statusbar").dataset.state, "error");
    assert.equal(app.blockFor("LOG430-02:0").closest(".daycol").dataset.jour, "1");
    app.close();
  });

  test("the status bar carries the error state", async () => {
    const app = await mount();
    app.server.fail("/undo", "Rien à annuler");
    const state = baseState();
    state.canUndo = true;
    await app.reload(state);

    await app.click(app.byId("undoBtn"));

    assert.equal(app.query(".statusbar").dataset.state, "error");
    app.close();
  });

  test("a failed add keeps the dialog open", async () => {
    const app = await mount();
    app.server.fail("/course/add", "Un sigle est requis");
    await app.click(app.byId("addBtn"));
    app.select(app.byId("fSigle"), "ATE100");

    await app.click(app.byId("addSubmit"));

    assert.equal(app.byId("addDialog").open, true);
    assert.equal(app.toast().text, "Un sigle est requis");
    app.close();
  });

  test("a refused field edit puts the shown value back", async () => {
    const app = await mount();
    app.select(app.byId("detailSelect"), "LOG430-02");
    await flush();
    app.server.fail("/evaluation/set", "Nom déjà utilisé");
    await app.click(app.query('#detail .evals__row[data-index="0"]'));

    const input = app.query('#detail [data-key="ev:nom"]');
    input.value = "TP1 - Architecture microservices";
    app.fire(input, "change");
    await flush();

    assert.equal(app.toast().text, "Nom déjà utilisé");
    assert.equal(
      app.query('#detail [data-key="ev:nom"]').getAttribute("value"),
      "Examen intra",
    );
    app.close();
  });

  test("a status line without a message falls back to the http status", async () => {
    const app = await mount();
    app.server.fail("/undo", undefined, 500);
    const state = baseState();
    state.canUndo = true;
    await app.reload(state);

    await app.click(app.byId("undoBtn"));

    assert.equal(app.toast().intent, "error");
    assert.ok(app.toast().text.length > 0);
    app.close();
  });
});

describe("while saving", () => {
  test("the status bar says it is working", async () => {
    const app = await mount();
    const state = baseState();
    state.canUndo = true;
    await app.reload(state);

    const original = app.window.fetch;
    let release;
    app.window.fetch = (...args) =>
      new Promise((resolve) => {
        release = () => resolve(original(...args));
      });

    app.byId("undoBtn").click();
    await flush();

    assert.equal(app.status(), "Enregistrement…");
    assert.equal(app.byId("statusProgress").hidden, false);
    assert.equal(app.query(".statusbar").dataset.state, "busy");

    release();
    await flush();

    assert.equal(app.status(), "Enregistré.");
    assert.equal(app.byId("statusProgress").hidden, true);
    assert.equal(app.query(".statusbar").dataset.state, "idle");
    app.close();
  });

  test("a gesture started while saving is ignored", async () => {
    const app = await mount();
    const state = baseState();
    state.canUndo = true;
    await app.reload(state);

    const original = app.window.fetch;
    let release;
    app.window.fetch = (...args) =>
      new Promise((resolve) => {
        release = () => resolve(original(...args));
      });
    app.byId("undoBtn").click();
    await flush();

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.server.lastCall("/block/move"), null);

    release();
    await flush();
    app.close();
  });
});

describe("notices", () => {
  test("a notice from the server replaces the saved message", async () => {
    const app = await mount();
    const state = baseState();
    state.notices = ["Journée pédagogique (23 févr.) ne s'applique plus."];
    app.server.reply("/block/move", state);

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.status(), state.notices[0]);
    app.close();
  });

  test("several notices are joined", async () => {
    const app = await mount();
    const state = baseState();
    state.notices = ["Premier avis.", "Second avis."];
    app.server.reply("/block/move", state);

    await app.drag("LOG430-02:0", { dx: 240, dy: 64.8 });

    assert.equal(app.status(), "Premier avis. Second avis.");
    app.close();
  });
});

describe("empty sessions", () => {
  test("says so when no session has courses", async () => {
    const state = baseState();
    state.sessions = [];
    state.courses = [];
    state.blocks = [];
    state.occurrences = [];
    const app = await mount({ state });

    assert.equal(app.status(), "Aucune session avec des cours.");
    app.close();
  });
});
