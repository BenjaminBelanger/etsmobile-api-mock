import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

import { startServer } from "./server.js";

const stage = (name) => postMessage({ type: "stage", stage: name });

const lastLine = (err) => String(err.message || err).trim().split("\n").pop();

async function downloadServerFiles() {
  const res = await fetch(new URL("server.json", import.meta.url));
  if (!res.ok) throw new Error(`server.json: ${res.status} ${res.statusText}`);
  return res.json();
}

const download = downloadServerFiles();
download.catch(() => {});
const server = startServer(loadPyodide, download, stage);

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
