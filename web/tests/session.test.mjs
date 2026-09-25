import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, flush, mount } from "./harness.mjs";

function stateWith(edit) {
  const state = baseState();
  edit(state);
  return state;
}

function changed(state, key, value) {
  Object.assign(
    state.dates.find((row) => row.key === key),
    { value, modified: true },
  );
  state.canUndo = true;
  return state;
}

const field = (app, key) => app.query(`#sessionDates [data-key="date:${key}"]`);
const shownKeys = (app) =>
  app.queryAll("#sessionDates [data-key]").map((node) => node.dataset.key.slice(5));
const toggle = (app) => app.query('#sessionDates [data-act="toggleDates"]');
const posted = (app, path) => app.server.lastCall(path)?.body;

async function pick(app, key, value) {
  const node = field(app, key);
  app.mouse(node, "pointerdown");
  node.value = value;
  app.fire(node, "change");
  await flush();
}

describe("the session dates panel", () => {
  test("shows the dates that shape the calendar first", async () => {
    const app = await mount();
    const dateFin = baseState().dates.find((row) => row.key === "dateFin");

    assert.equal(app.byId("sessionPanel").hidden, false);
    assert.deepEqual(shownKeys(app), ["dateDebut", "dateFinCours", "dateFin"]);
    assert.equal(field(app, "dateDebut").textContent, "Début de la session");
    assert.equal(field(app, "dateFin").value, dateFin.value);
    assert.equal(field(app, "dateFin").getAttribute("type"), "date");
    app.close();
  });

  test("names the API field of each date on hover", async () => {
    const app = await mount();

    assert.equal(field(app, "dateFinCours").getAttribute("title"), "dateFinCours");
    app.close();
  });

  test("keeps the other dates folded until asked", async () => {
    const app = await mount();
    assert.equal(field(app, "dateDebutChemiNot"), null);
    assert.equal(toggle(app).getAttribute("aria-expanded"), "false");

    await app.click(toggle(app));

    assert.equal(toggle(app).getAttribute("aria-expanded"), "true");
    assert.deepEqual(
      shownKeys(app),
      [
        "dateDebut",
        "dateFinCours",
        "dateFin",
        ...baseState()
          .dates.map((row) => row.key)
          .filter((key) => !["dateDebut", "dateFinCours", "dateFin"].includes(key)),
      ],
    );
    assert.equal(field(app, "dateLimitePourAnnulerASEQ").textContent, "Date limite pour annuler l'ASEQ");
    app.close();
  });

  test("keeps the other dates open after a save", async () => {
    const app = await mount();
    await app.click(toggle(app));
    await pick(app, "dateFin", "2026-05-01");

    assert.notEqual(field(app, "dateDebutChemiNot"), null);
    app.close();
  });

  test("flags the fold when a hidden date was changed", async () => {
    const state = changed(baseState(), "dateFinChemiNot", "2026-06-01");
    const app = await mount({ state });

    assert.equal(toggle(app).classList.contains("is-pinned"), true);
    app.close();
  });

  test("saves a date picked from the calendar", async () => {
    const app = await mount();
    await pick(app, "dateFin", "2026-05-01");

    assert.deepEqual(posted(app, "/session/date"), {
      session: "H2026",
      field: "dateFin",
      value: "2026-05-01",
    });
    app.close();
  });

  test("saves a typed date once, when the field is left", async () => {
    const app = await mount();
    const node = field(app, "dateFin");
    node.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    node.value = "0002-04-27";
    app.fire(node, "change");
    node.value = "2026-05-01";
    app.fire(node, "change");
    await flush();

    assert.equal(app.server.called("/session/date").length, 0);

    app.fire(node, "focusout");
    await flush();

    assert.equal(app.server.called("/session/date").length, 1);
    assert.equal(posted(app, "/session/date").value, "2026-05-01");
    app.close();
  });

  test("marks a changed date and explains how to restore it", async () => {
    const state = changed(baseState(), "dateFin", "2026-05-01");
    const app = await mount({ state });

    assert.equal(field(app, "dateFin").classList.contains("is-pinned"), true);
    assert.match(field(app, "dateFin").getAttribute("title"), /^dateFin · .*valeur d'origine/);
    assert.equal(field(app, "dateDebut").classList.contains("is-pinned"), false);
    app.close();
  });

  test("offers to restore every date once one changed", async () => {
    const app = await mount();
    assert.equal(app.byId("sessionDatesReset").hidden, true);

    app.server.reply("/session/date", changed(baseState(), "dateFin", "2026-05-01"));
    await pick(app, "dateFin", "2026-05-01");
    assert.equal(app.byId("sessionDatesReset").hidden, false);

    app.server.reply("/session/dates/reset", baseState());
    await app.click(app.byId("sessionDatesReset"));
    assert.deepEqual(posted(app, "/session/dates/reset"), { session: "H2026" });
    assert.equal(app.toast().text, "Dates de la session rétablies");
    assert.equal(app.byId("sessionDatesReset").hidden, true);
    app.close();
  });

  test("redraws the calendar the server sends back", async () => {
    const app = await mount();
    const weeks = app.queryAll("#weekSelect fluent-option").length;
    const shorter = stateWith((s) => {
      changed(s, "dateFin", "2026-02-27");
      s.meta.semester.dateFin = "2026-02-27";
      s.meta.semester.weeks = s.meta.semester.weeks.slice(0, weeks - 1);
    });
    app.server.reply("/session/date", shorter);
    await pick(app, "dateFin", "2026-02-27");

    assert.equal(app.queryAll("#weekSelect fluent-option").length, weeks - 1);
    assert.equal(app.byId("undoBtn").disabled, false);
    app.close();
  });

  test("warns when an end comes before its start", async () => {
    const app = await mount();
    assert.equal(app.query("#sessionDates .detail__warn"), null);

    app.server.reply("/session/date", changed(baseState(), "dateFinCours", "2026-05-15"));
    await pick(app, "dateFinCours", "2026-05-15");

    assert.equal(
      app.query("#sessionDates .detail__warn").textContent,
      "« Fin de la session » précède « Fin des cours »",
    );
    app.close();
  });

  test("puts the shown date back when an edit is refused", async () => {
    const app = await mount();
    const original = field(app, "dateFin").value;
    app.server.fail("/session/date", "Invalid date '2026-02-30'");
    await pick(app, "dateFin", "2026-02-30");

    assert.equal(app.toast().intent, "error");
    assert.equal(field(app, "dateFin").value, original);
    app.close();
  });

  test("keeps a date being typed when another save redraws the panel", async () => {
    const app = await mount();
    const typed = field(app, "dateDebut");
    typed.setAttribute("tabindex", "0");
    typed.focus();
    typed.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    typed.value = "2026-01-12";
    await pick(app, "dateFin", "2026-05-01");

    assert.equal(field(app, "dateDebut"), typed);
    assert.equal(app.document.activeElement, typed);

    app.fire(typed, "focusout");
    await flush();
    assert.deepEqual(posted(app, "/session/date"), {
      session: "H2026",
      field: "dateDebut",
      value: "2026-01-12",
    });
    app.close();
  });

  test("saves nothing for a field that a redraw takes away", async () => {
    const app = await mount();
    const typed = field(app, "dateDebut");
    typed.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    typed.value = "0002-01-05";
    const panel = app.byId("sessionDates");
    const setInner = Object.getOwnPropertyDescriptor(app.window.Element.prototype, "innerHTML").set;
    Object.defineProperty(panel, "innerHTML", {
      configurable: true,
      set(html) {
        app.fire(typed, "focusout");
        setInner.call(this, html);
      },
    });
    await pick(app, "dateFin", "2026-05-01");

    assert.equal(app.server.called("/session/date").length, 1);
    assert.equal(posted(app, "/session/date").field, "dateFin");
    app.close();
  });

  test("hides itself for a session without a calendar", async () => {
    const app = await mount({ state: stateWith((s) => (s.dates = [])) });

    assert.equal(app.byId("sessionPanel").hidden, true);
    app.close();
  });

  test("leaves the delete shortcut alone while a date is edited", async () => {
    const app = await mount();
    await app.click(app.blockFor("LOG430-02:0"));
    const node = field(app, "dateFin");
    node.setAttribute("tabindex", "0");
    node.focus();
    app.key("Backspace");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    app.close();
  });
});
