import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, flush, mount, rect } from "./harness.mjs";

const COURSE = "LOG430-02";

async function openCourse(app, courseId = COURSE) {
  app.select(app.byId("detailSelect"), courseId);
  await flush();
}

async function openEvaluation(app, index) {
  await app.click(app.query(`#detail .evals__row[data-index="${index}"]`));
}

const field = (app, key) => app.query(`#detail [data-key="${key}"]`);

async function commit(app, key, value) {
  const node = field(app, key);
  node.value = value;
  app.fire(node, "change");
  await flush();
  return node;
}

async function check(app, key, checked) {
  const node = field(app, key);
  node.checked = checked;
  app.fire(node, "change");
  await flush();
  return node;
}

describe("the detail panel", () => {
  test("lists every course of the session", async () => {
    const app = await mount();
    assert.equal(app.byId("detailPanel").hidden, false);
    assert.deepEqual(
      app.queryAll("#detailSelect fluent-option").map((o) => o.getAttribute("value")),
      ["LOG410-01", "LOG430-02"],
    );
    app.close();
  });

  test("shows the course picked in the dropdown", async () => {
    const app = await mount();

    await openCourse(app);

    assert.equal(app.text("#detail .detail__title"), "Architecture logicielle");
    app.close();
  });

  test("hides itself when the session has no course", async () => {
    const state = baseState();
    state.courses = [];
    state.blocks = [];
    state.occurrences = [];
    const app = await mount({ state });

    assert.equal(app.byId("detailPanel").hidden, true);
    app.close();
  });

  test("follows the block that was clicked", async () => {
    const app = await mount();

    await app.drag("LOG430-02:0", { dx: 0, dy: 0, steps: false });

    assert.equal(app.text("#detail .detail__title"), "Architecture logicielle");
    app.close();
  });

  test("selects the blocks of the course picked in the dropdown", async () => {
    const app = await mount();

    await openCourse(app);

    assert.deepEqual(
      app.queryAll(".block.is-selected").map((block) => block.dataset.blockId),
      ["LOG430-02:0", "LOG430-02:1"],
    );
    app.close();
  });

  test("sums up the published grades", async () => {
    const app = await mount();
    await openCourse(app);

    const summary = app.text("#detail .detail__summary").replace(/\s+/g, " ");

    assert.match(summary, /À ce jour 76.4/);
    assert.match(summary, /Moyenne 17.8/);
    assert.match(summary, /Publié 30.0 %/);
    app.close();
  });

  test("says when nothing is published", async () => {
    const state = baseState();
    state.courses[1].summary.noteACeJour = "";
    const app = await mount({ state });
    await openCourse(app);

    assert.equal(app.text("#detail .detail__empty"), "Aucune note publiée.");
    app.close();
  });

  test("lists the evaluations with their weighting and grade", async () => {
    const app = await mount();
    await openCourse(app);

    const rows = app.queryAll("#detail .evals__row");
    assert.deepEqual(
      rows.map((row) => row.querySelector(".evals__name").textContent),
      ["Examen intra", "TP1 - Architecture microservices", "TP2 - Projet final"],
    );
    assert.equal(rows[0].querySelector(".evals__pond").textContent, "30 %");
    assert.match(rows[0].querySelector(".evals__note").textContent, /^38.2\/50$/);
    app.close();
  });

  test("marks published evaluations", async () => {
    const app = await mount();
    await openCourse(app);

    const dots = app.queryAll("#detail .evals__pub");
    assert.ok(dots[0].classList.contains("is-on"));
    assert.equal(dots[2].classList.contains("is-on"), false);
    app.close();
  });

  test("says when a course has no evaluation", async () => {
    const state = baseState();
    state.courses[1].evaluations = [];
    const app = await mount({ state });
    await openCourse(app);

    assert.ok(
      app
        .queryAll("#detail .detail__empty")
        .some((node) => node.textContent === "Aucun élément d'évaluation."),
    );
    app.close();
  });

  test("warns when the weighting does not add up", async () => {
    const app = await mount();
    await openCourse(app);

    assert.equal(app.text("#detail .detail__warn"), "Pondération totale 70 %");
    app.close();
  });

  test("warns about a grade above its scale", async () => {
    const state = baseState();
    state.courses[1].evaluations[0].note = 99;
    const app = await mount({ state });
    await openCourse(app);

    assert.match(app.text("#detail .detail__warn"), /Note hors barème : Examen intra/);
    assert.ok(
      app.query("#detail .evals__note").classList.contains("is-warn"),
    );
    app.close();
  });

  test("opens and closes an evaluation", async () => {
    const app = await mount();
    await openCourse(app);

    await openEvaluation(app, 0);
    assert.ok(app.query("#detail .props"));
    assert.equal(
      app.query('#detail .evals__row[data-index="0"]').getAttribute("aria-expanded"),
      "true",
    );

    await openEvaluation(app, 0);
    assert.equal(app.query("#detail .props"), null);
    app.close();
  });

  test("fills the open evaluation with its values", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 0);

    assert.equal(field(app, "ev:nom").value, "Examen intra");
    assert.equal(field(app, "ev:note").value, "38.2");
    assert.equal(field(app, "ev:corrigeSur").value, "50");
    assert.equal(field(app, "ev:ponderation").value, "30");
    assert.equal(field(app, "ev:dateCible").value, "2026-01-30");
    assert.equal(field(app, "ev:publie").checked, true);
    assert.equal(field(app, "ev:isTeam").checked, false);
    app.close();
  });

  test("hides the class statistics until they are asked for", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 0);
    assert.equal(field(app, "ev:moyenne"), null);

    await app.click(app.query('#detail [data-act="toggleStats"]'));

    assert.equal(field(app, "ev:moyenne").value, "29.7");
    assert.equal(field(app, "ev:mediane").value, "27.9");
    assert.equal(field(app, "ev:ecartType").value, "5.7");
    assert.equal(field(app, "ev:rangCentile").value, "78");
    app.close();
  });

  test("marks the values that were pinned by hand", async () => {
    const state = baseState();
    state.courses[1].evaluations[0].pinned = ["note"];
    const app = await mount({ state });
    await openCourse(app);
    await openEvaluation(app, 0);

    const note = field(app, "ev:note");
    assert.ok(note.className.includes("is-pinned"));
    assert.match(note.getAttribute("title"), /videz le champ/);
    app.close();
  });
});

