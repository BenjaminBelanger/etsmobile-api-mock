import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const DEMO = join(HERE, "demo");

const APP_SCRIPT = '<script type="module" src="/editor/assets/app.js"></script>';
const DEMO_TAGS = [
  '<link rel="stylesheet" href="demo/demo.css" />',
  '<script type="module" src="demo/main.js"></script>',
];
const LOCAL_ONLY = new Set(["seed/schedule_overrides.json"]);
const PAGE_FILES = ["backend.js", "demo.css", "main.js", "worker.js"];

async function listFiles(dir, extension) {
  const names = await readdir(join(ROOT, dir));
  return names
    .filter((name) => name.endsWith(extension))
    .sort()
    .map((name) => `${dir}/${name}`)
    .filter((path) => !LOCAL_ONLY.has(path));
}

export async function serverFiles() {
  const paths = [
    "main.py",
    ...(await listFiles("lib", ".py")),
    ...(await listFiles("seed", ".json")),
  ];
  const files = {};
  for (const path of paths) files[path] = await readFile(join(ROOT, path), "utf8");
  files["bridge.py"] = await readFile(join(DEMO, "bridge.py"), "utf8");
  return files;
}

export function demoPage(html) {
  if (!html.includes(APP_SCRIPT)) {
    throw new Error(`index.html no longer loads the editor with: ${APP_SCRIPT}`);
  }
  return html
    .replace(APP_SCRIPT, [...DEMO_TAGS, APP_SCRIPT].join("\n    "))
    .replaceAll("/editor/assets/", "assets/");
}

export async function buildDemo(out) {
  await rm(out, { recursive: true, force: true });
  await mkdir(join(out, "demo"), { recursive: true });
  const html = await readFile(join(HERE, "index.html"), "utf8");
  await writeFile(join(out, "index.html"), demoPage(html));
  await cp(join(HERE, "assets"), join(out, "assets"), { recursive: true });
  for (const name of PAGE_FILES) await cp(join(DEMO, name), join(out, "demo", name));
  await writeFile(join(out, "demo", "server.json"), JSON.stringify(await serverFiles()));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = resolve(process.argv[2] ?? join(HERE, "dist"));
  await buildDemo(out);
  console.log(`built the demo site in ${out}`);
}
