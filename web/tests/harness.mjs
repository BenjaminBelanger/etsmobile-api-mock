import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");

const HTML = readFileSync(join(WEB, "index.html"), "utf8");
const APP = readFileSync(join(WEB, "assets", "app.js"), "utf8");
const FIXTURE = JSON.parse(
  readFileSync(join(HERE, "fixtures", "state.json"), "utf8"),
);

const VENDOR_IMPORTS = [
  'import "./vendor/fluent.js";',
  'import { icon } from "./vendor/fluent-icons.js";',
];

export const PX_PER_MIN = 1.08;
export const DAY_START_MIN = 8 * 60;
const GRID = { left: 0, top: 0, width: 600, height: 907 };

export const clone = (value) => JSON.parse(JSON.stringify(value));

const refused = new Set();

function ignoreRefusedRejections() {
  process.removeAllListeners("unhandledRejection");
  process.on("unhandledRejection", (reason) => {
    if (!refused.has(reason && reason.message)) throw reason;
  });
}

export const baseState = () => clone(FIXTURE);

export const toMin = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

export const topPx = (hhmm) => (toMin(hhmm) - DAY_START_MIN) * PX_PER_MIN;
export const heightPx = (start, end) => (toMin(end) - toMin(start)) * PX_PER_MIN;

function appSource() {
  let source = APP;
  for (const line of VENDOR_IMPORTS) {
    if (!source.includes(line)) {
      throw new Error(`app.js no longer starts with: ${line}`);
    }
    source = source.replace(line, "");
  }
  return source;
}

function defineElements(window) {
  const { HTMLElement } = window;

  class Plain extends HTMLElement {}

  class Dropdown extends HTMLElement {
    get control() {
      const host = this;
      if (!this._control) {
        this._control = {
          get value() {
            return host._typed ?? "";
          },
          set value(next) {
            host._typed = next;
          },
        };
      }
      return this._control;
    }

    get value() {
      const selected = this.querySelector("fluent-option[selected]");
      if (selected) return selected.getAttribute("value");
      return this._typed ?? "";
    }

    set value(next) {
      this._typed = next;
      this.querySelectorAll("fluent-option").forEach((option) => {
        if (option.getAttribute("value") === next) {
          option.setAttribute("selected", "");
        } else {
          option.removeAttribute("selected");
        }
      });
    }
  }

  class TextInput extends HTMLElement {
    get value() {
      return this._value ?? this.getAttribute("value") ?? "";
    }

    set value(next) {
      this._value = next;
    }
  }

  class Button extends HTMLElement {
    get disabled() {
      return this.hasAttribute("disabled");
    }

    set disabled(next) {
      if (next) this.setAttribute("disabled", "");
      else this.removeAttribute("disabled");
    }
  }

  class Dialog extends HTMLElement {
    show() {
      this.setAttribute("open", "");
    }

    hide() {
      this.removeAttribute("open");
    }

    get open() {
      return this.hasAttribute("open");
    }
  }

  class TabList extends HTMLElement {
    get activeid() {
      return this.getAttribute("activeid");
    }

    set activeid(next) {
      this.setAttribute("activeid", next);
    }
  }

  const registry = {
    "fluent-dropdown": Dropdown,
    "fluent-text-input": TextInput,
    "fluent-button": Button,
    "fluent-dialog": Dialog,
    "fluent-tablist": TabList,
  };
  for (const tag of [
    "fluent-listbox",
    "fluent-option",
    "fluent-tab",
    "fluent-field",
    "fluent-label",
    "fluent-divider",
    "fluent-tooltip",
    "fluent-text",
    "fluent-message-bar",
    "fluent-progress-bar",
    "fluent-badge",
    "fluent-counter-badge",
    "fluent-dialog-body",
  ]) {
    registry[tag] = class extends Plain {};
  }

  for (const [tag, constructor] of Object.entries(registry)) {
    window.customElements.define(tag, constructor);
  }
}

