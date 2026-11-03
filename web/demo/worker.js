import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const APP_DIR = "/app";

const stage = (name) => postMessage({ type: "stage", stage: name });

const lastLine = (err) => String(err.message || err).trim().split("\n").pop();

async function downloadServerFiles() {
  const res = await fetch(new URL("server.json", import.meta.url));
  if (!res.ok) throw new Error(`server.json: ${res.status} ${res.statusText}`);
  return res.json();
}

function writeServerFiles(pyodide, files) {
  for (const [path, content] of Object.entries(files)) {
    const target = `${APP_DIR}/${path}`;
    pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    pyodide.FS.writeFile(target, content);
  }
  pyodide.FS.mkdirTree(`${APP_DIR}/web/assets`);
}

async function boot() {
  const download = downloadServerFiles();
  download.catch(() => {});
  stage("python");
  const pyodide = await loadPyodide();
  stage("packages");
  await pyodide.loadPackage("fastapi");
  stage("server");
  writeServerFiles(pyodide, await download);
  pyodide.runPython(`import os, sys; os.chdir("${APP_DIR}"); sys.path.insert(0, "${APP_DIR}")`);
  const bridge = pyodide.pyimport("bridge");
  const app = bridge.load_app();
  const handle = bridge.handle;
  return async ({ method, url, headers, body }) =>
    JSON.parse(await handle(app, method, url, JSON.stringify(headers), body));
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
