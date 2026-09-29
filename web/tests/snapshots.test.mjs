import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { CURRENT_SETUP, SCENARIO_ITEMS, SNAPSHOT_ITEMS, clone, flush, mount } from "./harness.mjs";

async function openTab(app, id) {
  app.fire(app.byId("viewToggle"), "change", { detail: app.byId(id) });
  await flush();
}

async function onSnapshots(options = {}) {
  const app = await mount(options);
  await openTab(app, "viewSnapshots");
  return app;
}

const rows = (app) => app.queryAll("#snapshotList .snapshot");
const rowFor = (app, id) => app.query(`#snapshotList .snapshot[data-id="${id}"]`);
const action = (app, id, act) => rowFor(app, id).querySelector(`[data-act="${act}"]`);
const posted = (app, path) => app.server.snapshots.lastCall(path)?.body;

async function saveAs(app, name) {
  await app.click(app.byId("snapshotSaveBtn"));
  app.byId("fSnapshotName").value = name;
  await app.click(app.byId("snapshotSaveSubmit"));
}

async function importFile(app, text) {
  const input = app.byId("snapshotFile");
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [{ name: "demo.json", text: async () => text }],
  });
  app.fire(input, "change");
  await flush(6);
}

describe("the snapshots tab", () => {
  test("stays out of the way until it is picked", async () => {
    const app = await mount();

    assert.equal(app.byId("snapshotsView").hidden, true);
    assert.equal(app.byId("snapshotsToolbar").hidden, true);
    assert.equal(app.server.snapshots.calls.length, 0);
    app.close();
  });

  test("replaces the other views and their toolbars once picked", async () => {
    const app = await onSnapshots();

    assert.equal(app.byId("snapshotsView").hidden, false);
    assert.equal(app.byId("snapshotsToolbar").hidden, false);
    for (const id of ["scheduleView", "scheduleToolbar", "failuresView", "studentView"]) {
      assert.equal(app.byId(id).hidden, true, id);
    }
    assert.equal(app.document.title, "Sauvegardes - ÉTS Mock");
    app.close();
  });

  test("reads the list again each time it is picked", async () => {
    const app = await onSnapshots();
    await openTab(app, "viewSchedule");
    await openTab(app, "viewSnapshots");

    assert.equal(app.server.snapshots.called("").length, 2);
    app.close();
  });

  test("lists the snapshots in the order they come", async () => {
    const app = await onSnapshots();

    assert.deepEqual(
      rows(app).map((row) => row.querySelector(".snapshot__name").textContent),
      ["Démo", "Examen final"],
    );
    app.close();
  });

  test("describes where and when each snapshot was saved", async () => {
    const app = await onSnapshots();

    assert.equal(
      rowFor(app, "demo").querySelector(".snapshot__meta").textContent,
      "A2026 · vendredi 25 sept. 2026 à 14 h 03",
    );
    app.close();
  });

  test("lists what each snapshot contains, starting with its calendar position", async () => {
    const app = await onSnapshots();

    const details = (id) => [...rowFor(app, id).querySelectorAll(".snapshot__detail")].map((t) => t.textContent);
    assert.deepEqual(details("demo"), [
      "semaine 4",
      "congé de 16 jours",
      "profil normal",
      "scénario friday-off",
      "horaire A2026",
      "profil étudiant (1 champ)",
      "2 pannes",
    ]);
    assert.deepEqual(details("examen-final"), [
      "entre deux sessions",
      "aucune session suivante",
      "profil generated-busy",
      "2 cours",
      "lun-mer",
      "matin",
    ]);
    app.close();
  });

  test("leaves out the schedule when it holds just the saved session and the next one", async () => {
    const app = await onSnapshots({
      snapshots: [{ ...clone(SNAPSHOT_ITEMS[0]), sessions: ["A2026", "H2027"] }],
    });

    const details = [...rowFor(app, "demo").querySelectorAll(".snapshot__detail")].map(
      (d) => d.textContent,
    );
    assert.ok(!details.some((text) => text.startsWith("horaire")), details.join(" · "));
    app.close();
  });

  test("names the pannes a snapshot carries", async () => {
    const app = await onSnapshots();

    const detail = rowFor(app, "demo").querySelector(".snapshot__detail--warn");
    assert.equal(detail.getAttribute("title"), "Latence : 100-800 ms\nErreurs aléatoires : 30 % d'erreurs");
    app.close();
  });

  test("invites to save a first snapshot when there is none", async () => {
    const app = await onSnapshots({ snapshots: [] });

    assert.equal(app.byId("snapshotEmpty").hidden, false);
    assert.equal(app.byId("snapshotList").hidden, true);
    app.close();
  });

  const setupRows = (app) =>
    [...app.queryAll("#currentSetup dt")].map((dt) => [
      dt.textContent,
      dt.nextElementSibling.textContent,
    ]);

  test("shows the setup the mock runs with", async () => {
    const current = {
      ...clone(CURRENT_SETUP),
      position: { week: 3, gap: 10 },
      setup: {
        profile: "semester-off",
        scenario: "friday-off",
        semesterWeek: 3,
        semesterGap: 10,
        courses: 2,
      },
      failures: { malformed: true },
    };
    const app = await onSnapshots({ current });

    assert.deepEqual(setupRows(app), [
      ["Session", "A2026 · semaine 3 sur 16"],
      ["Suivante", "H2027 · après 10 jours de congé"],
      ["Calendrier", "décalé"],
      ["Profil", "semester-off"],
      ["Scénario", "friday-off"],
      ["Génération", "2 cours"],
      ["Pannes", "réponses tronquées"],
    ]);
    app.close();
  });

  test("shows the real calendar position when nothing shifts it", async () => {
    const app = await onSnapshots();

    assert.deepEqual(setupRows(app).slice(0, 3), [
      ["Session", "A2026 · semaine 4 sur 16"],
      ["Suivante", "H2027 · après 16 jours de congé"],
      ["Calendrier", "dates réelles"],
    ]);
    app.close();
  });

  test("shows a break without a next session", async () => {
    const current = {
      ...clone(CURRENT_SETUP),
      position: { betweenSessions: true, noNextSession: true },
      setup: { profile: "normal", scenario: "none", betweenSessions: true, noNextSession: true },
    };
    const app = await onSnapshots({ current });

    assert.deepEqual(setupRows(app).slice(0, 3), [
      ["Session", "A2026 · entre deux sessions"],
      ["Suivante", "aucune (non publiée)"],
      ["Calendrier", "décalé"],
    ]);
    app.close();
  });

  test("counts down to the next session during a break", async () => {
    const current = {
      ...clone(CURRENT_SETUP),
      position: { betweenSessions: true, gap: 13 },
      setup: { profile: "normal", scenario: "none", betweenSessions: true, semesterGap: 13 },
    };
    const app = await onSnapshots({ current });

    assert.deepEqual(setupRows(app)[1], ["Suivante", "H2027 · dans 13 jours"]);
    app.close();
  });

  test("shows a session that has not started yet", async () => {
    const current = { ...clone(CURRENT_SETUP), position: { week: 0, gap: 16 } };
    const app = await onSnapshots({ current });

    assert.deepEqual(setupRows(app)[0], ["Session", "A2026 · avant le début de la session"]);
    app.close();
  });
});

