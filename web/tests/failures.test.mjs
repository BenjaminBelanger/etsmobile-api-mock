import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { ENDPOINTS, PRESETS, baseState, defaultFailures, flush, mount } from "./harness.mjs";

const BROKEN = {
  latencyMs: "500-2000",
  errorRate: 0.4,
  failEndpoints: ["lireHoraireDesSeances", "listeElementsEvaluation"],
  timeoutEndpoints: ["listeCours"],
  timeoutDurationS: 30,
  malformed: true,
  authRequired: true,
  tokenExpiredCalls: 3,
  tokensRejected: true,
  tokenLifetimeS: 30,
};

const ALL_KINDS = [
  "latency",
  "errorRate",
  "fail",
  "timeout",
  "malformed",
  "auth",
  "tokenExpired",
  "tokensRejected",
  "tokenLifetime",
];

const POLL_MS = 2000;

async function openFailures(app) {
  app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewFailures") });
  await flush();
}

async function onFailures(failures) {
  const app = await mount(failures ? { failures } : {});
  await openFailures(app);
  return app;
}

const kinds = (app) => app.queryAll(".injection").map((node) => node.dataset.kind);

const chips = (app, kind) =>
  app
    .queryAll(`.injection[data-kind="${kind}"] .injection__value .chip:not(.chip--add)`)
    .map((node) => node.textContent.trim());

const field = (app, kind, name) =>
  app.query(`.injection[data-kind="${kind}"] [data-field="${name}"]`);

const lastPatch = (app) => app.server.admin.lastCall("");

const patches = (app) =>
  app.server.admin.called("").filter((call) => call.method === "PATCH");

const undoBtn = (app) => app.byId("failuresUndoBtn");
const redoBtn = (app) => app.byId("failuresRedoBtn");

const iconOf = (node) => node.querySelector("svg").dataset.name;

async function undoKey(app) {
  const event = app.key("z", { ctrlKey: true });
  await flush();
  return event;
}

const stagedChips = (app) =>
  app.queryAll(".chips--staged .chip").map((node) => node.textContent.trim());

const unitOf = (app, kind) =>
  app.text(`.injection[data-kind="${kind}"] .injection__unit`);

function holdPolls(app) {
  const held = new Map();
  const { setTimeout: realSet, clearTimeout: realClear } = app.window;
  let next = 0;
  app.window.setTimeout = (fn, ms, ...args) => {
    if (ms !== POLL_MS) return realSet.call(app.window, fn, ms, ...args);
    next -= 1;
    held.set(next, fn);
    return next;
  };
  app.window.clearTimeout = (id) =>
    id < 0 ? held.delete(id) : realClear.call(app.window, id);
  return {
    get size() {
      return held.size;
    },
    async run() {
      const due = [...held.values()];
      held.clear();
      due.forEach((fn) => fn());
      await flush();
    },
  };
}

async function onFailuresPolled(failures) {
  const app = await mount({ failures });
  const polls = holdPolls(app);
  await openFailures(app);
  return { app, polls };
}

async function openDialog(app, kind) {
  await app.click(app.byId("failureAddBtn"));
  if (kind) {
    app.select(app.byId("fFailureKind"), kind);
    await flush();
  }
}

