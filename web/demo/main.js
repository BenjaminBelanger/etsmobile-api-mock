import { createDemoFetch } from "./backend.js";

const REPO = "https://github.com/BenjaminBelanger/etsmobile-api-mock";

const STAGES = {
  python: "Chargement de Python…",
  packages: "Chargement de FastAPI…",
  server: "Démarrage du serveur mock…",
};

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
window.fetch = createDemoFetch(worker, window.fetch.bind(window), location.href);

const boot = document.createElement("div");
boot.className = "demo-boot";
boot.innerHTML = `
  <div class="demo-boot__card" role="status" aria-live="polite">
    <h1 class="demo-boot__title">Démo de l'éditeur d'horaire</h1>
    <p class="demo-boot__text">Le serveur mock démarre directement dans votre navigateur.
      Le premier chargement peut prendre quelques secondes.</p>
    <fluent-progress-bar class="demo-boot__progress"></fluent-progress-bar>
    <p class="demo-boot__stage">${STAGES.python}</p>
  </div>`;
document.body.append(boot);

const stageText = boot.querySelector(".demo-boot__stage");

const note = document.createElement("span");
note.className = "demo-note";
note.innerHTML = `Démo : le serveur tourne dans votre navigateur, les modifications
  disparaissent au rechargement. <a href="${REPO}" target="_blank" rel="noopener">GitHub</a>`;
document.querySelector(".statusbar").append(note);

function showFailure(message) {
  if (boot.dataset.state === "error") return;
  boot.dataset.state = "error";
  boot.querySelector(".demo-boot__progress").remove();
  stageText.textContent = `Le serveur n'a pas pu démarrer : ${message}`;
  const retry = document.createElement("fluent-button");
  retry.setAttribute("appearance", "primary");
  retry.textContent = "Réessayer";
  retry.addEventListener("click", () => location.reload());
  boot.querySelector(".demo-boot__card").append(retry);
}

worker.addEventListener("message", ({ data }) => {
  if (data.type === "stage") {
    stageText.textContent = STAGES[data.stage];
  } else if (data.type === "ready") {
    document.documentElement.dataset.demo = "ready";
    boot.remove();
  } else if (data.type === "failed") {
    showFailure(data.message);
  }
});

worker.addEventListener("error", (event) =>
  showFailure(event.message || "le script du serveur n'a pas pu être chargé."),
);