function createServer(initial) {
  const calls = [];
  const replies = new Map();
  let current = clone(initial);

  const server = {
    calls,
    get state() {
      return current;
    },
    set state(next) {
      current = clone(next);
    },
    reply(path, payload) {
      replies.set(path, { status: 200, payload });
    },
    fail(path, message, status = 400) {
      replies.set(path, { status, payload: { error: message } });
      refused.add(message);
      refused.add("Error");
    },
    called(path) {
      return calls.filter((call) => call.path === path);
    },
    lastCall(path) {
      const matching = server.called(path);
      return matching.length ? matching[matching.length - 1] : null;
    },
    fetch: async (url, options = {}) => {
      const href = String(url);
      const [rawPath, query] = href.replace("/editor/api", "").split("?");
      const call = {
        path: rawPath,
        query: query || "",
        method: options.method || "GET",
        body: options.body ? JSON.parse(options.body) : null,
      };
      calls.push(call);

      const canned = replies.get(rawPath);
      if (canned && canned.status !== 200) {
        return {
          ok: false,
          status: canned.status,
          statusText: "Error",
          json: async () => canned.payload,
        };
      }
      const payload = canned ? canned.payload : current;
      if (canned) current = clone(canned.payload);
      return { ok: true, status: 200, json: async () => clone(payload) };
    },
  };
  return server;
}

export async function flush(times = 3) {
  for (let i = 0; i < times; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

export function rect(node, box) {
  node.getBoundingClientRect = () => ({
    left: box.left,
    top: box.top,
    right: box.left + box.width,
    bottom: box.top + box.height,
    width: box.width,
    height: box.height,
    x: box.left,
    y: box.top,
    toJSON: () => box,
  });
}

export async function mount(options = {}) {
  ignoreRefusedRejections();
  const dom = new JSDOM(HTML, {
    url: "http://localhost:8080/editor",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const server = createServer(options.state || baseState());

  window.Element.prototype.setPointerCapture = function () {};
  window.Element.prototype.releasePointerCapture = function () {};
  window.PointerEvent = window.MouseEvent;
  window.fetch = server.fetch;
  window.icon = (name, size = 20) =>
    `<svg class="icon" data-name="${name}" width="${size}" height="${size}"></svg>`;

  defineElements(window);

  if (options.failLoad) server.fail("/state", options.failLoad);

  window.eval(appSource());
  await flush();

  const harness = {
    dom,
    window,
    document: window.document,
    server,
    byId: (id) => window.document.getElementById(id),
    query: (selector) => window.document.querySelector(selector),
    queryAll: (selector) => [...window.document.querySelectorAll(selector)],
    text: (selector) => window.document.querySelector(selector)?.textContent.trim(),
    blocks: () => [...window.document.querySelectorAll(".block")],
    blockFor: (blockId) =>
      window.document.querySelector(`.block[data-block-id="${blockId}"]`),
    status: () => window.document.getElementById("statusText").textContent,
    toast: () => ({
      hidden: window.document.getElementById("toastHost").hidden,
      text: window.document.getElementById("toastText").textContent,
      intent: window.document.getElementById("toast").getAttribute("intent"),
    }),
    async reload(state) {
      server.state = state;
      harness.byId("sessionSelect").value = state.session;
      harness.fire(harness.byId("sessionSelect"), "change");
      await flush();
    },
    fire(node, type, init = {}) {
      const { detail, ...options } = init;
      const event = new window.Event(type, {
        bubbles: true,
        cancelable: true,
        ...options,
      });
      if ("detail" in init) Object.defineProperty(event, "detail", { value: detail });
      node.dispatchEvent(event);
      return event;
    },
    mouse(node, type, init = {}) {
      const event = new window.MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        button: 0,
        ...init,
      });
      node.dispatchEvent(event);
      return event;
    },
    key(key, init = {}) {
      const event = new window.KeyboardEvent("keydown", {
        key,
        bubbles: true,
        cancelable: true,
        ...init,
      });
      window.document.dispatchEvent(event);
      return event;
    },
    type(node, value) {
      node.value = value;
      harness.fire(node, "input");
    },
    select(node, value) {
      node.value = value;
      harness.fire(node, "change");
    },
    setupGrid() {
      rect(harness.byId("grid"), GRID);
      return harness.byId("grid");
    },
    async drag(blockId, { dx = 0, dy = 0, handle = null, steps = true } = {}) {
      harness.setupGrid();
      const node = harness.blockFor(blockId);
      const target = handle ? node.querySelector(handle) : node;
      const start = { clientX: 10, clientY: 100 };
      harness.mouse(target, "pointerdown", start);
      if (steps) {
        harness.mouse(node, "pointermove", {
          clientX: start.clientX + dx,
          clientY: start.clientY + dy,
        });
      }
      harness.mouse(node, "pointerup", {
        clientX: start.clientX + dx,
        clientY: start.clientY + dy,
      });
      await flush();
      return node;
    },
    async click(node) {
      node.dispatchEvent(
        new window.MouseEvent("click", { bubbles: true, cancelable: true }),
      );
      await flush();
    },
    close() {
      window.close();
    },
  };

  return harness;
}
