import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { at, callEntry, flush, markerEntry, mount } from "./harness.mjs";

const GRADES = {
  endpoint: "listeElementsEvaluation",
  params: { session: "H2026", sigle: "LOG430", groupe: "02" },
};

async function openCalls(app) {
  app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewCalls") });
  await flush();
}

async function onCalls(calls = []) {
  const app = await mount({ calls });
  await openCalls(app);
  return app;
}

async function refresh(app) {
  app.fire(app.document, "visibilitychange");
  await flush();
}

const rowFor = (app, id) => app.query(`#callRows tr[data-id="${id}"]`);

const rowIds = (app) => app.queryAll("#callRows tr").map((row) => Number(row.dataset.id));

const cells = (row) =>
  [...row.cells].map((cell) => cell.textContent.trim().replace(/\s+/g, " "));

const chips = (row) =>
  [...row.querySelectorAll(".call-failure")].map((chip) => ({
    text: chip.textContent.trim(),
    icon: chip.querySelector("svg").dataset.name,
  }));

const reads = (app) => app.server.callLog.called("", "GET").map((call) => call.query);

const stats = (app) =>
  app.queryAll("#endpointStats .endpoint-stat").map((item) => ({
    endpoint: item.dataset.endpoint,
    count: item.querySelector(".endpoint-stat__count").textContent.trim(),
    details: item.querySelector(".endpoint-stat__details").textContent.trim(),
  }));

describe("the calls tab", () => {
  test("stays out of the way until it is picked", async () => {
    const app = await mount();

    assert.equal(app.byId("callsView").hidden, true);
    assert.equal(app.byId("callsToolbar").hidden, true);
    assert.deepEqual(app.server.callLog.calls, []);
    app.close();
  });

  test("replaces the other views and their toolbars once picked", async () => {
    const app = await onCalls();

    assert.equal(app.byId("callsView").hidden, false);
    assert.equal(app.byId("callsToolbar").hidden, false);
    assert.equal(app.byId("scheduleView").hidden, true);
    assert.equal(app.byId("scheduleControls").hidden, true);
    assert.equal(app.byId("scheduleToolbar").hidden, true);
    assert.equal(app.byId("failuresView").hidden, true);
    assert.equal(app.byId("failuresToolbar").hidden, true);
    assert.equal(app.document.title, "Appels - ÉTS Mock");
    app.close();
  });

  test("gives the schedule back when the schedule tab is picked", async () => {
    const app = await onCalls();

    app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewSchedule") });
    await flush();

    assert.equal(app.byId("callsView").hidden, true);
    assert.equal(app.byId("callsToolbar").hidden, true);
    assert.equal(app.byId("scheduleView").hidden, false);
    assert.equal(app.blocks().length > 0, true);
    app.close();
  });

  test("leaves schedule shortcuts alone while it is open", async () => {
    const app = await mount();
    await app.click(app.blockFor("LOG430-02:0"));
    await openCalls(app);

    app.key("Delete");
    app.key("z", { ctrlKey: true });
    app.key("ArrowRight");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    assert.equal(app.server.lastCall("/undo"), null);
    assert.equal(app.byId("weekSelect").value, "1");
    app.close();
  });
});