describe("editing from the detail panel", () => {
  test("saves an evaluation field", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 1);

    await commit(app, "ev:nom", "TP1 renommé");

    assert.deepEqual(app.server.lastCall("/evaluation/set").body, {
      session: "H2026",
      courseId: COURSE,
      index: 1,
      field: "nom",
      value: "TP1 renommé",
    });
    app.close();
  });

  test("saves a grade", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 0);

    await commit(app, "ev:note", "42,5");

    assert.equal(app.server.lastCall("/evaluation/set").body.value, "42,5");
    assert.equal(app.server.lastCall("/evaluation/set").body.field, "note");
    app.close();
  });

  test("saves a cleared grade as an empty value", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 0);

    await commit(app, "ev:note", "");

    assert.equal(app.server.lastCall("/evaluation/set").body.value, "");
    app.close();
  });

  test("saves the publication and team flags", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 0);

    await check(app, "ev:publie", false);
    assert.deepEqual(app.server.lastCall("/evaluation/set").body, {
      session: "H2026",
      courseId: COURSE,
      index: 0,
      field: "publie",
      value: false,
    });

    await check(app, "ev:isTeam", true);
    assert.equal(app.server.lastCall("/evaluation/set").body.field, "isTeam");
    assert.equal(app.server.lastCall("/evaluation/set").body.value, true);
    app.close();
  });

  test("saves the cote of the course", async () => {
    const app = await mount();
    await openCourse(app);

    await commit(app, "course:cote", "A+");

    assert.deepEqual(app.server.lastCall("/course/cote").body, {
      session: "H2026",
      courseId: COURSE,
      cote: "A+",
    });
    app.close();
  });

  test("saves the exam fields one by one", async () => {
    const app = await mount();
    await openCourse(app);

    await commit(app, "exam:date", "2026-04-22");
    assert.deepEqual(app.server.lastCall("/exam/set").body, {
      session: "H2026",
      courseId: COURSE,
      date: "2026-04-22",
    });

    await commit(app, "exam:local", "Z-9999");
    assert.deepEqual(app.server.lastCall("/exam/set").body, {
      session: "H2026",
      courseId: COURSE,
      local: "Z-9999",
    });
    app.close();
  });

  test("says when a course has no exam", async () => {
    const state = baseState();
    state.courses[1].exam = null;
    const app = await mount({ state });
    await openCourse(app);

    assert.ok(
      app
        .queryAll("#detail .detail__empty")
        .some((node) => node.textContent === "Aucun examen final."),
    );
    app.close();
  });

  test("adds an evaluation", async () => {
    const app = await mount();
    await openCourse(app);

    await app.click(app.query('#detail [data-act="addEval"]'));

    assert.deepEqual(app.server.lastCall("/evaluation/add").body, {
      session: "H2026",
      courseId: COURSE,
    });
    assert.equal(app.toast().text, "Élément ajouté");
    app.close();
  });

  test("opens the evaluation it just added", async () => {
    const app = await mount();
    await openCourse(app);
    const grown = baseState();
    grown.courses[1].evaluations.push({
      index: 3,
      nom: "Nouvel élément",
      ponderation: 0,
      corrigeSur: 100,
      isTeam: false,
      note: null,
      moyenne: null,
      mediane: null,
      ecartType: null,
      rangCentile: null,
      dateCible: "",
      publie: false,
      equipe: "",
      pinned: [],
    });
    app.server.reply("/evaluation/add", grown);

    await app.click(app.query('#detail [data-act="addEval"]'));

    assert.equal(field(app, "ev:nom").value, "Nouvel élément");
    app.close();
  });

  test("deletes the open evaluation", async () => {
    const app = await mount();
    await openCourse(app);
    await openEvaluation(app, 2);

    await app.click(app.query('#detail [data-act="delete"]'));

    assert.deepEqual(app.server.lastCall("/evaluation/delete").body, {
      session: "H2026",
      courseId: COURSE,
      index: 2,
    });
    assert.equal(app.toast().text, "Élément supprimé");
    app.close();
  });

  test("reorders an evaluation with alt and the arrow keys", async () => {
    const app = await mount();
    await openCourse(app);

    const row = app.query('#detail .evals__row[data-index="0"]');
    app.fire(row, "keydown");
    row.dispatchEvent(
      new app.window.KeyboardEvent("keydown", {
        key: "ArrowDown",
        altKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
    await flush();

    assert.deepEqual(app.server.lastCall("/evaluation/move").body, {
      session: "H2026",
      courseId: COURSE,
      index: 0,
      toIndex: 1,
    });
    app.close();
  });

  test("never reorders past the ends of the list", async () => {
    const app = await mount();
    await openCourse(app);

    const first = app.query('#detail .evals__row[data-index="0"]');
    first.dispatchEvent(
      new app.window.KeyboardEvent("keydown", {
        key: "ArrowUp",
        altKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
    await flush();

    assert.equal(app.server.lastCall("/evaluation/move"), null);
    app.close();
  });

  test("offers to regenerate grades only once they were touched", async () => {
    const app = await mount();
    await openCourse(app);
    assert.equal(app.query('#detail [data-act="resetGrades"]'), null);

    const touched = baseState();
    touched.courses[1].canResetGrades = true;
    await app.reload(touched);
    await openCourse(app);

    await app.click(app.query('#detail [data-act="resetGrades"]'));

    assert.deepEqual(app.server.lastCall("/grades/reset").body, {
      session: "H2026",
      courseId: COURSE,
    });
    assert.equal(app.toast().text, "Notes régénérées");
    app.close();
  });

  test("offers to restore the exam only once it was pinned", async () => {
    const app = await mount();
    await openCourse(app);
    assert.equal(app.query('#detail [data-act="examReset"]'), null);

    const pinned = baseState();
    pinned.courses[1].exam.pinned = ["dateExamen"];
    await app.reload(pinned);
    await openCourse(app);

    await app.click(app.query('#detail [data-act="examReset"]'));

    assert.deepEqual(app.server.lastCall("/exam/reset").body, {
      session: "H2026",
      courseId: COURSE,
    });
    assert.equal(app.toast().text, "Examen final rétabli");
    app.close();
  });
});

describe("reordering by hand", () => {
  const ROW_HEIGHT = 40;

  function measure(app) {
    const list = app.query("#detail .evals");
    rect(list, { left: 0, top: 0, width: 300, height: ROW_HEIGHT * 3 });
    app.queryAll("#detail .evals__item").forEach((item, index) => {
      rect(item, {
        left: 0,
        top: index * ROW_HEIGHT,
        width: 300,
        height: ROW_HEIGHT,
      });
    });
    return list;
  }

  test("drags an evaluation onto another row", async () => {
    const app = await mount();
    await openCourse(app);
    measure(app);

    app.mouse(app.query('#detail .evals__row[data-index="0"]'), "pointerdown", {
      clientY: 10,
    });
    app.mouse(app.window, "pointermove", { clientY: 60 });
    app.mouse(app.window, "pointerup", { clientY: 60 });
    await new Promise((resolve) => setTimeout(resolve, 250));
    await flush();

    assert.deepEqual(app.server.lastCall("/evaluation/move").body, {
      session: "H2026",
      courseId: COURSE,
      index: 0,
      toIndex: 1,
    });
    app.close();
  });

  test("a drag that lands where it started saves nothing", async () => {
    const app = await mount();
    await openCourse(app);
    measure(app);

    app.mouse(app.query('#detail .evals__row[data-index="0"]'), "pointerdown", {
      clientY: 10,
    });
    app.mouse(app.window, "pointermove", { clientY: 18 });
    app.mouse(app.window, "pointerup", { clientY: 18 });
    await new Promise((resolve) => setTimeout(resolve, 250));

    assert.equal(app.server.lastCall("/evaluation/move"), null);
    app.close();
  });

  test("a click without a drag still opens the evaluation", async () => {
    const app = await mount();
    await openCourse(app);
    measure(app);

    app.mouse(app.query('#detail .evals__row[data-index="1"]'), "pointerdown", {
      clientY: 50,
    });
    app.mouse(app.window, "pointerup", { clientY: 50 });
    await app.click(app.query('#detail .evals__row[data-index="1"]'));

    assert.equal(field(app, "ev:nom").value, "TP1 - Architecture microservices");
    assert.equal(app.server.lastCall("/evaluation/move"), null);
    app.close();
  });
});