describe("the failures tab", () => {
  test("stays out of the way until it is picked", async () => {
    const app = await mount();

    assert.equal(app.byId("scheduleView").hidden, false);
    assert.equal(app.byId("failuresView").hidden, true);
    assert.equal(app.byId("failuresToolbar").hidden, true);
    app.close();
  });

  test("replaces the schedule and its toolbar once picked", async () => {
    const app = await onFailures();

    assert.equal(app.byId("scheduleView").hidden, true);
    assert.equal(app.byId("failuresView").hidden, false);
    assert.equal(app.byId("scheduleControls").hidden, true);
    assert.equal(app.byId("scheduleToolbar").hidden, true);
    assert.equal(app.byId("failuresToolbar").hidden, false);
    app.close();
  });

  test("gives the schedule back when the schedule tab is picked", async () => {
    const app = await onFailures();

    app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewSchedule") });
    await flush();

    assert.equal(app.byId("scheduleView").hidden, false);
    assert.equal(app.byId("failuresView").hidden, true);
    assert.equal(app.byId("scheduleToolbar").hidden, false);
    assert.equal(app.byId("failuresToolbar").hidden, true);
    assert.equal(app.blocks().length > 0, true);
    app.close();
  });

  test("leaves schedule shortcuts alone while it is open", async () => {
    const app = await mount();
    await app.click(app.blockFor("LOG430-02:0"));
    await openFailures(app);

    app.key("Delete");
    await flush();

    assert.equal(app.server.lastCall("/course/delete"), null);
    app.close();
  });

  test("flags on the tab that the API is broken", async () => {
    const app = await mount({ failures: { errorRate: 0.3 } });

    assert.equal(app.byId("failuresDot").hidden, false);
    app.close();
  });

  test("drops the flag once nothing is injected", async () => {
    const app = await onFailures({ errorRate: 0.3 });

    await app.click(app.byId("failuresResetBtn"));

    assert.equal(app.byId("failuresDot").hidden, true);
    app.close();
  });
});

describe("active injections", () => {
  test("say so when the API answers normally", async () => {
    const app = await onFailures();

    assert.equal(kinds(app).length, 0);
    assert.equal(app.byId("injectionEmpty").hidden, false);
    assert.equal(app.byId("failuresResetBtn").disabled, true);
    app.close();
  });

  test("list one row per injected parameter", async () => {
    const app = await onFailures({
      latencyMs: "100-800",
      errorRate: 0.3,
      failEndpoints: ["listeCours"],
      timeoutEndpoints: ["listeCoequipiers"],
      timeoutDurationS: 30,
      malformed: true,
      authRequired: true,
      tokenExpiredCalls: 2,
      tokensRejected: true,
      tokenLifetimeS: 30,
    });

    assert.deepEqual(kinds(app), ALL_KINDS);
    assert.equal(app.byId("injectionEmpty").hidden, true);
    assert.equal(app.byId("failuresResetBtn").disabled, false);
    app.close();
  });

  test("show the parameters the server reported", async () => {
    const app = await onFailures({
      latencyMs: "100-800",
      errorRate: 0.3,
      failEndpoints: ["*", "listeCours"],
      timeoutEndpoints: ["listeCoequipiers"],
      timeoutDurationS: 30,
    });

    assert.equal(field(app, "latency", "latencyMs").getAttribute("value"), "100-800");
    assert.equal(field(app, "errorRate", "errorRate").getAttribute("value"), "30");
    assert.deepEqual(chips(app, "fail"), ["tous les endpoints", "listeCours"]);
    assert.deepEqual(chips(app, "timeout"), ["listeCoequipiers"]);
    assert.equal(field(app, "timeout", "timeoutDurationS").getAttribute("value"), "30");
    app.close();
  });

  test("show how many calls an expired token still fails", async () => {
    const app = await onFailures({ tokenExpiredCalls: 3 });

    assert.equal(field(app, "tokenExpired", "tokenExpiredCalls").getAttribute("value"), "3");
    assert.equal(unitOf(app, "tokenExpired"), "appels restants");
    app.close();
  });

  test("speak of a single remaining call in the singular", async () => {
    const app = await onFailures({ tokenExpiredCalls: 1 });

    assert.equal(unitOf(app, "tokenExpired"), "appel restant");
    app.close();
  });

  test("show the token lifetime", async () => {
    const app = await onFailures({ tokenLifetimeS: 45 });

    assert.equal(field(app, "tokenLifetime", "tokenLifetimeS").getAttribute("value"), "45");
    assert.equal(unitOf(app, "tokenLifetime"), "s");
    app.close();
  });
});