describe("the built-in scenarios", () => {
  const scenarioRows = (app) => app.queryAll("#scenarioList .snapshot");
  const scenarioRow = (app, name) => app.query(`#scenarioList .snapshot[data-scenario="${name}"]`);
  const apply = (app, name) => app.click(scenarioRow(app, name).querySelector('[data-act="apply"]'));
  const badges = (app) =>
    scenarioRows(app)
      .filter((row) => row.querySelector(".snapshot__badge"))
      .map((row) => row.dataset.scenario);

  test("come before the saves, described in plain words", async () => {
    const app = await onSnapshots();

    const shown = scenarioRows(app).map((row) => [
      row.querySelector(".snapshot__name").textContent,
      row.querySelector(".snapshot__meta").textContent,
    ]);
    assert.deepEqual(shown, [
      ["Aucun scénario", "Aucune modification, dates réelles"],
      ["Prochain vendredi sans cours", "friday-off"],
      ["Semaine 15, examen final du premier cours demain", "examen-final-demain"],
    ]);
    const headings = app.queryAll("#snapshotsBoard .snapshots__heading").map((h) => h.textContent);
    assert.deepEqual(headings, ["Scénarios", "Mes sauvegardes"]);
    app.close();
  });

  test("can only be applied, not copied, exported or deleted", async () => {
    const app = await onSnapshots();

    for (const row of scenarioRows(app)) {
      const actions = [...row.querySelectorAll("[data-act]")].map((b) => b.dataset.act);
      assert.deepEqual(actions, ["apply"], row.dataset.scenario);
    }
    app.close();
  });

  test("mark the one the mock runs with", async () => {
    const plain = await onSnapshots();
    const shifted = await onSnapshots({
      current: { ...clone(CURRENT_SETUP), setup: { profile: "normal", scenario: "friday-off" } },
    });

    assert.deepEqual(badges(plain), ["none"]);
    assert.deepEqual(badges(shifted), ["friday-off"]);
    assert.equal(scenarioRow(shifted, "friday-off").querySelector(".snapshot__badge").textContent, "Actif");
    plain.close();
    shifted.close();
  });

  test("apply at once when the schedule has no edits", async () => {
    const app = await onSnapshots();
    const before = app.server.called("/state").length;
    await apply(app, "examen-final-demain");
    await flush();

    assert.deepEqual(posted(app, "/scenario"), { name: "examen-final-demain" });
    assert.equal(app.byId("snapshotConfirmDialog").open, false);
    assert.equal(app.server.called("/state").length, before + 1);
    assert.deepEqual(badges(app), ["examen-final-demain"]);
    assert.equal(app.toast().text, "Scénario « examen-final-demain » appliqué");
    app.close();
  });

  test("ask before clearing schedule edits", async () => {
    const app = await onSnapshots({ current: { ...clone(CURRENT_SETUP), scheduleEdited: true } });
    await apply(app, "friday-off");

    assert.equal(app.server.snapshots.called("/scenario").length, 0);
    assert.equal(app.byId("snapshotConfirmDialog").open, true);
    assert.equal(app.byId("snapshotConfirmTitle").textContent, "Appliquer « friday-off » ?");
    assert.match(app.byId("snapshotConfirmText").textContent, /horaire .* effacées\. Le profil, le profil étudiant et les pannes sont gardés\./);

    await app.click(app.byId("snapshotConfirmSubmit"));
    await flush();

    assert.deepEqual(posted(app, "/scenario"), { name: "friday-off" });
    app.close();
  });

  test("going back to no scenario says the real dates are back", async () => {
    const app = await onSnapshots({
      current: { ...clone(CURRENT_SETUP), setup: { profile: "normal", scenario: "friday-off" } },
    });
    await apply(app, "none");
    await flush();

    assert.deepEqual(posted(app, "/scenario"), { name: "none" });
    assert.equal(app.toast().text, "Scénario retiré: dates réelles");
    app.close();
  });

  test("keep the pannes undo history", async () => {
    const app = await mount({ failures: { latencyMs: 500 } });
    await openTab(app, "viewFailures");
    app.select(app.query('.injection[data-kind="latency"] [data-field="latencyMs"]'), "200-900");
    await flush();
    await openTab(app, "viewSnapshots");
    await apply(app, "friday-off");
    await flush();
    await openTab(app, "viewFailures");

    assert.equal(app.byId("failuresUndoBtn").disabled, false);
    app.close();
  });

  test("report a scenario the server refuses", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/scenario", { error: "Unknown scenario 'gone'" }, 400);
    await apply(app, "friday-off");
    await flush();

    assert.equal(app.toast().text, "Unknown scenario 'gone'");
    assert.deepEqual(badges(app), ["none"]);
    app.close();
  });

  test("come from the server list", async () => {
    const app = await onSnapshots({ scenarios: SCENARIO_ITEMS.slice(0, 1) });

    assert.equal(scenarioRows(app).length, 1);
    app.close();
  });
});

