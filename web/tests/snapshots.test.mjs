import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { CURRENT_SETUP, SNAPSHOT_ITEMS, clone, flush, mount } from "./harness.mjs";

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

function pick(app, name, value) {
  const radio = app.query(`input[name="${name}"][value="${value}"]`);
  radio.checked = true;
  app.fire(radio, "change");
}

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
  const firstHint = (app) => app.query("#fSnapshotDates .choice__hint").textContent;
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
  const partHints = (app) =>
    app.queryAll("#fSnapshotParts .choice__hint").map((h) => h.textContent);

  function uncheck(app, id) {
    const box = app.byId(id);
    box.checked = false;
    app.fire(box, "change");
  }

  test("offers two date choices, realigning on today first", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const modes = app.queryAll('input[name="snapshotDates"]');
    assert.deepEqual(modes.map((m) => m.value), ["week", "exact"]);
    assert.equal(modes[0].checked, true);
    assert.equal(app.byId("snapshotLoadTitle").textContent, "Charger « Démo »");
    const titles = app.queryAll("#fSnapshotDates .choice__title").map((t) => t.textContent);
    assert.deepEqual(titles, ["Recaler sur aujourd’hui", "Garder les dates enregistrées"]);
    const hints = app.queryAll("#fSnapshotDates .choice__hint").map((h) => h.textContent);
    assert.equal(
      hints[1],
      "Rien n’est décalé: l’horaire garde les dates du 25 sept. 2026. " +
        "Pour reproduire un bug, réglez l’horloge du téléphone à cette date.",
    );
    app.close();
  });

  test("explains how a snapshot saved in week N comes back, weekday included", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: "2020-01-10", week: 4, gap: 16 })],
    });
    await openLoad(app);

    assert.equal(
      firstHint(app),
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
      firstHint(app),
      /^Retrouve la même situation: la session active s’est terminée hier et la suivante commence dans 10 jours\. .*enregistrée un mardi,/,
    );
    app.close();
  });

  test("explains that a missing next session stays missing", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: "2020-01-10", week: 6, noNextSession: true })],
    });
    await openLoad(app);

    const hints = app.queryAll("#fSnapshotDates .choice__hint").map((h) => h.textContent);
    assert.match(hints[0], /semaine 6 de la session et aucune session suivante n’est publiée\./);
    assert.match(hints[1], /La session suivante reste masquée\.$/);
    app.close();
  });

  test("says which session takes over the schedule of another one", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", date: "2026-01-30", week: 4, gap: 6 })],
    });
    await openLoad(app);

    assert.match(firstHint(app), /L’horaire de H2026 est repris dans A2026\.$/);
    app.close();
  });

  test("says there is nothing to shift for a snapshot saved this week", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", date: today(), week: 4, gap: 16 })],
    });
    await openLoad(app);

    assert.equal(firstHint(app), "Enregistrée cette semaine: rien à décaler, tout est chargé tel quel.");
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

    assert.equal(firstHint(sameDay), "Enregistrée aujourd’hui: rien à décaler, tout est chargé tel quel.");
    assert.match(firstHint(sameWeek), /^Retrouve la même situation/);
    sameDay.close();
    sameWeek.close();
  });

  test("warns before a week that the current session cannot hold", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", date: "2026-04-24", week: 17, gap: 6 })],
    });
    await openLoad(app);

    assert.match(
      firstHint(app),
      /A2026\. A2026 n’a que 16 semaines: la semaine 16 sera utilisée\.$/,
    );
    app.close();
  });

  test("applies the schedule, the student profile and the pannes by default", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const titles = app.queryAll("#fSnapshotParts .choice__title").map((t) => t.textContent);
    assert.deepEqual(titles, ["Horaire", "Profil étudiant", "Pannes"]);
    for (const id of ["fSnapshotSchedule", "fSnapshotStudent", "fSnapshotFailures"]) {
      assert.equal(app.byId(id).checked, true, id);
    }
    assert.deepEqual(partHints(app), [
      "Modifications de A2026. Décoché: les modifications actuelles sont effacées et " +
        "l’horaire est régénéré.",
      "1 champ modifié. Décoché: le profil actuel est gardé.",
      "Décoché: les pannes actuelles sont gardées.",
    ]);
    app.close();
  });

  test("lists the pannes that will be applied", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const items = app.queryAll("#fSnapshotParts .choice__list > span").map((row) =>
      row.textContent.replace(/\s+/g, " ").trim(),
    );
    assert.deepEqual(items, ["Latence 100-800 ms", "Erreurs aléatoires 30 % d'erreurs"]);
    app.close();
  });

  test("warns that exact dates without the schedule use the real calendar", async () => {
    const app = await onSnapshots();
    await openLoad(app);
    const scheduleHint = () => partHints(app)[0];

    pick(app, "snapshotDates", "exact");
    assert.equal(
      scheduleHint(),
      "Modifications de A2026. Décoché: les modifications actuelles sont effacées et " +
        "l’horaire est régénéré sur le calendrier réel.",
    );

    pick(app, "snapshotDates", "week");
    assert.doesNotMatch(scheduleHint(), /calendrier réel/);
    app.close();
  });

  test("says what loading a snapshot with nothing saved does", async () => {
    const app = await onSnapshots();
    await openLoad(app, "examen-final");

    assert.deepEqual(partHints(app), [
      "Aucune modification enregistrée: l’horaire est régénéré.",
      "Aucune modification: le profil par défaut est remis. Décoché: le profil actuel est gardé.",
      "Aucune panne: les pannes actives seront retirées. Décoché: elles sont gardées.",
    ]);
    app.close();
  });

  test("sends the default choices", async () => {
    const app = await onSnapshots();
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), {
      id: "demo",
      dates: "week",
      schedule: true,
      student: true,
      failures: true,
    });
    assert.equal(app.byId("snapshotLoadDialog").open, false);
    app.close();
  });

  for (const [id, part] of [
    ["fSnapshotSchedule", "schedule"],
    ["fSnapshotStudent", "student"],
    ["fSnapshotFailures", "failures"],
  ]) {
    test(`can leave out the ${part} alone`, async () => {
      const app = await onSnapshots();
      await openLoad(app);
      uncheck(app, id);
      await app.click(app.byId("snapshotLoadSubmit"));

      const sent = posted(app, "/load");
      assert.equal(sent[part], false);
      const others = ["schedule", "student", "failures"].filter((name) => name !== part);
      assert.deepEqual(others.map((name) => sent[name]), [true, true]);
      app.close();
    });
  }

  test("can keep exact dates and leave everything else out", async () => {
    const app = await onSnapshots();
    await openLoad(app, "examen-final");
    pick(app, "snapshotDates", "exact");
    for (const id of ["fSnapshotSchedule", "fSnapshotStudent", "fSnapshotFailures"]) {
      uncheck(app, id);
    }
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), {
      id: "examen-final",
      dates: "exact",
      schedule: false,
      student: false,
      failures: false,
    });
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

  for (const [applied, disabled] of [[true, true], [false, false]]) {
    test(`${applied ? "forgets" : "keeps"} the pannes undo history when they are ${applied ? "" : "not "}loaded`, async () => {
      const app = await mount({ failures: { latencyMs: 500 } });
      await openTab(app, "viewFailures");
      app.select(app.query('.injection[data-kind="latency"] [data-field="latencyMs"]'), "200-900");
      await flush();
      await openTab(app, "viewSnapshots");
      await openLoad(app);
      if (!applied) uncheck(app, "fSnapshotFailures");
      await app.click(app.byId("snapshotLoadSubmit"));
      await flush();
      await openTab(app, "viewFailures");

      assert.equal(app.byId("failuresUndoBtn").disabled, disabled);
      app.close();
    });
  }

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
