import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, mount } from "./harness.mjs";

function stateWith(edit) {
  const state = baseState();
  edit(state);
  return state;
}

const removedState = () =>
  stateWith((state) => {
    state.removedSessions = [state.session];
    state.sessionStatus = { added: false, removed: true, removable: false };
    state.canUndo = true;
  });

const addedState = (code = "A2024") =>
  stateWith((state) => {
    state.session = code;
    state.sessions = [...state.sessions, code];
    state.sessionStatus = { added: true, removed: false, removable: true };
    state.courses = [];
    state.blocks = [];
    state.occurrences = [];
    state.meta.addableSessions = state.meta.addableSessions.filter((c) => c !== code);
  });

const protectedState = () =>
  stateWith((state) => {
    state.sessionStatus = { added: false, removed: false, removable: false };
  });

const posted = (app, path) => app.server.lastCall(path)?.body;
const optionTexts = (app, id) =>
  app.queryAll(`#${id} fluent-option`).map((option) => option.textContent);

describe("removing a session", () => {
  test("retires a past session from the API in one click", async () => {
    const app = await mount();
    app.server.reply("/session/remove", removedState());

    await app.click(app.byId("sessionRemoveBtn"));

    assert.deepEqual(posted(app, "/session/remove"), { session: "H2026" });
    assert.equal(app.byId("sessionDeleteDialog").open, false);
    assert.equal(app.toast().text, "H2026 retirée de l’API");
  });

  test("cannot remove the active session, and says why", async () => {
    const app = await mount({ state: protectedState() });
    const button = app.byId("sessionRemoveBtn");

    assert.equal(button.disabled, true);
    assert.match(app.byId("sessionRemoveTip").textContent, /session active ne peut pas/);
    assert.equal(button.getAttribute("aria-label"), app.byId("sessionRemoveTip").textContent);

    await app.click(button);
    assert.equal(app.server.called("/session/remove").length, 0);
  });

  test("asks before deleting a session added in the editor", async () => {
    const app = await mount({ state: addedState() });
    assert.equal(app.byId("sessionRemoveTip").textContent, "Supprimer la session");

    await app.click(app.byId("sessionRemoveBtn"));

    assert.equal(app.byId("sessionDeleteDialog").open, true);
    assert.equal(app.text("#sessionDeleteName"), "A2024");
    assert.equal(app.server.called("/session/remove").length, 0);

    app.server.reply("/session/remove", baseState());
    await app.click(app.byId("sessionDeleteConfirm"));

    assert.equal(app.byId("sessionDeleteDialog").open, false);
    assert.deepEqual(posted(app, "/session/remove"), { session: "A2024" });
    assert.equal(app.toast().text, "A2024 supprimée");
  });

  test("keeps an added session when the deletion is cancelled", async () => {
    const app = await mount({ state: addedState() });

    await app.click(app.byId("sessionRemoveBtn"));
    await app.click(app.query("[data-close-session-delete]"));

    assert.equal(app.byId("sessionDeleteDialog").open, false);
    assert.equal(app.server.called("/session/remove").length, 0);
  });
});

describe("a removed session", () => {
  test("is marked in the session list", async () => {
    const app = await mount({ state: removedState() });

    assert.deepEqual(optionTexts(app, "sessionSelect"), ["A2026", "H2026 (retirée)", "H2025"]);
  });

  test("dims the schedule and explains that the API ignores it", async () => {
    const app = await mount({ state: removedState() });

    assert.equal(app.byId("board").classList.contains("is-removed"), true);
    assert.equal(app.byId("removedNotice").hidden, false);
    assert.match(app.text("#removedNoticeText"), /^H2026 n’est plus servie par l’API/);
    assert.equal(app.byId("addBtn").disabled, true);
    assert.equal(app.byId("detailPanel").hidden, true);
    assert.equal(app.byId("sessionRemoveBtn").disabled, true);
  });

  test("can be restored", async () => {
    const app = await mount({ state: removedState() });
    app.server.reply("/session/restore", baseState());

    await app.click(app.byId("sessionRestoreBtn"));

    assert.deepEqual(posted(app, "/session/restore"), { session: "H2026" });
    assert.equal(app.byId("removedNotice").hidden, true);
    assert.equal(app.byId("board").classList.contains("is-removed"), false);
    assert.equal(app.byId("addBtn").disabled, false);
    assert.deepEqual(optionTexts(app, "sessionSelect"), ["A2026", "H2026", "H2025"]);
    assert.equal(app.toast().text, "H2026 restaurée");
  });
});

describe("adding a session", () => {
  test("offers only the sessions that do not exist yet", async () => {
    const app = await mount();

    await app.click(app.byId("sessionAddBtn"));

    assert.equal(app.byId("sessionDialog").open, true);
    assert.deepEqual(optionTexts(app, "fNewSession"), baseState().meta.addableSessions);
  });

  test("needs a session to be picked", async () => {
    const app = await mount();
    await app.click(app.byId("sessionAddBtn"));

    await app.click(app.byId("sessionAddSubmit"));

    assert.equal(app.server.called("/session/add").length, 0);
    assert.equal(app.toast().text, "Choisissez une session");
    assert.equal(app.byId("sessionDialog").open, true);
  });

  test("creates the session and switches to it", async () => {
    const app = await mount();
    await app.click(app.byId("sessionAddBtn"));
    app.select(app.byId("fNewSession"), "A2024");
    app.server.reply("/session/add", addedState("A2024"));

    await app.click(app.byId("sessionAddSubmit"));

    assert.deepEqual(posted(app, "/session/add"), { session: "A2024" });
    assert.equal(app.byId("sessionDialog").open, false);
    assert.equal(app.byId("sessionSelect").value, "A2024");
    assert.equal(app.toast().text, "A2024 ajoutée");
  });

  test("is disabled when every session already exists", async () => {
    const app = await mount({
      state: stateWith((state) => {
        state.meta.addableSessions = [];
      }),
    });

    assert.equal(app.byId("sessionAddBtn").disabled, true);
  });
});