describe("an expired token countdown", () => {
  test("follows the calls the app uses up", async () => {
    const { app, polls } = await onFailuresPolled({ tokenExpiredCalls: 3 });
    assert.equal(polls.size, 1);

    app.server.admin.config.tokenExpiredCalls = 1;
    await polls.run();

    assert.equal(field(app, "tokenExpired", "tokenExpiredCalls").getAttribute("value"), "1");
    assert.equal(polls.size, 1);
    app.close();
  });

  test("drops the row once the calls are used up", async () => {
    const { app, polls } = await onFailuresPolled({ tokenExpiredCalls: 1 });

    app.server.admin.config.tokenExpiredCalls = 0;
    await polls.run();

    assert.deepEqual(kinds(app), []);
    assert.equal(app.byId("failuresDot").hidden, true);
    assert.equal(polls.size, 0);
    app.close();
  });

  test("leaves the rows alone while nothing changes", async () => {
    const { app, polls } = await onFailuresPolled({ tokenExpiredCalls: 2, latencyMs: 500 });
    const input = field(app, "latency", "latencyMs");

    await polls.run();

    assert.equal(field(app, "latency", "latencyMs"), input);
    assert.equal(polls.size, 1);
    app.close();
  });

  test("keeps watching when the server cannot be read", async () => {
    const { app, polls } = await onFailuresPolled({ tokenExpiredCalls: 2 });
    app.server.admin.reply("", { error: "server unavailable" }, 500);

    await polls.run();

    assert.deepEqual(kinds(app), ["tokenExpired"]);
    assert.equal(polls.size, 1);
    app.close();
  });

  test("is not watched without a countdown", async () => {
    const { app, polls } = await onFailuresPolled({ tokenLifetimeS: 30 });

    assert.equal(polls.size, 0);
    app.close();
  });

  test("is not watched from the schedule tab", async () => {
    const { app, polls } = await onFailuresPolled({ tokenExpiredCalls: 3 });

    app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewSchedule") });
    await flush();

    assert.equal(polls.size, 0);
    app.close();
  });
});

describe("editing an injection", () => {
  test("saves a new latency", async () => {
    const app = await onFailures({ latencyMs: 500 });

    app.select(field(app, "latency", "latencyMs"), "200-900");
    await flush();

    assert.deepEqual(lastPatch(app), {
      path: "",
      method: "PATCH",
      body: { latencyMs: "200-900" },
    });
    assert.equal(field(app, "latency", "latencyMs").getAttribute("value"), "200-900");
    app.close();
  });

  test("saves a rate the user reads as a percentage", async () => {
    const app = await onFailures({ errorRate: 0.3 });

    app.select(field(app, "errorRate", "errorRate"), "50");
    await flush();

    assert.deepEqual(lastPatch(app).body, { errorRate: 0.5 });
    assert.equal(field(app, "errorRate", "errorRate").getAttribute("value"), "50");
    app.close();
  });

  test("saves a new timeout duration", async () => {
    const app = await onFailures({ timeoutEndpoints: ["listeCours"] });

    app.select(field(app, "timeout", "timeoutDurationS"), "5");
    await flush();

    assert.deepEqual(lastPatch(app).body, { timeoutDurationS: 5 });
    app.close();
  });

  test("refuses a rate outside the scale", async () => {
    const app = await onFailures({ errorRate: 0.3 });
    const before = app.server.admin.calls.length;

    app.select(field(app, "errorRate", "errorRate"), "180");
    await flush();

    assert.equal(app.server.admin.calls.length, before);
    assert.equal(app.toast().intent, "error");
    assert.equal(field(app, "errorRate", "errorRate").getAttribute("value"), "30");
    app.close();
  });

  test("saves a new count of calls for an expired token", async () => {
    const app = await onFailures({ tokenExpiredCalls: 3 });

    app.select(field(app, "tokenExpired", "tokenExpiredCalls"), "5");
    await flush();

    assert.deepEqual(lastPatch(app).body, { tokenExpiredCalls: 5 });
    app.close();
  });

  test("refuses a partial call", async () => {
    const app = await onFailures({ tokenExpiredCalls: 3 });
    const before = app.server.admin.calls.length;

    app.select(field(app, "tokenExpired", "tokenExpiredCalls"), "1.5");
    await flush();

    assert.equal(app.server.admin.calls.length, before);
    assert.equal(app.toast().text, "Un nombre d'appels est requis");
    assert.equal(field(app, "tokenExpired", "tokenExpiredCalls").getAttribute("value"), "3");
    app.close();
  });

  test("saves a new token lifetime", async () => {
    const app = await onFailures({ tokenLifetimeS: 30 });

    app.select(field(app, "tokenLifetime", "tokenLifetimeS"), "90");
    await flush();

    assert.deepEqual(lastPatch(app).body, { tokenLifetimeS: 90 });
    app.close();
  });

  test("puts the shown value back when the server refuses", async () => {
    const app = await onFailures({ latencyMs: 500 });
    app.server.admin.reply("", { error: "invalid latency range" }, 400);

    app.select(field(app, "latency", "latencyMs"), "900-100");
    await flush();

    assert.equal(app.status(), "Erreur.");
    assert.equal(app.toast().text, "invalid latency range");
    assert.equal(field(app, "latency", "latencyMs").getAttribute("value"), "500");
    app.close();
  });
});

