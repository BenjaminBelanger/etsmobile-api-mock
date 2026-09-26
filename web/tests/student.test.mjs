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
const rows = (app) => app.queryAll("#profileFields .field");
const field = (app, key) => app.query(`#profileFields [data-key="student:${key}"]`);
const rowFor = (app, key) => field(app, key).closest(".field");
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

  test("gives the schedule back when the schedule tab is picked", async () => {
    const app = await onStudent();
    await openTab(app, "viewSchedule");

    assert.equal(app.byId("studentView").hidden, true);
    assert.equal(app.byId("studentToolbar").hidden, true);
    assert.equal(app.byId("scheduleView").hidden, false);
    assert.equal(app.blocks().length > 0, true);
    app.close();
  });

  test("reads the profile again each time it is picked", async () => {
    const app = await onStudent();
    await openTab(app, "viewSchedule");
    await openTab(app, "viewStudent");

    assert.equal(app.server.student.called("/state").length, 2);
    app.close();
  });

  test("reports a server it cannot reach", async () => {
    const app = await mount();
    app.server.student.fail("/state", "Serveur injoignable", 500);
    await openTab(app, "viewStudent");

    assert.equal(app.status(), "Impossible de lire le profil étudiant.");
    assert.equal(app.toast().intent, "error");
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
});

describe("the student profile", () => {
  test("lists every field with its label and value, keeping the key as a tooltip", async () => {
    const app = await onStudent();
    const profile = baseStudent().student;

    assert.deepEqual(
      rows(app).map((row) => row.getAttribute("title")),
      profile.map((row) => row.key),
    );
    assert.equal(app.query("#profileFields code"), null);
    assert.equal(rowFor(app, "nom").querySelector(".field__label").textContent, "Nom");
    assert.equal(field(app, "nom").value, "Last0");
    assert.equal(field(app, "codePerm").value, "ABCD12345678");
    assert.equal(field(app, "soldeTotal").value, "1234,56$");
    assert.equal(field(app, "masculin").checked, true);
    assert.equal(rowFor(app, "masculin").querySelector(".check span").textContent, "Oui");
    app.close();
  });

  test("only lets the values be edited, never their keys", async () => {
    const app = await onStudent();

    rows(app).forEach((row) => {
      assert.equal(row.querySelectorAll("fluent-text-input, input").length, 1);
    });
    app.close();
  });

  test("shows a field it has no label for by its key", async () => {
    const student = studentWith((s) => {
      s.student.push({ key: "courriel", value: "a@b.ca", modified: false });
    });
    const app = await onStudent(student);

    assert.equal(rowFor(app, "courriel").querySelector(".field__label").textContent, "courriel");
    app.close();
  });

  test("saves an edited name once the field is left", async () => {
    const app = await onStudent();
    await typeAndLeave(app, "nom", "Tremblay");

    assert.equal(app.server.student.called("/set").length, 1);
    assert.deepEqual(posted(app, "/set"), { field: "nom", value: "Tremblay" });
    assert.equal(app.status(), "Enregistré.");
    app.close();
  });

  test("saves the checkbox as a boolean", async () => {
    const app = await onStudent();
    const box = field(app, "masculin");
    box.checked = false;
    app.fire(box, "change");
    await flush();

    assert.deepEqual(posted(app, "/set"), { field: "masculin", value: false });
    assert.equal(rowFor(app, "masculin").querySelector(".check span").textContent, "Non");
    app.close();
  });

  test("marks a changed field and offers to restore it", async () => {
    const app = await onStudent();
    assert.equal(app.query("#profileFields [data-reset]"), null);

    await typeAndLeave(app, "nom", "Tremblay");
    assert.equal(rowFor(app, "nom").classList.contains("is-modified"), true);
    assert.equal(field(app, "nom").classList.contains("is-pinned"), true);
    assert.match(field(app, "nom").getAttribute("title"), /^nom · .*valeur d'origine/);

    await app.click(rowFor(app, "nom").querySelector("[data-reset]"));
    assert.deepEqual(posted(app, "/set"), { field: "nom", value: null });
    assert.equal(app.toast().text, "Valeur d'origine rétablie");
    assert.equal(rowFor(app, "nom").classList.contains("is-modified"), false);
    app.close();
  });

  test("puts the shown value back when an edit is refused", async () => {
    const app = await onStudent();
    app.server.student.fail("/set", "Invalid amount 'gratuit'");
    await typeAndLeave(app, "soldeTotal", "gratuit");

    assert.equal(app.status(), "Erreur.");
    assert.deepEqual(app.toast(), {
      hidden: false,
      text: "Invalid amount 'gratuit'",
      intent: "error",
    });
    assert.equal(field(app, "soldeTotal").value, "1234,56$");
    app.close();
  });

  test("keeps a field being typed when another save redraws the list", async () => {
    const app = await onStudent();
    const typed = field(app, "prenom");
    typed.setAttribute("tabindex", "0");
    typed.focus();
    typed.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "e", bubbles: true }));
    typed.value = "Mari";
    const box = field(app, "masculin");
    box.checked = false;
    app.fire(box, "change");
    await flush();

    assert.equal(field(app, "prenom"), typed);
    assert.equal(typed.value, "Mari");
    assert.equal(app.server.student.called("/set").length, 1);
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
    await typeAndLeave(app, "nom", "Tremblay");
    assert.equal(app.byId("studentUndoBtn").disabled, false);
    assert.equal(app.byId("studentResetBtn").disabled, false);

    app.server.student.reply("/undo", { ...baseStudent(), canRedo: true });
    await app.click(app.byId("studentUndoBtn"));
    assert.equal(app.server.student.called("/undo").length, 1);
    assert.equal(app.toast().text, "Modification annulée");
    assert.equal(app.byId("studentRedoBtn").disabled, false);
    assert.equal(field(app, "nom").value, rowOf(baseStudent().student, "nom").value);

    await app.click(app.byId("studentRedoBtn"));
    assert.equal(app.server.student.called("/redo").length, 1);
    assert.equal(app.toast().text, "Modification rétablie");
    app.close();
  });

  test("undoes the profile edit with Ctrl+Z, not the schedule", async () => {
    const app = await onStudent();
    await typeAndLeave(app, "nom", "Tremblay");
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

  test("resets the whole profile at once", async () => {
    const app = await onStudent();
    await typeAndLeave(app, "nom", "Tremblay");
    await app.click(app.byId("studentResetBtn"));

    assert.equal(app.server.student.called("/reset").length, 1);
    assert.equal(app.toast().text, "Profil réinitialisé");
    assert.equal(rowFor(app, "nom").classList.contains("is-modified"), false);
    assert.equal(app.byId("studentResetBtn").disabled, true);
    app.close();
  });
});