describe("saving a snapshot", () => {
  test("sends the name", async () => {
    const app = await onSnapshots();
    await saveAs(app, "Examen demain");

    assert.deepEqual(posted(app, "/save"), { name: "Examen demain", overwrite: false });
    assert.equal(app.byId("snapshotSaveDialog").open, false);
    assert.equal(app.toast().text, "Sauvegarde « Examen demain » enregistrée");
    assert.ok(rowFor(app, "examen-demain"));
    app.close();
  });

  test("needs a name", async () => {
    const app = await onSnapshots();
    await app.click(app.byId("snapshotSaveBtn"));
    await app.click(app.byId("snapshotSaveSubmit"));

    assert.equal(app.server.snapshots.called("/save").length, 0);
    assert.equal(app.toast().intent, "error");
    assert.equal(app.byId("snapshotSaveDialog").open, true);
    app.close();
  });

  test("asks before replacing a snapshot with the same name", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/save", { error: "A snapshot named 'Démo' already exists" }, 409);
    await saveAs(app, "Démo");

    assert.equal(app.byId("snapshotSaveDialog").open, true);
    assert.equal(app.byId("snapshotSaveConflict").hidden, false);
    assert.equal(app.byId("snapshotSaveSubmit").textContent, "Remplacer");

    await app.click(app.byId("snapshotSaveSubmit"));

    assert.equal(posted(app, "/save").overwrite, true);
    assert.equal(app.byId("snapshotSaveDialog").open, false);
    app.close();
  });

  test("forgets the replace choice when the name changes", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/save", { error: "exists" }, 409);
    await saveAs(app, "Démo");

    app.byId("fSnapshotName").value = "Autre";
    app.fire(app.byId("fSnapshotName"), "input");
    await app.click(app.byId("snapshotSaveSubmit"));

    assert.equal(posted(app, "/save").overwrite, false);
    app.close();
  });
});