describe("removing an injection", () => {
  test("clears only that parameter", async () => {
    const app = await onFailures({ latencyMs: 500, malformed: true });

    await app.click(app.query('[data-remove="latency"]'));

    assert.deepEqual(lastPatch(app).body, { latencyMs: 0 });
    assert.deepEqual(kinds(app), ["malformed"]);
    app.close();
  });

  test("keeps the other endpoints of the same row", async () => {
    const app = await onFailures({ failEndpoints: ["listeCoequipiers", "listeCours"] });

    await app.click(app.query('.injection[data-kind="fail"] .chip__x'));

    assert.deepEqual(lastPatch(app).body, { failEndpoints: ["listeCours"] });
    assert.deepEqual(chips(app, "fail"), ["listeCours"]);
    app.close();
  });

  test("clears everything at once", async () => {
    const app = await onFailures({ latencyMs: 500, authRequired: true });

    await app.click(app.byId("failuresResetBtn"));

    assert.equal(app.server.admin.lastCall("").method, "DELETE");
    assert.equal(kinds(app).length, 0);
    app.close();
  });

  test("tells a whole row apart from one of its endpoints", async () => {
    const app = await onFailures(BROKEN);

    for (const kind of ["fail", "timeout"]) {
      const row = app.query(`.injection[data-kind="${kind}"]`);
      assert.equal(iconOf(row.querySelector("[data-remove]")), "delete");
      row.querySelectorAll(".chip__x").forEach((node) => assert.equal(iconOf(node), "dismiss"));
    }
    app.close();
  });
});

