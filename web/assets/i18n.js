import fr from "./locales/fr.js";
import en from "./locales/en.js";

const CATALOGS = { fr, en };
const DEFAULT_LOCALE = "fr";
const STORAGE_KEY = "etsmock.lang";

export const availableLocales = () => Object.keys(CATALOGS);

function normalize(raw) {
  if (!raw) return null;
  const tag = String(raw).trim().replace("_", "-").split("-")[0].toLowerCase();
  return tag in CATALOGS ? tag : null;
}

function stored() {
  try {
    return normalize(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

function remember(code) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
  }
}

function fromUrl() {
  return normalize(new URLSearchParams(location.search).get("lang"));
}

function fromServer() {
  return normalize(document.body.dataset.locale);
}

function fromBrowser() {
  for (const tag of navigator.languages || [navigator.language]) {
    const code = normalize(tag);
    if (code) return code;
  }
  return null;
}

let locale =
  fromUrl() || stored() || fromServer() || fromBrowser() || DEFAULT_LOCALE;

export const getLocale = () => locale;

export function setLocale(code) {
  const next = normalize(code);
  if (!next || next === locale) return false;
  locale = next;
  remember(next);
  return true;
}

export const localeName = (code) => CATALOGS[code]?.name || code;

function lookup(catalog, key) {
  return key.split(".").reduce((node, part) => (node ? node[part] : undefined), catalog);
}

export function t(key, params) {
  let value = lookup(CATALOGS[locale], key);
  if (value === undefined) value = lookup(CATALOGS[DEFAULT_LOCALE], key);
  if (typeof value !== "string") return key;
  if (!params) return value;
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    name in params ? String(params[name]) : match
  );
}

export function months() {
  return lookup(CATALOGS[locale], "months") || lookup(CATALOGS[DEFAULT_LOCALE], "months");
}

const ATTRIBUTES = {
  "data-i18n-title": "title",
  "data-i18n-label": "aria-label",
  "data-i18n-placeholder": "placeholder",
};

export function applyTranslations(root = document) {
  document.documentElement.lang = locale;
  document.title = t("title");
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  Object.entries(ATTRIBUTES).forEach(([dataAttr, target]) => {
    root.querySelectorAll(`[${dataAttr}]`).forEach((node) => {
      node.setAttribute(target, t(node.getAttribute(dataAttr)));
    });
  });
}
