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

async function saveAs(app, name, scope = "personal") {
  await app.click(app.byId("snapshotSaveBtn"));
  app.byId("fSnapshotName").value = name;
  pick(app, "snapshotScope", scope);
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
    assert.equal(app.document.title, "Instantanés - ÉTS Mock");
    app.close();
  });

  test("reads the list again each time it is picked", async () => {
    const app = await onSnapshots();
    await openTab(app, "viewSchedule");
    await openTab(app, "viewSnapshots");

    assert.equal(app.server.snapshots.called("").length, 2);
    app.close();
  });

  test("lists personal snapshots before shared ones", async () => {
    const app = await onSnapshots();

    const groups = app.queryAll(".snapshot-group").map((node) => node.dataset.group);
    assert.deepEqual(groups, ["personal", "shared"]);
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
      "A2026 · semaine 4 · 25 sept. 2026 à 14 h 03",
    );
    app.close();
  });

  test("tags what each snapshot contains", async () => {
    const app = await onSnapshots();

    const tags = (id) => [...rowFor(app, id).querySelectorAll(".tag")].map((t) => t.textContent);
    assert.deepEqual(tags("demo"), [
      "profil normal",
      "scénario friday-off",
      "horaire A2026",
      "profil étudiant (1 champ)",
      "2 pannes",
    ]);
    assert.deepEqual(tags("examen-final"), [
      "profil generated-busy",
      "semaine 3 forcée",
      "2 cours",
      "lun-mer",
      "matin",
    ]);
    app.close();
  });

  test("names the pannes a snapshot carries", async () => {
    const app = await onSnapshots();

    const tag = rowFor(app, "demo").querySelector(".tag--warn");
    assert.equal(tag.getAttribute("title"), "Latence : 100-800 ms\nErreurs aléatoires : 30 % d'erreurs");
    app.close();
  });

  test("says so when a scope has no snapshot", async () => {
    const app = await onSnapshots({ snapshots: [SNAPSHOT_ITEMS[0]] });

    assert.equal(
      app.query('[data-group="shared"] .snapshot-group__empty').textContent,
      "Aucun instantané partagé.",
    );
    app.close();
  });

  test("invites to save a first snapshot when there is none", async () => {
    const app = await onSnapshots({ snapshots: [] });

    assert.equal(app.byId("snapshotEmpty").hidden, false);
    assert.equal(app.byId("snapshotList").hidden, true);
    app.close();
  });

  test("shows the setup the mock runs with", async () => {
    const current = {
      ...clone(CURRENT_SETUP),
      setup: { profile: "semester-off", scenario: "friday-off", semesterWeek: 3, courses: 2 },
      failures: { malformed: true },
    };
    const app = await onSnapshots({ current });

    const pairs = [...app.queryAll("#currentSetup dt")].map((dt) => [
      dt.textContent,
      dt.nextElementSibling.textContent,
    ]);
    assert.deepEqual(pairs, [
      ["Session", "A2026 · semaine 4 sur 16"],
      ["Profil", "semester-off"],
      ["Scénario", "friday-off"],
      ["Semaine", "semaine 3 forcée"],
      ["Génération", "2 cours"],
      ["Pannes", "réponses tronquées"],
    ]);
    app.close();
  });
});