describe("undo and redo on the failures tab", () => {
  test("start with nothing to undo or redo", async () => {
    const app = await onFailures(BROKEN);

    assert.equal(undoBtn(app).disabled, true);
    assert.equal(redoBtn(app).disabled, true);
    app.close();
  });

  test("undo and redo an edit from the toolbar", async () => {
    const app = await onFailures({ latencyMs: 500 });
    app.select(field(app, "latency", "latencyMs"), "200-900");
    await flush();

    assert.equal(undoBtn(app).disabled, false);
    await app.click(undoBtn(app));

    assert.deepEqual(lastPatch(app).body, { ...defaultFailures(), latencyMs: 500 });
    assert.equal(field(app, "latency", "latencyMs").getAttribute("value"), "500");
    assert.equal(app.toast().text, "Modification annulée");
    assert.equal(undoBtn(app).disabled, true);
    assert.equal(redoBtn(app).disabled, false);

    await app.click(redoBtn(app));

    assert.equal(field(app, "latency", "latencyMs").getAttribute("value"), "200-900");
    assert.equal(app.toast().text, "Modification rétablie");
    assert.equal(undoBtn(app).disabled, false);
    assert.equal(redoBtn(app).disabled, true);
    app.close();
  });

  test("step back through several changes and forward again", async () => {
    const app = await onFailures(BROKEN);
    await app.click(app.query('[data-remove="latency"]'));
    app.select(field(app, "errorRate", "errorRate"), "50");
    await flush();
    await app.click(app.byId("failuresResetBtn"));

    for (let i = 0; i < 3; i += 1) await undoKey(app);

    assert.deepEqual(app.server.admin.config, BROKEN);
    assert.equal(undoBtn(app).disabled, true);

    app.key("y", { ctrlKey: true });
    await flush();
    app.key("z", { ctrlKey: true, shiftKey: true });
    await flush();

    assert.deepEqual(app.server.admin.config, {
      ...BROKEN,
      latencyMs: 0,
      errorRate: 0.5,
    });

    app.key("y", { ctrlKey: true });
    await flush();

    assert.deepEqual(app.server.admin.config, defaultFailures());
    assert.equal(redoBtn(app).disabled, true);
    app.close();
  });

  test("forget what was undone once something else changes", async () => {
    const app = await onFailures(BROKEN);
    await app.click(app.query('[data-remove="latency"]'));
    await undoKey(app);

    assert.equal(redoBtn(app).disabled, false);

    app.select(field(app, "errorRate", "errorRate"), "50");
    await flush();

    assert.equal(redoBtn(app).disabled, true);
    app.close();
  });

  test("record nothing for a scenario that changed nothing", async () => {
    const app = await onFailures(PRESETS[0].config);

    await app.click(app.query(`[data-preset="${PRESETS[0].name}"]`));

    assert.equal(undoBtn(app).disabled, true);
    app.close();
  });

  test("do not undo past a change made outside the editor", async () => {
    const app = await onFailures(BROKEN);
    await app.click(app.query('[data-remove="latency"]'));
    app.server.admin.config.malformed = false;

    app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewSchedule") });
    await flush();
    await openFailures(app);
    await undoKey(app);

    assert.equal(undoBtn(app).disabled, true);
    assert.equal(patches(app).length, 1);
    app.close();
  });

  test("leave ctrl+z to the field being typed in", async () => {
    const app = await onFailures(BROKEN);
    await app.click(app.query('[data-remove="auth"]'));
    const input = field(app, "latency", "latencyMs");
    input.tabIndex = 0;
    input.focus();

    const event = await undoKey(app);

    assert.equal(event.defaultPrevented, false);
    assert.equal(patches(app).length, 1);
    app.close();
  });

  test("keep their history apart from the schedule", async () => {
    const state = baseState();
    state.canUndo = true;
    const app = await mount({ state, failures: BROKEN });
    await openFailures(app);
    await app.click(app.byId("failuresResetBtn"));

    app.fire(app.byId("viewToggle"), "change", { detail: app.byId("viewSchedule") });
    await flush();
    await undoKey(app);

    assert.equal(app.server.called("/undo").length, 1);
    assert.equal(patches(app).length, 0);

    await openFailures(app);
    await undoKey(app);

    assert.equal(app.server.called("/undo").length, 1);
    assert.deepEqual(app.server.admin.config, BROKEN);
    app.close();
  });

  test("can be retried when a step fails", async () => {
    const app = await onFailures(BROKEN);
    await app.click(app.byId("failuresResetBtn"));
    app.server.admin.reply("", { error: "server unavailable" }, 500);

    await app.click(undoBtn(app));

    assert.equal(app.toast().intent, "error");
    assert.equal(kinds(app).length, 0);
    assert.equal(undoBtn(app).disabled, false);

    app.server.admin.reply("", BROKEN);
    await undoKey(app);

    assert.equal(patches(app).length, 2);
    assert.deepEqual(kinds(app), ALL_KINDS);
    app.close();
  });
});

