import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { loadPyodide } from "pyodide";

import { buildDemo } from "../build-demo.mjs";
import { startServer } from "../demo/server.js";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const PYODIDE_VERSION = createRequire(import.meta.url)("pyodide/package.json").version;

const VISITOR_REQUESTS = [
  "/editor/api/state?session=",
  "/admin/failures/options",
  "/admin/failures",
  "/editor/api/student/state",
  "/admin/calls?after=0",
  "/api/Etudiant/listeCours",
];

describe("the deployed demo server", { timeout: 300_000 }, () => {
  let out;
  let serve;

  before(async () => {
    out = await mkdtemp(join(tmpdir(), "demo-site-"));
    await buildDemo(out);
    const files = JSON.parse(await readFile(join(out, "demo", "server.json"), "utf8"));
    serve = await startServer(loadPyodide, files);
  });

  after(() => rm(out, { recursive: true, force: true }));

  test("runs on the Pyodide release the worker loads", async () => {
    const worker = await readFile(join(WEB, "demo", "worker.js"), "utf8");

    assert.ok(worker.includes(`/pyodide/v${PYODIDE_VERSION}/`), PYODIDE_VERSION);
  });

  for (const url of VISITOR_REQUESTS) {
    test(`answers ${url}`, async () => {
      const response = await serve({ method: "GET", url, headers: [], body: "" });

      assert.equal(response.status, 200, response.body);
      JSON.parse(response.body);
    });
  }
});