describe("the call list", () => {
  test("says so when no call came in", async () => {
    const app = await onCalls();

    assert.equal(app.byId("callsEmpty").hidden, false);
    assert.equal(app.byId("callsTable").hidden, true);
    assert.equal(app.byId("callsClearBtn").disabled, true);
    app.close();
  });

  test("shows the time, endpoint, parameters, status, duration and size of a call", async () => {
    const app = await onCalls([
      callEntry({ id: 1, ...GRADES, time: at(9, 5, 7, 42), durationMs: 12.4, bytes: 2150 }),
    ]);

    assert.equal(app.byId("callsEmpty").hidden, true);
    assert.equal(app.byId("callsTable").hidden, false);
    assert.deepEqual(cells(rowFor(app, 1)), [
      "09:05:07.042",
      "listeElementsEvaluation",
      "session=H2026 sigle=LOG430 groupe=02",
      "200",
      "12 ms",
      "2,1 ko",
      "",
    ]);
    assert.equal(
      rowFor(app, 1).querySelector(".calls__endpoint").title,
      "/api/Etudiant/listeElementsEvaluation",
    );
    app.close();
  });

  test("lists calls in the order they came in", async () => {
    const app = await onCalls([
      callEntry({ id: 1, endpoint: "infoEtudiant" }),
      callEntry({ id: 2, endpoint: "listeSessions" }),
    ]);

    assert.deepEqual(rowIds(app), [1, 2]);
    app.close();
  });

  test("scales durations and sizes to something readable", async () => {
    const app = await onCalls([
      callEntry({ id: 1, durationMs: 3.2, bytes: 512 }),
      callEntry({ id: 2, durationMs: 1840, bytes: 3.5 * 1024 * 1024 }),
    ]);

    assert.deepEqual(cells(rowFor(app, 1)).slice(4, 6), ["3,2 ms", "512 o"]);
    assert.deepEqual(cells(rowFor(app, 2)).slice(4, 6), ["1,8 s", "3,5 Mo"]);
    app.close();
  });

  test("tells successes, refusals and server errors apart", async () => {
    const app = await onCalls([
      callEntry({ id: 1, status: 200 }),
      callEntry({ id: 2, status: 404 }),
      callEntry({ id: 3, status: 503 }),
    ]);

    const tone = (id) => rowFor(app, id).querySelector(".status").className;
    assert.equal(tone(1), "status status--ok");
    assert.equal(tone(2), "status status--warn");
    assert.equal(tone(3), "status status--error");
    app.close();
  });

  test("shows a call that is still running", async () => {
    const app = await onCalls([
      callEntry({ id: 1, status: null, durationMs: null, bytes: null }),
    ]);

    const row = rowFor(app, 1);
    assert.equal(row.classList.contains("is-pending"), true);
    assert.deepEqual(cells(row).slice(3, 6), ["en cours", "", ""]);
    app.close();
  });

  test("names every failure injected into a call", async () => {
    const app = await onCalls([
      callEntry({ id: 1, failures: [{ kind: "latency", ms: 340 }, { kind: "malformed" }] }),
      callEntry({ id: 2, status: 504, failures: [{ kind: "timeout", seconds: 30 }] }),
      callEntry({ id: 3, status: 503, failures: [{ kind: "fail" }] }),
      callEntry({ id: 4, status: 500, failures: [{ kind: "errorRate" }] }),
      callEntry({ id: 5, status: 401, failures: [{ kind: "auth" }] }),
    ]);

    assert.deepEqual(chips(rowFor(app, 1)), [
      { text: "Latence 340 ms", icon: "timer" },
      { text: "Réponse tronquée", icon: "documentError" },
    ]);
    assert.deepEqual(chips(rowFor(app, 2)), [
      { text: "Expiration après 30 s", icon: "hourglass" },
    ]);
    assert.deepEqual(chips(rowFor(app, 3)), [
      { text: "Endpoint en panne", icon: "plugDisconnected" },
    ]);
    assert.deepEqual(chips(rowFor(app, 4)), [{ text: "Erreur aléatoire", icon: "warning" }]);
    assert.deepEqual(chips(rowFor(app, 5)), [
      { text: "Authentification manquante", icon: "lockClosed" },
    ]);
    app.close();
  });

  test("shows what the app sent as text", async () => {
    const app = await onCalls([
      callEntry({ id: 1, params: { chaine: "<b>salut</b>" } }),
    ]);

    const params = rowFor(app, 1).querySelector(".calls__params");
    assert.equal(params.querySelector("b"), null);
    assert.equal(params.textContent.trim(), "chaine=<b>salut</b>");
    app.close();
  });
});

describe("repeated calls", () => {
  const repeat = (app, id) => rowFor(app, id).querySelector(".repeat");

  test("are flagged with how many identical calls were made", async () => {
    const app = await onCalls([
      callEntry({ id: 1, ...GRADES }),
      callEntry({ id: 2, endpoint: "listeSessions" }),
      callEntry({ id: 3, ...GRADES }),
      callEntry({ id: 4, ...GRADES }),
    ]);

    assert.equal(repeat(app, 1).textContent.trim(), "×3");
    assert.equal(repeat(app, 3).textContent.trim(), "×3");
    assert.equal(repeat(app, 4).title.startsWith("Appel identique 3 sur 3"), true);
    assert.equal(repeat(app, 2), null);
    app.close();
  });

  test("are highlighted from the second one on", async () => {
    const app = await onCalls([
      callEntry({ id: 1, ...GRADES }),
      callEntry({ id: 2, ...GRADES }),
    ]);

    assert.equal(rowFor(app, 1).classList.contains("is-repeat"), false);
    assert.equal(rowFor(app, 2).classList.contains("is-repeat"), true);
    app.close();
  });

  test("need the same parameters, in any order", async () => {
    const app = await onCalls([
      callEntry({ id: 1, ...GRADES }),
      callEntry({ id: 2, ...GRADES, params: { groupe: "02", sigle: "LOG430", session: "H2026" } }),
      callEntry({ id: 3, ...GRADES, params: { ...GRADES.params, groupe: "01" } }),
    ]);

    assert.equal(rowFor(app, 2).classList.contains("is-repeat"), true);
    assert.equal(repeat(app, 3), null);
    app.close();
  });

  test("need the same endpoint", async () => {
    const app = await onCalls([
      callEntry({ id: 1, endpoint: "listeCours" }),
      callEntry({ id: 2, endpoint: "listeSessions" }),
    ]);

    assert.equal(app.queryAll(".repeat").length, 0);
    app.close();
  });
});