describe("undoing what a single click took away", () => {
  test("brings a removed row back with its endpoints", async () => {
    const app = await onFailures(BROKEN);

    await app.click(app.query('[data-remove="fail"]'));
    await app.click(undoBtn(app));

    assert.deepEqual(lastPatch(app), { path: "", method: "PATCH", body: BROKEN });
    assert.deepEqual(chips(app, "fail"), BROKEN.failEndpoints);
    assert.equal(app.toast().text, "Modification annulée");
    app.close();
  });

  test("puts every parameter back after a full reset", async () => {
    const app = await onFailures(BROKEN);

    await app.click(app.byId("failuresResetBtn"));
    await app.click(undoBtn(app));

    assert.deepEqual(app.server.admin.config, BROKEN);
    assert.deepEqual(kinds(app), ALL_KINDS);
    assert.equal(app.byId("failuresDot").hidden, false);
    app.close();
  });

  test("puts back the setup a scenario replaced", async () => {
    const app = await onFailures(BROKEN);

    await app.click(app.query('[data-preset="flaky"]'));
    await app.click(undoBtn(app));

    assert.deepEqual(app.server.admin.config, BROKEN);
    assert.deepEqual(app.queryAll(".preset.is-active"), []);
    app.close();
  });

  test("brings back a single endpoint", async () => {
    const app = await onFailures({ failEndpoints: ["listeCoequipiers", "listeCours"] });

    await app.click(app.query('.injection[data-kind="fail"] .chip__x'));
    await app.click(undoBtn(app));

    assert.deepEqual(chips(app, "fail"), ["listeCoequipiers", "listeCours"]);
    app.close();
  });
});