describe("loading a snapshot", () => {
  async function openLoad(app, id = "demo") {
    await app.click(action(app, id, "load"));
  }

  const savedOn = (anchor) => ({ ...clone(SNAPSHOT_ITEMS[0]), anchor });
  const realign = (app) => app.byId("snapshotRealign").textContent;
  const today = () => {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  };

  const isoDay = (day) => {
    const pad = (n) => String(n).padStart(2, "0");
    return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
  };
  const otherDayThisWeek = () => {
    const day = new Date();
    day.setDate(day.getDate() + (day.getDay() === 1 ? 1 : -1));
    return isoDay(day);
  };

  function keepDates(app, keep = true) {
    const box = app.byId("fSnapshotExact");
    box.checked = keep;
    app.fire(box, "change");
  }

  test("realigns on today unless the saved dates are kept", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    assert.equal(app.byId("snapshotLoadTitle").textContent, "Charger « Démo »");
    assert.equal(app.byId("fSnapshotExact").checked, false);
    assert.equal(app.byId("snapshotExactChoice").hidden, false);
    assert.equal(app.byId("snapshotRealign").hidden, false);
    assert.equal(
      app.byId("snapshotExactHint").textContent,
      "Rien n’est décalé: l’horaire garde les dates du 25 sept. 2026. " +
        "Pour reproduire un bug, réglez l’horloge du téléphone à cette date.",
    );
    app.close();
  });

  test("has nothing else to choose", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const inputs = app.queryAll("#snapshotLoadDialog input");
    assert.deepEqual(inputs.map((input) => input.id), ["fSnapshotExact"]);
    app.close();
  });

  test("drops the realign explanation while the saved dates are kept", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    keepDates(app);
    assert.equal(app.byId("snapshotRealign").hidden, true);

    keepDates(app, false);
    assert.equal(app.byId("snapshotRealign").hidden, false);
    app.close();
  });

  test("forgets the kept dates when it opens again", async () => {
    const app = await onSnapshots();
    await openLoad(app);
    keepDates(app);
    await app.click(app.query("[data-close-snapshot-load]"));
    await openLoad(app, "examen-final");

    assert.equal(app.byId("fSnapshotExact").checked, false);
    assert.equal(app.byId("snapshotRealign").hidden, false);
    app.close();
  });

  test("explains how a snapshot saved in week N comes back, weekday included", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: "2020-01-10", week: 4, gap: 16 })],
    });
    await openLoad(app);

    assert.equal(
      realign(app),
      "Retrouve la même situation: aujourd’hui tombe à la semaine 4 de la session et la " +
        "suivante commence après 16 jours de congé. Les cours gardent leur jour de " +
        "semaine: enregistrée un vendredi, un « examen demain » ne revient qu’un vendredi.",
    );
    app.close();
  });

  test("counts down to the next session of a snapshot saved between sessions", async () => {
    const app = await onSnapshots({
      snapshots: [
        savedOn({ session: "A2026", date: "2020-12-22", betweenSessions: true, gap: 10 }),
      ],
    });
    const details = [...rowFor(app, "demo").querySelectorAll(".snapshot__detail")].map((t) => t.textContent);
    await openLoad(app);

    assert.deepEqual(details.slice(0, 2), ["entre deux sessions", "rentrée dans 10 jours"]);
    assert.match(
      realign(app),
      /^Retrouve la même situation: la session active s’est terminée hier et la suivante commence dans 10 jours\. .*enregistrée un mardi,/,
    );
    app.close();
  });

  test("explains that a missing next session stays missing", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: "2020-01-10", week: 6, noNextSession: true })],
    });
    await openLoad(app);

    assert.match(realign(app), /semaine 6 de la session et aucune session suivante n’est publiée\./);
    assert.match(app.byId("snapshotExactHint").textContent, /La session suivante reste masquée\.$/);
    app.close();
  });

  test("says which session takes over the schedule of another one", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", date: "2026-01-30", week: 4, gap: 6 })],
    });
    await openLoad(app);

    assert.match(realign(app), /L’horaire de H2026 est repris dans A2026\.$/);
    app.close();
  });

  test("has no dates to choose for a snapshot saved this week", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: today(), week: 4, gap: 16 })],
    });
    await openLoad(app);

    assert.equal(realign(app), "Enregistrée cette semaine: rien à décaler, tout est chargé tel quel.");
    assert.equal(app.byId("snapshotExactChoice").hidden, true);
    app.close();
  });

  test("only skips the shift of a break saved today", async () => {
    const between = { session: "A2026", betweenSessions: true, gap: 10 };
    const sameDay = await onSnapshots({ snapshots: [savedOn({ ...between, date: today() })] });
    await openLoad(sameDay);
    const sameWeek = await onSnapshots({
      snapshots: [savedOn({ ...between, date: otherDayThisWeek() })],
    });
    await openLoad(sameWeek);

    assert.equal(realign(sameDay), "Enregistrée aujourd’hui: rien à décaler, tout est chargé tel quel.");
    assert.equal(sameDay.byId("snapshotExactChoice").hidden, true);
    assert.match(realign(sameWeek), /^Retrouve la même situation/);
    assert.equal(sameWeek.byId("snapshotExactChoice").hidden, false);
    sameDay.close();
    sameWeek.close();
  });

  test("warns before a week that the current session cannot hold", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", date: "2026-04-24", week: 17, gap: 6 })],
    });
    await openLoad(app);

    assert.match(realign(app), /A2026\. A2026 n’a que 16 semaines: la semaine 16 sera utilisée\.$/);
    app.close();
  });

  test("sends the realigned dates by default", async () => {
    const app = await onSnapshots();
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), { id: "demo", dates: "week" });
    assert.equal(app.byId("snapshotLoadDialog").open, false);
    app.close();
  });

  test("sends the saved dates when they are kept", async () => {
    const app = await onSnapshots();
    await openLoad(app, "examen-final");
    keepDates(app);
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), { id: "examen-final", dates: "exact" });
    app.close();
  });

  test("refreshes the schedule and the pannes afterwards", async () => {
    const app = await onSnapshots();
    const before = app.server.called("/state").length;
    const pannes = app.server.admin.called("").length;
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));
    await flush();

    assert.equal(app.server.called("/state").length, before + 1);
    assert.equal(app.server.admin.called("").length, pannes + 1);
    assert.equal(app.status(), "Sauvegarde « Démo » chargée.");
    assert.equal(app.toast().text, "Sauvegarde « Démo » chargée");
    app.close();
  });

  test("forgets the pannes undo history", async () => {
    const app = await mount({ failures: { latencyMs: 500 } });
    await openTab(app, "viewFailures");
    app.select(app.query('.injection[data-kind="latency"] [data-field="latencyMs"]'), "200-900");
    await flush();
    await openTab(app, "viewSnapshots");
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));
    await flush();
    await openTab(app, "viewFailures");

    assert.equal(app.byId("failuresUndoBtn").disabled, true);
    app.close();
  });

  test("tells what had to be adjusted", async () => {
    const notice = "A2026 n'a que 16 semaines: la semaine 16 est utilisée au lieu de la semaine 17.";
    const app = await onSnapshots({ notices: [notice] });
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));
    await flush();

    assert.equal(app.status(), notice);
    app.close();
  });

  test("keeps the dialog open when the server refuses", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/load", { error: "Unknown profile 'gone'" }, 400);
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.equal(app.byId("snapshotLoadDialog").open, true);
    assert.equal(app.toast().text, "Unknown profile 'gone'");
    app.close();
  });
});

