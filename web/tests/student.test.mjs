import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseStudent, flush, mount } from "./harness.mjs";

async function openTab(app, id) {
  app.fire(app.byId("viewToggle"), "change", { detail: app.byId(id) });
  await flush();
}

async function onStudent(student) {
  const app = await mount(student ? { student } : {});
  await openTab(app, "viewStudent");
  return app;
}

function studentWith(edit) {
  const student = baseStudent();
  edit(student);
  return student;
}

const rowOf = (rows, key) => rows.find((row) => row.key === key);
const dateRows = (app) => app.queryAll("#dateList .date");
const field = (app, key) => app.query(`#studentView [data-key="${key}"]`);
const rowFor = (app, key) => field(app, `date:${key}`).closest(".date");
const posted = (app, path) => app.server.student.lastCall(path)?.body;

async function typeAndLeave(app, key, value) {
  const node = field(app, key);
  node.dispatchEvent(
    new app.window.KeyboardEvent("keydown", { key: value.slice(-1), bubbles: true }),
  );
  node.value = value;
  app.fire(node, "change");
  await flush();
  app.fire(node, "focusout");
  await flush();
}

async function pick(app, key, value) {
  const node = field(app, key);
  app.mouse(node, "pointerdown");
  node.value = value;
  app.fire(node, "change");
  await flush();
}

describe("the student tab", () => {
  test("stays out of the way until it is picked", async () => {
    const app = await mount();

    assert.equal(app.byId("studentView").hidden, true);
    assert.equal(app.byId("studentToolbar").hidden, true);
    assert.equal(app.server.student.calls.length, 0);
    app.close();
  });

  test("replaces the schedule and its toolbar once picked", async () => {
    const app = await onStudent();

    assert.equal(app.byId("studentView").hidden, false);
    assert.equal(app.byId("studentToolbar").hidden, false);
    assert.equal(app.byId("scheduleView").hidden, true);
    assert.equal(app.byId("scheduleControls").hidden, true);
    assert.equal(app.byId("scheduleToolbar").hidden, true);
    assert.equal(app.byId("failuresView").hidden, true);
    assert.equal(app.byId("failuresToolbar").hidden, true);
    assert.equal(app.document.title, "Étudiant - ÉTS Mock");
    app.close();
  });

  test("opens on the session shown in the schedule", async () => {
    const app = await onStudent();

    assert.equal(app.server.student.lastCall("/state").query, "session=H2026");
    assert.equal(app.byId("studentSessionSelect").value, "H2026");
    app.close();
  });

  test("gives the schedule back when the schedule tab is picked", async () => {
    const app = await onStudent();
    await openTab(app, "viewSchedule");

    assert.equal(app.byId("studentView").hidden, true);
    assert.equal(app.byId("studentToolbar").hidden, true);
    assert.equal(app.byId("scheduleView").hidden, false);
    assert.equal(app.blocks().length > 0, true);
    app.close();
  });

  test("reports a server it cannot reach", async () => {
    const app = await mount();
    app.server.student.fail("/state", "Serveur injoignable", 500);
    await openTab(app, "viewStudent");

    assert.equal(app.status(), "Impossible de lire le dossier étudiant.");
    assert.equal(app.toast().intent, "error");
    app.close();
  });
});