describe("registering a failure", () => {
  test("offers every endpoint the server exposes", async () => {
    const app = await onFailures();

    await openDialog(app, "fail");

    const options = app.queryAll("#fEndpoint fluent-option:not([freeform])");
    assert.deepEqual(
      options.map((option) => option.getAttribute("value")),
      ["*", ...ENDPOINTS],
    );
    app.close();
  });

  test("adds a latency to a healthy server", async () => {
    const app = await onFailures();

    await openDialog(app);
    app.select(app.byId("fLatency"), "250");
    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, { latencyMs: "250" });
    assert.deepEqual(kinds(app), ["latency"]);
    assert.equal(app.byId("failureDialog").open, false);
    assert.equal(app.toast().text, "Panne enregistrée");
    app.close();
  });

  test("stages several endpoints before saving them", async () => {
    const app = await onFailures({ failEndpoints: ["listeCours"] });

    await openDialog(app, "fail");
    app.select(app.query("#fEndpoint"), "helloWorld");
    await app.click(app.query("#fEndpointAdd"));
    app.select(app.query("#fEndpoint"), "listeCoequipiers");

    assert.deepEqual(stagedChips(app), ["helloWorld"]);

    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, {
      failEndpoints: ["listeCours", "helloWorld", "listeCoequipiers"],
    });
    app.close();
  });

  test("drops a staged endpoint again", async () => {
    const app = await onFailures();

    await openDialog(app, "fail");
    app.select(app.query("#fEndpoint"), "helloWorld");
    await app.click(app.query("#fEndpointAdd"));
    await app.click(app.query(".chips--staged .chip__x"));

    assert.deepEqual(stagedChips(app), []);
    app.close();
  });

  test("registers a timeout with its duration", async () => {
    const app = await onFailures();

    await openDialog(app, "timeout");
    app.select(app.query("#fEndpoint"), "listeCours");
    app.select(app.query("#fTimeoutDuration"), "12");
    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, {
      timeoutEndpoints: ["listeCours"],
      timeoutDurationS: 12,
    });
    app.close();
  });

  test("registers a switch that takes no parameter", async () => {
    const app = await onFailures();

    await openDialog(app, "auth");

    assert.equal(app.byId("failureParams").children.length, 0);

    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, { authRequired: true });
    assert.deepEqual(kinds(app), ["auth"]);
    app.close();
  });

  test("registers an expired token for a number of calls", async () => {
    const app = await onFailures();

    await openDialog(app, "tokenExpired");
    app.select(app.byId("fTokenExpiredCalls"), "3");
    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, { tokenExpiredCalls: 3 });
    assert.deepEqual(kinds(app), ["tokenExpired"]);
    app.close();
  });

  test("asks how many calls an expired token fails", async () => {
    const app = await onFailures();
    const before = app.server.admin.calls.length;

    await openDialog(app, "tokenExpired");
    app.select(app.byId("fTokenExpiredCalls"), "0");
    await app.click(app.byId("failureSubmit"));

    assert.equal(app.server.admin.calls.length, before);
    assert.equal(app.toast().text, "Un nombre d'appels est requis");
    app.close();
  });

  test("registers rejected tokens without a parameter", async () => {
    const app = await onFailures();

    await openDialog(app, "tokensRejected");

    assert.equal(app.byId("failureParams").children.length, 0);

    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, { tokensRejected: true });
    assert.deepEqual(kinds(app), ["tokensRejected"]);
    app.close();
  });

  test("registers a token lifetime", async () => {
    const app = await onFailures();

    await openDialog(app, "tokenLifetime");
    app.select(app.byId("fTokenLifetime"), "45");
    await app.click(app.byId("failureSubmit"));

    assert.deepEqual(lastPatch(app).body, { tokenLifetimeS: 45 });
    assert.deepEqual(kinds(app), ["tokenLifetime"]);
    app.close();
  });

  test("asks for a token lifetime longer than zero", async () => {
    const app = await onFailures();
    const before = app.server.admin.calls.length;

    await openDialog(app, "tokenLifetime");
    app.select(app.byId("fTokenLifetime"), "0");
    await app.click(app.byId("failureSubmit"));

    assert.equal(app.server.admin.calls.length, before);
    assert.equal(app.toast().text, "Une durée en secondes est requise");
    app.close();
  });

  test("asks for the missing parameter and keeps the dialog open", async () => {
    const app = await onFailures();
    const before = app.server.admin.calls.length;

    await openDialog(app);
    await app.click(app.byId("failureSubmit"));

    assert.equal(app.server.admin.calls.length, before);
    assert.equal(app.byId("failureDialog").open, true);
    assert.equal(app.toast().intent, "error");
    assert.equal(app.toast().text, "Une durée est requise");
    app.close();
  });

  test("opens on the right type from an endpoint row", async () => {
    const app = await onFailures({ timeoutEndpoints: ["listeCours"] });

    await app.click(app.query('.injection[data-kind="timeout"] .chip--add'));

    assert.equal(app.byId("failureDialog").open, true);
    assert.equal(app.byId("fFailureKind").value, "timeout");
    app.close();
  });
});

describe("scenarios", () => {
  test("summarise what each one breaks", async () => {
    const app = await onFailures();

    assert.deepEqual(
      app.queryAll(".preset__name").map((node) => node.textContent),
      PRESETS.map((preset) => preset.name),
    );
    assert.equal(app.text(".preset__summary"), "100-800 ms · 30 % d'erreurs");
    assert.equal(app.query(".preset").getAttribute("title"), PRESETS[0].description);
    app.close();
  });

  test("replace the active injections when applied", async () => {
    const app = await onFailures({ authRequired: true });

    await app.click(app.query('[data-preset="flaky"]'));

    assert.deepEqual(app.server.admin.lastCall("/preset"), {
      path: "/preset",
      method: "POST",
      body: { name: "flaky" },
    });
    assert.deepEqual(kinds(app), ["latency", "errorRate"]);
    assert.equal(app.toast().text, "Scénario flaky appliqué");
    app.close();
  });

  test("mark the one the server is running", async () => {
    const app = await onFailures();

    await app.click(app.query('[data-preset="outage"]'));

    const active = app.queryAll(".preset.is-active").map((node) => node.dataset.preset);
    assert.deepEqual(active, ["outage"]);

    await app.click(app.query('.injection[data-kind="fail"] .chip__x'));

    assert.deepEqual(app.queryAll(".preset.is-active"), []);
    app.close();
  });
});
