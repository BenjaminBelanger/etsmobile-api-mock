import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const APP_DIR = "/app";

const stage = (name) => postMessage({ type: "stage", stage: name });

const lastLine = (err) => String(err.message || err).trim().split("\n").pop();

async function writeServerFiles(pyodide) {
  const res = await fetch(new URL("server.json", import.meta.url));
  if (!res.ok) throw new Error(`server.json: ${res.status} ${res.statusText}`);
  const files = await res.json();
  for (const [path, content] of Object.entries(files)) {
    const target = `${APP_DIR}/${path}`;
    pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    pyodide.FS.writeFile(target, content);
  }
  pyodide.FS.mkdirTree(`${APP_DIR}/web/assets`);
}

async function boot() {
  stage("python");
  const pyodide = await loadPyodide();
  stage("packages");
  await pyodide.loadPackage("fastapi");
  stage("server");
  await writeServerFiles(pyodide);
  pyodide.runPython(`import os, sys; os.chdir("${APP_DIR}"); sys.path.insert(0, "${APP_DIR}")`);
  const bridge = pyodide.pyimport("bridge");
  const app = bridge.load_app();
  return async ({ method, url, headers, body }) =>
    JSON.parse(await bridge.handle(app, method, url, JSON.stringify(headers), body));
}

const server = boot();

server.then(
  () => postMessage({ type: "ready" }),
  (err) => {
    console.error(err);
    postMessage({ type: "failed", message: lastLine(err) });
  },
);

addEventListener("message", async ({ data }) => {
  if (data.type !== "request") return;
  try {
    const serve = await server;
    postMessage({ type: "response", id: data.id, ...(await serve(data.request)) });
  } catch (err) {
    postMessage({ type: "response", id: data.id, error: lastLine(err) });
  }
});