describe("the session dates", () => {
  test("lists every date of the session with its key", async () => {
    const app = await onStudent();
    const dates = baseStudent().dates;

    assert.equal(dateRows(app).length, dates.length);
    assert.deepEqual(
      dateRows(app).map((row) => row.querySelector(".date__key").textContent),
      dates.map((row) => row.key),
    );
    assert.equal(rowFor(app, "dateDebut").querySelector(".date__label").textContent, "Début de la session");
    assert.equal(field(app, "date:dateFin").value, rowOf(dates, "dateFin").value);
    app.close();
  });

  test("only lets the dates be edited, never their keys", async () => {
    const app = await onStudent();

    dateRows(app).forEach((row) => {
      const inputs = row.querySelectorAll("fluent-text-input, input");
      assert.equal(inputs.length, 1);
      assert.equal(inputs[0].getAttribute("type"), "date");
      assert.equal(row.querySelector(".date__key").tagName, "CODE");
    });
    app.close();
  });

  test("shows a date it has no label for by its key", async () => {
    const student = studentWith((s) => {
      s.dates.push({ key: "dateInconnue", value: "2026-03-02", modified: false });
    });
    const app = await onStudent(student);
    const row = rowFor(app, "dateInconnue");

    assert.equal(row.querySelector(".date__label"), null);
    assert.equal(row.querySelector(".date__key").textContent, "dateInconnue");
    app.close();
  });

  test("saves a date picked from the calendar", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");

    assert.deepEqual(posted(app, "/session-date"), {
      session: "H2026",
      field: "dateFin",
      value: "2026-05-01",
    });
    assert.equal(app.status(), "Enregistré.");
    app.close();
  });

  test("saves a typed date once, when the field is left", async () => {
    const app = await onStudent();
    const node = field(app, "date:dateFin");
    node.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    node.value = "0002-04-27";
    app.fire(node, "change");
    node.value = "2026-05-01";
    app.fire(node, "change");
    await flush();

    assert.equal(app.server.student.called("/session-date").length, 0);

    app.fire(node, "focusout");
    await flush();

    assert.equal(app.server.student.called("/session-date").length, 1);
    assert.equal(posted(app, "/session-date").value, "2026-05-01");
    app.close();
  });

  test("does not save a date that is left unchanged", async () => {
    const app = await onStudent();
    app.fire(field(app, "date:dateFin"), "focusout");
    await flush();

    assert.equal(app.server.student.called("/session-date").length, 0);
    app.close();
  });

  test("does not save a half typed date when a save redraws the list", async () => {
    const app = await onStudent();
    const typed = field(app, "date:dateDebut");
    typed.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    typed.value = "0002-01-05";
    const list = app.byId("dateList");
    const setInner = Object.getOwnPropertyDescriptor(app.window.Element.prototype, "innerHTML").set;
    Object.defineProperty(list, "innerHTML", {
      configurable: true,
      set(html) {
        app.fire(typed, "focusout");
        setInner.call(this, html);
      },
    });
    await pick(app, "date:dateFin", "2026-05-01");

    assert.equal(app.server.student.called("/session-date").length, 1);
    assert.equal(posted(app, "/session-date").field, "dateFin");
    app.close();
  });

  test("keeps a date being typed when another save redraws the list", async () => {
    const app = await onStudent();
    const typed = field(app, "date:dateDebut");
    typed.setAttribute("tabindex", "0");
    typed.focus();
    typed.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "2", bubbles: true }));
    typed.value = "2026-01-12";
    await pick(app, "date:dateFin", "2026-05-01");

    assert.equal(field(app, "date:dateDebut"), typed);
    assert.equal(app.document.activeElement, typed);
    assert.equal(typed.value, "2026-01-12");

    app.fire(typed, "focusout");
    await flush();
    assert.deepEqual(posted(app, "/session-date"), {
      session: "H2026",
      field: "dateDebut",
      value: "2026-01-12",
    });
    app.close();
  });

  test("moves focus to the redrawn field when nothing is being typed", async () => {
    const app = await onStudent();
    const picked = field(app, "date:dateFin");
    picked.setAttribute("tabindex", "0");
    picked.focus();
    await pick(app, "date:dateFin", "2026-05-01");
    const redrawn = field(app, "date:dateFin");

    assert.notEqual(redrawn, picked);
    assert.equal(redrawn.classList.contains("is-pinned"), true);
    app.close();
  });

  test("marks a changed date and offers to restore it", async () => {
    const app = await onStudent();
    assert.equal(app.query("#dateList [data-reset]"), null);

    await pick(app, "date:dateFin", "2026-05-01");
    const row = rowFor(app, "dateFin");
    assert.equal(row.classList.contains("is-modified"), true);
    assert.equal(field(app, "date:dateFin").classList.contains("is-pinned"), true);

    await app.click(row.querySelector("[data-reset]"));
    assert.deepEqual(posted(app, "/session-date"), {
      session: "H2026",
      field: "dateFin",
      value: null,
    });
    assert.equal(app.toast().text, "Date rétablie");
    assert.equal(rowFor(app, "dateFin").classList.contains("is-modified"), false);
    app.close();
  });

  test("loads the session picked in the dropdown", async () => {
    const app = await onStudent();
    app.select(app.byId("studentSessionSelect"), "H2025");
    await flush();

    assert.equal(app.server.student.lastCall("/state").query, "session=H2025");
    app.close();
  });

  test("saves a date to the session on show", async () => {
    const app = await onStudent();
    app.select(app.byId("studentSessionSelect"), "H2025");
    await flush();
    await pick(app, "date:dateDebut", "2025-01-13");

    assert.equal(posted(app, "/session-date").session, "H2025");
    app.close();
  });

  test("warns when an end comes before its start", async () => {
    const app = await onStudent();
    assert.equal(app.byId("dateWarn").hidden, true);

    await pick(app, "date:dateFinCours", "2026-05-15");

    assert.equal(app.byId("dateWarn").hidden, false);
    assert.equal(
      app.byId("dateWarn").textContent,
      "« Fin de la session » précède « Fin des cours »",
    );
    app.close();
  });

  test("says so when no session has courses", async () => {
    const student = studentWith((s) => {
      s.session = "";
      s.sessions = [];
      s.dates = [];
    });
    const app = await onStudent(student);

    assert.equal(dateRows(app).length, 0);
    assert.equal(app.byId("dateEmpty").hidden, false);
    assert.equal(app.byId("studentSessionSelect").hidden, true);
    app.close();
  });
});