describe("managing snapshots", () => {
  test("deleting asks first", async () => {
    const app = await onSnapshots();
    await app.click(action(app, "demo", "delete"));

    assert.equal(app.byId("snapshotConfirmDialog").open, true);
    assert.match(app.byId("snapshotConfirmText").textContent, /snapshots\/demo\.json/);
    assert.equal(app.server.snapshots.called("/delete").length, 0);

    await app.click(app.byId("snapshotConfirmSubmit"));

    assert.deepEqual(posted(app, "/delete"), { id: "demo" });
    assert.equal(rowFor(app, "demo"), null);
    app.close();
  });

  test("exporting downloads the snapshot file", async () => {
    const app = await onSnapshots();
    const clicked = [];
    app.window.HTMLAnchorElement.prototype.click = function () {
      clicked.push({ href: this.getAttribute("href"), download: this.download });
    };
    await app.click(action(app, "examen-final", "export"));

    assert.deepEqual(clicked, [
      {
        href: "/editor/api/snapshots/export?id=examen-final",
        download: "examen-final.json",
      },
    ]);
    app.close();
  });

  test("importing sends the file content", async () => {
    const app = await onSnapshots();
    await importFile(app, JSON.stringify({ format: 1, name: "Reçu" }));

    assert.deepEqual(posted(app, "/import"), {
      snapshot: { format: 1, name: "Reçu" },
      overwrite: false,
    });
    assert.equal(app.toast().text, "Sauvegarde « Reçu » importée");
    app.close();
  });

  test("importing over an existing name asks first", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/import", { error: "exists" }, 409);
    await importFile(app, JSON.stringify({ format: 1, name: "Démo" }));

    assert.equal(app.byId("snapshotConfirmDialog").open, true);
    await app.click(app.byId("snapshotConfirmSubmit"));

    assert.equal(posted(app, "/import").overwrite, true);
    app.close();
  });

  test("a file that is not JSON is refused before reaching the server", async () => {
    const app = await onSnapshots();
    await importFile(app, "not json");

    assert.equal(app.server.snapshots.called("/import").length, 0);
    assert.equal(app.toast().intent, "error");
    app.close();
  });

  function clipboard(app, writeText) {
    Object.defineProperty(app.window.navigator, "clipboard", {
      configurable: true,
      value: writeText ? { writeText } : undefined,
    });
  }

  test("copying puts the snapshot code on the clipboard", async () => {
    const app = await onSnapshots();
    const copied = [];
    clipboard(app, async (text) => copied.push(text));
    await app.click(action(app, "demo", "copy"));
    await flush();

    assert.equal(app.server.snapshots.called("/code?id=demo").length, 1);
    assert.deepEqual(copied, ["CODE-Démo"]);
    assert.equal(app.toast().text, "Code de « Démo » copié");
    app.close();
  });

  test("copying falls back on a selection when the clipboard API is missing", async () => {
    const app = await onSnapshots();
    const copied = [];
    clipboard(app, null);
    app.document.execCommand = (command) => {
      copied.push([command, app.document.querySelector("body > textarea").value]);
      return true;
    };
    await app.click(action(app, "demo", "copy"));
    await flush();

    assert.deepEqual(copied, [["copy", "CODE-Démo"]]);
    assert.equal(app.document.querySelector("body > textarea"), null);
    assert.equal(app.toast().text, "Code de « Démo » copié");
    app.close();
  });

  test("copying points to the export when nothing can copy", async () => {
    const app = await onSnapshots();
    clipboard(app, async () => {
      throw new Error("denied");
    });
    app.document.execCommand = () => false;
    await app.click(action(app, "demo", "copy"));
    await flush();

    assert.equal(app.toast().intent, "error");
    assert.match(app.toast().text, /exportez le fichier/);
    app.close();
  });

  test("copying reports a snapshot the server cannot find", async () => {
    const app = await onSnapshots();
    clipboard(app, async () => assert.fail("nothing to copy"));
    app.server.snapshots.once("/code?id=demo", { error: "Snapshot 'demo' not found" }, 400);
    await app.click(action(app, "demo", "copy"));
    await flush();

    assert.equal(app.toast().text, "Snapshot 'demo' not found");
    app.close();
  });

  async function openImport(app) {
    await app.click(app.byId("snapshotImportBtn"));
  }

  async function paste(app, text) {
    await openImport(app);
    app.byId("fSnapshotCode").value = text;
    await app.click(app.byId("snapshotImportSubmit"));
    await flush();
  }

  test("importing opens an empty paste box", async () => {
    const app = await onSnapshots();
    await openImport(app);
    app.byId("fSnapshotCode").value = "ancien";
    app.byId("snapshotImportDialog").hide();
    await openImport(app);

    assert.equal(app.byId("snapshotImportDialog").open, true);
    assert.equal(app.byId("fSnapshotCode").value, "");
    assert.equal(app.server.snapshots.called("/import").length, 0);
    app.close();
  });

  test("importing sends a pasted code", async () => {
    const app = await onSnapshots();
    await paste(app, "  CODE-Reçue\n");

    assert.deepEqual(posted(app, "/import"), { code: "CODE-Reçue", overwrite: false });
    assert.equal(app.byId("snapshotImportDialog").open, false);
    assert.equal(app.toast().text, "Sauvegarde « Reçue » importée");
    assert.ok(rowFor(app, "recue"));
    app.close();
  });

  test("Enter in the paste box imports", async () => {
    const app = await onSnapshots();
    await openImport(app);
    const box = app.byId("fSnapshotCode");
    box.value = "CODE-Reçue";
    box.dispatchEvent(new app.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flush();

    assert.deepEqual(posted(app, "/import"), { code: "CODE-Reçue", overwrite: false });
    app.close();
  });

  test("a pasted export file is imported as a snapshot", async () => {
    const app = await onSnapshots();
    await paste(app, JSON.stringify({ format: 2, name: "Collée" }, null, 2));

    assert.deepEqual(posted(app, "/import"), {
      snapshot: { format: 2, name: "Collée" },
      overwrite: false,
    });
    app.close();
  });

  test("broken pasted JSON is refused before reaching the server", async () => {
    const app = await onSnapshots();
    await paste(app, '{"format": 2,');

    assert.equal(app.server.snapshots.called("/import").length, 0);
    assert.equal(app.toast().intent, "error");
    assert.equal(app.byId("snapshotImportDialog").open, true);
    app.close();
  });

  test("an empty paste box asks for a code", async () => {
    const app = await onSnapshots();
    await paste(app, "   ");

    assert.equal(app.server.snapshots.called("/import").length, 0);
    assert.equal(app.toast().text, "Collez le code d’une sauvegarde");
    assert.equal(app.byId("snapshotImportDialog").open, true);
    app.close();
  });

  test("a code the server refuses keeps the paste box open", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once("/import", { error: "This is not a snapshot code" }, 400);
    await paste(app, "abc");

    assert.equal(app.byId("snapshotImportDialog").open, true);
    assert.equal(app.toast().text, "This is not a snapshot code");
    app.close();
  });

  test("a code for an existing name asks before replacing it", async () => {
    const app = await onSnapshots();
    app.server.snapshots.once(
      "/import",
      { error: "A snapshot named 'Démo' already exists", name: "Démo" },
      409,
    );
    await paste(app, "CODE-Démo");

    assert.equal(app.byId("snapshotImportDialog").open, false);
    assert.equal(app.byId("snapshotConfirmDialog").open, true);
    assert.equal(app.byId("snapshotConfirmTitle").textContent, "Remplacer « Démo » ?");

    await app.click(app.byId("snapshotConfirmSubmit"));

    assert.deepEqual(posted(app, "/import"), { code: "CODE-Démo", overwrite: true });
    app.close();
  });

  test("the paste box can still pick a file", async () => {
    const app = await onSnapshots();
    let picked = 0;
    app.byId("snapshotFile").click = () => picked++;
    await openImport(app);
    await app.click(app.byId("snapshotImportFileBtn"));

    assert.equal(picked, 1);
    app.close();
  });

  test("undo shortcuts do nothing on this tab", async () => {
    const app = await onSnapshots();
    const posts = app.server.calls.length;

    app.key("z", { ctrlKey: true });
    app.key("y", { ctrlKey: true });
    await flush();

    assert.equal(app.server.calls.length, posts);
    app.close();
  });
});
