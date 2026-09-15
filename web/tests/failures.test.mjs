import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { ENDPOINTS, PRESETS, flush, mount } from "./harness.mjs";

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

const stagedChips = (app) =>
  app.queryAll(".chips--staged .chip").map((node) => node.textContent.trim());

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
    });

    assert.deepEqual(kinds(app), [
      "latency",
      "errorRate",
      "fail",
      "timeout",
      "malformed",
      "auth",
    ]);
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