describe("saving a snapshot", () => {
  test("sends the name and the chosen scope", async () => {
    const app = await onSnapshots();
    await saveAs(app, "Examen demain", "shared");

    assert.deepEqual(posted(app, "/save"), {
      name: "Examen demain",
      scope: "shared",
      overwrite: false,
    });
    assert.equal(app.byId("snapshotSaveDialog").open, false);
    assert.equal(app.toast().text, "Instantané « Examen demain » enregistré");
    assert.ok(rowFor(app, "examen-demain"));
    app.close();
  });

  test("keeps personal as the default scope", async () => {
    const app = await onSnapshots();
    await app.click(app.byId("snapshotSaveBtn"));
    app.byId("fSnapshotName").value = "Démo 2";
    await app.click(app.byId("snapshotSaveSubmit"));

    assert.equal(posted(app, "/save").scope, "personal");
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

  test("offers the three date modes, realigning on today first", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const modes = app.queryAll('input[name="snapshotDates"]');
    assert.deepEqual(modes.map((m) => m.value), ["week", "exact", "setup"]);
    assert.equal(modes[0].checked, true);
    assert.equal(app.byId("snapshotLoadTitle").textContent, "Charger « Démo »");
    const titles = app.queryAll("#fSnapshotDates .choice__title").map((t) => t.textContent);
    assert.deepEqual(titles, [
      "Recaler sur aujourd’hui",
      "Garder les dates enregistrées",
      "Réglages seulement",
    ]);
    const hints = app.queryAll("#fSnapshotDates .choice__hint").map((h) => h.textContent);
    assert.match(hints[1], /^Rien n’est décalé: l’horaire garde les dates du 25 sept\. 2026\./);
    assert.match(hints[2], /profil étudiant enregistré est chargé/);
    app.close();
  });

  test("explains how an older snapshot is realigned on today", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", week: 4, date: "2020-01-10" })],
    });
    await openLoad(app);

    assert.equal(
      firstHint(app),
      "Retrouve la même situation aujourd’hui: toutes les dates sont décalées pour " +
        "qu’aujourd’hui tombe à la semaine 4 de la session, comme au moment de " +
        "l’enregistrement.",
    );
    app.close();
  });

  test("says which session takes over the schedule of another one", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", week: 4, date: "2026-01-30" })],
    });
    await openLoad(app);

    assert.match(firstHint(app), /L’horaire de H2026 est repris dans A2026\.$/);
    app.close();
  });

  test("says there is nothing to shift for a snapshot saved this week", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "A2026", week: 4, date: today() })],
    });
    await openLoad(app);

    assert.equal(firstHint(app), "Enregistré cette semaine: rien à décaler, tout est chargé tel quel.");
    app.close();
  });

  test("warns before a week that the current session cannot hold", async () => {
    const app = await onSnapshots({
      snapshots: [savedOn({ session: "H2026", week: 17, date: "2026-04-30" })],
    });
    await openLoad(app);

    assert.match(
      firstHint(app),
      /A2026\. A2026 n’a que 16 semaines: la semaine 16 sera utilisée\.$/,
    );
    app.close();
  });

  test("lists the pannes that will be applied", async () => {
    const app = await onSnapshots();
    await openLoad(app);

    const items = app.queryAll(".snapshot-failures__list li").map((li) =>
      li.textContent.replace(/\s+/g, " ").trim(),
    );
    assert.deepEqual(items, ["Latence 100-800 ms", "Erreurs aléatoires 30 % d'erreurs"]);
    assert.equal(app.byId("fSnapshotFailures").checked, true);
    app.close();
  });

  test("warns that loading a snapshot without pannes clears the active ones", async () => {
    const app = await onSnapshots();
    await openLoad(app, "examen-final");

    assert.match(app.text(".snapshot-failures__none"), /pannes actives seront retirées/);
    app.close();
  });

  test("sends the default choices", async () => {
    const app = await onSnapshots();
    await openLoad(app);
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), {
      scope: "personal",
      id: "demo",
      dates: "week",
      failures: true,
    });
    assert.equal(app.byId("snapshotLoadDialog").open, false);
    app.close();
  });

  test("can keep exact dates and skip the pannes", async () => {
    const app = await onSnapshots();
    await openLoad(app, "examen-final");
    pick(app, "snapshotDates", "exact");
    const toggle = app.byId("fSnapshotFailures");
    toggle.checked = false;
    app.fire(toggle, "change");
    await app.click(app.byId("snapshotLoadSubmit"));

    assert.deepEqual(posted(app, "/load"), {
      scope: "shared",
      id: "examen-final",
      dates: "exact",
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
    assert.equal(app.status(), "Instantané « Démo » chargé.");
    assert.equal(app.toast().text, "Instantané « Démo » chargé");
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
    assert.match(app.byId("snapshotConfirmText").textContent, /snapshots\/personal\/demo\.json/);
    assert.equal(app.server.snapshots.called("/delete").length, 0);

    await app.click(app.byId("snapshotConfirmSubmit"));

    assert.deepEqual(posted(app, "/delete"), { scope: "personal", id: "demo" });
    assert.equal(rowFor(app, "demo"), null);
    app.close();
  });

  test("a personal snapshot can be shared and back", async () => {
    const app = await onSnapshots();
    await app.click(action(app, "demo", "move"));

    assert.deepEqual(posted(app, "/move"), { scope: "personal", id: "demo", to: "shared" });
    assert.equal(rowFor(app, "demo").closest(".snapshot-group").dataset.group, "shared");
    assert.equal(action(app, "demo", "move").getAttribute("title"), "Rendre personnel");

    await app.click(action(app, "demo", "move"));

    assert.deepEqual(posted(app, "/move"), { scope: "shared", id: "demo", to: "personal" });
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
        href: "/editor/api/snapshots/export?scope=shared&id=examen-final",
        download: "examen-final.json",
      },
    ]);
    app.close();
  });

  test("importing sends the file content as a personal snapshot", async () => {
    const app = await onSnapshots();
    await importFile(app, JSON.stringify({ format: 1, name: "Reçu" }));

    assert.deepEqual(posted(app, "/import"), {
      snapshot: { format: 1, name: "Reçu" },
      scope: "personal",
      overwrite: false,
    });
    assert.equal(app.toast().text, "Instantané « Reçu » importé");
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