describe("the student profile", () => {
  test("shows every field with its value", async () => {
    const app = await onStudent();

    assert.equal(field(app, "student:nom").textContent, "Nom");
    assert.equal(field(app, "student:nom").value, "Last0");
    assert.equal(field(app, "student:prenom").value, "First0");
    assert.equal(field(app, "student:codePerm").value, "ABCD12345678");
    assert.equal(field(app, "student:codeUniversel").value, "AB12345");
    assert.equal(field(app, "student:soldeTotal").value, "1234,56$");
    assert.equal(field(app, "student:masculin").checked, true);
    app.close();
  });

  test("saves an edited name when the field is left", async () => {
    const app = await onStudent();
    await typeAndLeave(app, "student:nom", "Tremblay");

    assert.equal(app.server.student.called("/profile").length, 1);
    assert.deepEqual(posted(app, "/profile"), {
      session: "H2026",
      field: "nom",
      value: "Tremblay",
    });
    assert.equal(field(app, "student:nom").classList.contains("is-pinned"), true);
    app.close();
  });

  test("leaves a field on Enter", async () => {
    const app = await onStudent();
    const node = field(app, "student:prenom");
    let blurred = false;
    node.blur = () => {
      blurred = true;
    };
    node.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    assert.equal(blurred, true);
    app.close();
  });

  test("saves the checkbox as a boolean", async () => {
    const app = await onStudent();
    const box = field(app, "student:masculin");
    box.checked = false;
    app.fire(box, "change");
    await flush();

    assert.deepEqual(posted(app, "/profile"), {
      session: "H2026",
      field: "masculin",
      value: false,
    });
    assert.equal(field(app, "student:masculin").closest(".check").classList.contains("is-pinned"), true);
    app.close();
  });

  test("explains how to restore a changed field", async () => {
    const student = studentWith((s) => {
      Object.assign(rowOf(s.student, "nom"), { value: "Tremblay", modified: true });
    });
    const app = await onStudent(student);

    assert.match(field(app, "student:nom").getAttribute("title"), /valeur d'origine/);
    assert.equal(field(app, "student:prenom").hasAttribute("title"), false);
    app.close();
  });

  test("puts the shown value back when an edit is refused", async () => {
    const app = await onStudent();
    app.server.student.fail("/profile", "Invalid amount 'gratuit'");
    await typeAndLeave(app, "student:soldeTotal", "gratuit");

    assert.equal(app.status(), "Erreur.");
    assert.deepEqual(app.toast(), {
      hidden: false,
      text: "Invalid amount 'gratuit'",
      intent: "error",
    });
    assert.equal(field(app, "student:soldeTotal").value, "1234,56$");
    app.close();
  });
});

describe("the student history", () => {
  test("starts with nothing to undo, redo or reset", async () => {
    const app = await onStudent();

    assert.equal(app.byId("studentUndoBtn").disabled, true);
    assert.equal(app.byId("studentRedoBtn").disabled, true);
    assert.equal(app.byId("studentResetBtn").disabled, true);
    app.close();
  });

  test("undoes and redoes through the server", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");
    assert.equal(app.byId("studentUndoBtn").disabled, false);
    assert.equal(app.byId("studentResetBtn").disabled, false);

    app.server.student.reply("/undo", { ...baseStudent(), canRedo: true });
    await app.click(app.byId("studentUndoBtn"));
    assert.deepEqual(posted(app, "/undo"), { session: "H2026" });
    assert.equal(app.toast().text, "Modification annulée");
    assert.equal(app.byId("studentRedoBtn").disabled, false);
    assert.equal(field(app, "date:dateFin").value, rowOf(baseStudent().dates, "dateFin").value);

    await app.click(app.byId("studentRedoBtn"));
    assert.deepEqual(posted(app, "/redo"), { session: "H2026" });
    assert.equal(app.toast().text, "Modification rétablie");
    app.close();
  });

  test("shows the session an undo went back to", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");
    app.server.student.reply("/undo", { ...baseStudent(), session: "H2025" });
    await app.click(app.byId("studentUndoBtn"));

    assert.equal(app.byId("studentSessionSelect").value, "H2025");
    app.close();
  });

  test("undoes the student edit with Ctrl+Z, not the schedule", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");
    app.key("z", { ctrlKey: true });
    await flush();

    assert.equal(app.server.student.called("/undo").length, 1);
    assert.equal(app.server.lastCall("/undo"), null);
    app.close();
  });

  test("redoes with Ctrl+Y", async () => {
    const app = await onStudent(studentWith((s) => (s.canRedo = true)));
    app.key("y", { ctrlKey: true });
    await flush();

    assert.equal(app.server.student.called("/redo").length, 1);
    app.close();
  });

  test("leaves schedule shortcuts alone while it is open", async () => {
    const app = await mount();
    await app.click(app.blockFor("LOG430-02:0"));
    await openTab(app, "viewStudent");
    app.key("Delete");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    app.close();
  });

  test("resets everything at once", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");
    await app.click(app.byId("studentResetBtn"));

    assert.deepEqual(posted(app, "/reset"), { session: "H2026" });
    assert.equal(app.toast().text, "Dossier étudiant réinitialisé");
    assert.equal(rowFor(app, "dateFin").classList.contains("is-modified"), false);
    assert.equal(app.byId("studentResetBtn").disabled, true);
    app.close();
  });
});

describe("going back to the schedule", () => {
  test("reloads the schedule once the student record changed", async () => {
    const app = await onStudent();
    await pick(app, "date:dateFin", "2026-05-01");
    const loads = app.server.called("/state").length;
    await openTab(app, "viewSchedule");

    assert.equal(app.server.called("/state").length, loads + 1);
    assert.equal(app.server.lastCall("/state").query, "session=H2026");

    await openTab(app, "viewStudent");
    await openTab(app, "viewSchedule");
    assert.equal(app.server.called("/state").length, loads + 1);
    app.close();
  });

  test("does not reload the schedule when nothing changed", async () => {
    const app = await onStudent();
    const loads = app.server.called("/state").length;
    await openTab(app, "viewSchedule");

    assert.equal(app.server.called("/state").length, loads);
    app.close();
  });

  test("reopens on the session last shown in the tab", async () => {
    const app = await onStudent();
    app.select(app.byId("studentSessionSelect"), "H2025");
    await flush();
    await openTab(app, "viewSchedule");
    await openTab(app, "viewStudent");

    assert.equal(app.server.student.lastCall("/state").query, "session=H2025");
    app.close();
  });
});
