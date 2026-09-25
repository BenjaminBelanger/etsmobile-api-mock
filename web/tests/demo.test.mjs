import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { buildDemo, demoPage, serverFiles } from "../build-demo.mjs";
import { createDemoFetch, servedByDemo } from "../demo/backend.js";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const PAGE = "https://example.github.io/etsmobile-api-mock/";

function fakeWorker() {
  const listeners = { message: [], error: [] };
  return {
    sent: [],
    addEventListener: (type, listener) => listeners[type].push(listener),
    postMessage(message) {
      this.sent.push(message);
    },
    reply: (data) => listeners.message.forEach((listener) => listener({ data })),
    crash: () => listeners.error.forEach((listener) => listener(new Event("error"))),
  };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("the demo page", () => {
  test("loads its assets relative to the page", async () => {
    const page = demoPage(await readFile(join(WEB, "index.html"), "utf8"));

    assert.equal(page.includes("/editor/assets/"), false);
    assert.match(page, /href="assets\/styles\.css"/);
    assert.match(page, /src="assets\/app\.js"/);
  });

  test("starts the demo server before the editor", async () => {
    const page = demoPage(await readFile(join(WEB, "index.html"), "utf8"));

    assert.ok(page.indexOf('href="demo/demo.css"') > 0);
    assert.ok(page.indexOf('src="demo/main.js"') < page.indexOf('src="assets/app.js"'));
  });

  test("refuses a page that no longer loads the editor script", () => {
    assert.throws(() => demoPage("<html></html>"), /no longer loads the editor/);
  });
});

describe("the demo server bundle", () => {
  test("carries the app, every lib module, the seed data and the bridge", async () => {
    const files = await serverFiles();
    const modules = (await readdir(join(WEB, "..", "lib"))).filter((name) => name.endsWith(".py"));

    assert.ok(files["main.py"].includes("app = FastAPI("));
    assert.ok(files["bridge.py"].includes("async def handle("));
    for (const name of modules) assert.ok(`lib/${name}` in files, `lib/${name}`);
    assert.ok("seed/courses.json" in files);
    assert.ok("seed/failure_presets.json" in files);
  });

  test("builds a site with the page, the editor assets and the demo files", async () => {
    const out = await mkdtemp(join(tmpdir(), "demo-site-"));
    try {
      await buildDemo(out);

      for (const path of [
        "index.html",
        "assets/app.js",
        "assets/styles.css",
        "assets/vendor/fluent.js",
        "demo/main.js",
        "demo/backend.js",
        "demo/worker.js",
        "demo/demo.css",
        "demo/server.json",
      ]) {
        assert.ok(existsSync(join(out, path)), path);
      }
      const bundle = JSON.parse(await readFile(join(out, "demo", "server.json"), "utf8"));
      assert.deepEqual(bundle, await serverFiles());
    } finally {
      await rm(out, { recursive: true, force: true });
    }
  });
});

describe("the demo fetch", () => {
  test("serves the editor, admin and API routes of the page's origin", () => {
    for (const path of ["/editor/api/state?session=", "/admin/failures", "/api/Etudiant/listeCours"]) {
      assert.equal(servedByDemo(new URL(path, PAGE), PAGE), true, path);
    }
    assert.equal(servedByDemo(new URL("assets/app.js", PAGE), PAGE), false);
    assert.equal(servedByDemo(new URL("https://cdn.jsdelivr.net/api/x"), PAGE), false);
  });

  test("forwards a request to the worker and answers with its response", async () => {
    const worker = fakeWorker();
    const demoFetch = createDemoFetch(worker, () => assert.fail("used the network"), PAGE);

    const pending = demoFetch("/editor/api/block/move?x=1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"jour":"3"}',
    });
    await settle();
    const [sent] = worker.sent;
    worker.reply({
      type: "response",
      id: sent.id,
      status: 400,
      headers: [["content-type", "application/json"]],
      body: '{"error":"non"}',
    });
    const res = await pending;

    assert.equal(sent.type, "request");
    assert.deepEqual(sent.request, {
      method: "POST",
      url: "/editor/api/block/move?x=1",
      headers: [["content-type", "application/json"]],
      body: '{"jour":"3"}',
    });
    assert.equal(res.status, 400);
    assert.equal(res.headers.get("content-type"), "application/json");
    assert.deepEqual(await res.json(), { error: "non" });
  });

  test("sends an empty body for a GET", async () => {
    const worker = fakeWorker();
    const demoFetch = createDemoFetch(worker, () => assert.fail("used the network"), PAGE);

    demoFetch("/admin/failures");
    await settle();

    assert.equal(worker.sent[0].request.method, "GET");
    assert.equal(worker.sent[0].request.body, "");
  });

  test("leaves other requests to the network", async () => {
    const worker = fakeWorker();
    const calls = [];
    const demoFetch = createDemoFetch(worker, (...args) => (calls.push(args), "network"), PAGE);

    assert.equal(await demoFetch("assets/app.js"), "network");
    assert.deepEqual(calls, [["assets/app.js", undefined]]);
    assert.equal(worker.sent.length, 0);
  });

  test("fails like a network error when the server cannot answer", async () => {
    const worker = fakeWorker();
    const demoFetch = createDemoFetch(worker, () => assert.fail("used the network"), PAGE);

    const pending = demoFetch("/editor/api/state");
    await settle();
    worker.reply({ type: "response", id: worker.sent[0].id, error: "boom" });

    await assert.rejects(pending, { name: "TypeError", message: "boom" });
  });

  test("fails pending and later requests once the worker crashes", async () => {
    const worker = fakeWorker();
    const demoFetch = createDemoFetch(worker, () => assert.fail("used the network"), PAGE);

    const pending = demoFetch("/editor/api/state");
    await settle();
    worker.crash();

    await assert.rejects(pending, { name: "TypeError", message: "Serveur de démo indisponible." });
    await assert.rejects(demoFetch("/admin/failures"), { name: "TypeError" });
    assert.equal(worker.sent.length, 1);
  });
});
