const APP_DIR = "/app";

function writeServerFiles(pyodide, files) {
  for (const [path, content] of Object.entries(files)) {
    const target = `${APP_DIR}/${path}`;
    pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    pyodide.FS.writeFile(target, content);
  }
  pyodide.FS.mkdirTree(`${APP_DIR}/web/assets`);
}

export async function startServer(loadPyodide, files, stage = () => {}) {
  stage("python");
  const pyodide = await loadPyodide();
  stage("packages");
  await pyodide.loadPackage("fastapi");
  stage("server");
  writeServerFiles(pyodide, await files);
  pyodide.runPython(`import os, sys; os.chdir("${APP_DIR}"); sys.path.insert(0, "${APP_DIR}")`);
  const bridge = pyodide.pyimport("bridge");
  const app = bridge.load_app();
  const handle = bridge.handle;
  return async ({ method, url, headers, body }) =>
    JSON.parse(await handle(app, method, url, JSON.stringify(headers), body));
}