describe("markers", () => {
  test("split the list and sum up the calls that followed them", async () => {
    const app = await onCalls([
      callEntry({ id: 1 }),
      markerEntry({ id: 2, label: "notes ouvertes", time: at(14, 5, 0, 120) }),
      callEntry({ id: 3, ...GRADES, bytes: 1024 }),
      callEntry({ id: 4, ...GRADES, bytes: 2048 }),
      markerEntry({ id: 5, label: "horaire ouvert" }),
    ]);

    assert.deepEqual(rowIds(app), [1, 2, 3, 4, 5]);
    const marker = rowFor(app, 2);
    assert.equal(marker.className, "marker");
    assert.equal(marker.querySelector(".calls__time").textContent, "14:05:00.120");
    assert.equal(marker.querySelector(".marker__label").textContent, "notes ouvertes");
    assert.equal(marker.querySelector(".marker__summary").textContent, "2 appels · 3 ko");
    assert.equal(
      rowFor(app, 5).querySelector(".marker__summary").textContent,
      "aucun appel",
    );
    app.close();
  });

  test("are added with the label typed in", async () => {
    const app = await onCalls([callEntry({ id: 1 })]);

    app.type(app.byId("markerLabel"), "  notes ouvertes ");
    await app.click(app.byId("markerAddBtn"));

    assert.deepEqual(app.server.callLog.called("/marker")[0].body, {
      label: "notes ouvertes",
    });
    assert.deepEqual(rowIds(app), [1, 2]);
    assert.equal(rowFor(app, 2).querySelector(".marker__label").textContent, "notes ouvertes");
    assert.equal(app.byId("markerLabel").value, "");
    assert.equal(app.toast().text, "Marqueur ajouté");
    app.close();
  });

  test("are added when Enter is pressed in the label field", async () => {
    const app = await onCalls();

    app.type(app.byId("markerLabel"), "cours ouvert");
    app.byId("markerLabel").dispatchEvent(
      new app.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
    await flush();

    assert.equal(app.server.callLog.called("/marker")[0].body.label, "cours ouvert");
    app.close();
  });

  test("are numbered when left without a label", async () => {
    const app = await onCalls([markerEntry({ id: 1 })]);

    await app.click(app.byId("markerAddBtn"));

    assert.equal(app.server.callLog.called("/marker")[0].body.label, "Marqueur 2");
    app.close();
  });

  test("keep the label when the server refuses them", async () => {
    const app = await onCalls();
    app.server.callLog.fail("POST", "/marker", { detail: "Libellé trop long" }, 422);

    app.type(app.byId("markerLabel"), "notes ouvertes");
    await app.click(app.byId("markerAddBtn"));

    assert.equal(app.toast().intent, "error");
    assert.equal(app.toast().text, "Libellé trop long");
    assert.equal(app.byId("markerLabel").value, "notes ouvertes");
    app.close();
  });
});

describe("per-endpoint stats", () => {
  test("count calls, total size and average duration, busiest first", async () => {
    const app = await onCalls([
      callEntry({ id: 1, endpoint: "listeCours", durationMs: 8, bytes: 900 }),
      callEntry({ id: 2, ...GRADES, durationMs: 10, bytes: 1024 }),
      callEntry({ id: 3, ...GRADES, durationMs: 20, bytes: 1024 }),
      callEntry({ id: 4, ...GRADES, params: {}, durationMs: 30, bytes: 1024 }),
    ]);

    assert.deepEqual(stats(app), [
      {
        endpoint: "listeElementsEvaluation",
        count: "3 appels",
        details: "3 ko au total · 20 ms en moyenne · 1 répété",
      },
      { endpoint: "listeCours", count: "1 appel", details: "900 o au total · 8 ms en moyenne" },
    ]);
    assert.equal(
      app.byId("callsTotal").textContent,
      "4 appels · 3,9 ko au total · 17 ms en moyenne · 1 répété",
    );
    app.close();
  });

  test("leave calls still running out of the size and average", async () => {
    const app = await onCalls([
      callEntry({ id: 1, durationMs: 10, bytes: 1024 }),
      callEntry({ id: 2, params: { session: "H2026" }, status: null, durationMs: null, bytes: null }),
      callEntry({ id: 3, endpoint: "listeCoequipiers", status: null, durationMs: null, bytes: null }),
    ]);

    assert.deepEqual(stats(app), [
      { endpoint: "listeCours", count: "2 appels", details: "1 ko au total · 10 ms en moyenne" },
      { endpoint: "listeCoequipiers", count: "1 appel", details: "en cours" },
    ]);
    app.close();
  });

  test("ignore markers", async () => {
    const app = await onCalls([markerEntry({ id: 1 })]);

    assert.deepEqual(stats(app), []);
    assert.equal(app.byId("callsTotal").textContent, "Aucun appel.");
    app.close();
  });
});

describe("keeping the list current", () => {
  test("asks only for entries it does not have yet", async () => {
    const app = await onCalls([callEntry({ id: 1 }), callEntry({ id: 2 })]);

    await refresh(app);

    assert.deepEqual(reads(app), ["after=0", "after=2"]);
    app.close();
  });

  test("shows calls that came in since the last look", async () => {
    const app = await onCalls([callEntry({ id: 1 })]);

    app.server.callLog.add(callEntry({ id: 2, endpoint: "listeSessions" }));
    await refresh(app);

    assert.deepEqual(rowIds(app), [1, 2]);
    assert.equal(cells(rowFor(app, 2))[1], "listeSessions");
    app.close();
  });

  test("asks again for a running call and shows how it ended", async () => {
    const app = await onCalls([
      callEntry({ id: 1 }),
      callEntry({ id: 2, status: null, durationMs: null, bytes: null }),
      callEntry({ id: 3 }),
    ]);

    app.server.callLog.update(2, { status: 504, durationMs: 30000, bytes: 50 });
    await refresh(app);

    assert.equal(reads(app).at(-1), "after=1");
    assert.deepEqual(cells(rowFor(app, 2)).slice(3, 6), ["504", "30 s", "50 o"]);
    assert.deepEqual(rowIds(app), [1, 2, 3]);
    app.close();
  });

  test("drops entries the server no longer keeps", async () => {
    const app = await onCalls([callEntry({ id: 1 }), callEntry({ id: 2 })]);

    app.server.callLog.entries = [callEntry({ id: 2 }), callEntry({ id: 3 })];
    await refresh(app);

    assert.deepEqual(rowIds(app), [2, 3]);
    app.close();
  });

  test("notices when the log was cleared somewhere else", async () => {
    const app = await onCalls([callEntry({ id: 1 })]);

    app.server.callLog.entries = [];
    await refresh(app);

    assert.deepEqual(rowIds(app), []);
    assert.equal(app.byId("callsEmpty").hidden, false);
    app.close();
  });

  test("does not ask while the page is hidden", async () => {
    const app = await onCalls();
    Object.defineProperty(app.document, "hidden", { value: true, configurable: true });

    await refresh(app);

    assert.equal(reads(app).length, 1);
    app.close();
  });

  test("does not ask while another tab is open", async () => {
    const app = await mount();

    await refresh(app);

    assert.deepEqual(reads(app), []);
    app.close();
  });

  test("reports a log it cannot read, then recovers", async () => {
    const app = await onCalls();
    app.server.callLog.fail("GET", "", { error: "boom" });

    await refresh(app);

    assert.equal(app.status(), "Impossible de lire le journal des appels.");
    assert.equal(app.query(".statusbar").dataset.state, "error");

    app.server.callLog.heal("GET", "");
    await refresh(app);

    assert.equal(app.status(), "Prêt.");
    app.close();
  });
});

describe("clearing the log", () => {
  test("is only offered when there is something to clear", async () => {
    const app = await onCalls([callEntry({ id: 1 })]);

    assert.equal(app.byId("callsClearBtn").disabled, false);
    app.close();
  });

  test("empties the list", async () => {
    const app = await onCalls([callEntry({ id: 1 }), markerEntry({ id: 2 })]);

    await app.click(app.byId("callsClearBtn"));

    assert.equal(app.server.callLog.called("", "DELETE").length, 1);
    assert.deepEqual(rowIds(app), []);
    assert.equal(app.byId("callsEmpty").hidden, false);
    assert.equal(app.byId("callsClearBtn").disabled, true);
    assert.equal(app.toast().text, "Journal effacé");
    app.close();
  });

  test("keeps the list when the server refuses", async () => {
    const app = await onCalls([callEntry({ id: 1 })]);
    app.server.callLog.fail("DELETE", "", { error: "Journal verrouillé" });

    await app.click(app.byId("callsClearBtn"));

    assert.equal(app.toast().text, "Journal verrouillé");
    assert.deepEqual(rowIds(app), [1]);
    app.close();
  });
});
