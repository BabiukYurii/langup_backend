"use strict";

// Lightweight cabinet i18n. Locale files live in i18n/<lang>.json as a flat
// { key: "text" } map. English is the fallback for any missing key, so a
// half-translated locale degrades gracefully instead of showing blanks.
//
// The active language defaults to the user's native language (stored at login /
// profile load as `langup_ui_lang`); a manual switch overrides it. Pages await
// `window.i18nReady` before rendering so t() is available synchronously after.

const I18N_LANG_KEY = "langup_ui_lang";
const I18N_SUPPORTED = ["uk", "pl", "en", "de", "es", "fr", "it", "pt"];
const I18N_FALLBACK = "en";

let I18N = {}; // active locale
let I18N_FB = {}; // fallback (en)

function currentUiLang() {
  const saved = localStorage.getItem(I18N_LANG_KEY);
  if (saved && I18N_SUPPORTED.includes(saved)) return saved;
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return I18N_SUPPORTED.includes(nav) ? nav : I18N_FALLBACK;
}

async function loadLocale(lang) {
  try {
    const resp = await fetch(`i18n/${lang}.json`, { cache: "no-cache" });
    return resp.ok ? await resp.json() : {};
  } catch {
    return {};
  }
}

// t(key, params?) -> translated text; {name} placeholders filled from params.
function t(key, params) {
  let s = (key in I18N ? I18N[key] : I18N_FB[key]) ?? key;
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

// Translate every element carrying a data-i18n* attribute under `root`.
function applyTranslations(root) {
  root = root || document;
  for (const el of root.querySelectorAll("[data-i18n]")) el.textContent = t(el.getAttribute("data-i18n"));
  for (const el of root.querySelectorAll("[data-i18n-placeholder]"))
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  for (const el of root.querySelectorAll("[data-i18n-title]"))
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  for (const el of root.querySelectorAll("[data-i18n-aria-label]"))
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria-label")));
  document.documentElement.lang = currentUiLang();
}

async function initI18n() {
  const lang = currentUiLang();
  I18N_FB = lang === I18N_FALLBACK ? {} : await loadLocale(I18N_FALLBACK);
  I18N = await loadLocale(lang);
  if (lang === I18N_FALLBACK) I18N_FB = I18N;
  applyTranslations();
}

// Switch the UI language, persist it, and re-render static text. Pages that also
// build strings in JS should re-run their own render after awaiting this.
async function setUiLang(lang) {
  if (!I18N_SUPPORTED.includes(lang)) return;
  localStorage.setItem(I18N_LANG_KEY, lang);
  I18N = lang === I18N_FALLBACK ? I18N_FB : await loadLocale(lang);
  if (lang === I18N_FALLBACK && !Object.keys(I18N_FB).length) I18N = I18N_FB = await loadLocale(I18N_FALLBACK);
  applyTranslations();
}

// Align the UI language with the account's native language, unless the user has
// explicitly chosen a UI language before (that manual choice wins).
function syncUiLangToNative(nativeLanguage) {
  if (localStorage.getItem(I18N_LANG_KEY)) return;
  if (nativeLanguage && I18N_SUPPORTED.includes(nativeLanguage)) {
    localStorage.setItem(I18N_LANG_KEY, nativeLanguage);
  }
}

// Localised mastery label from a level enum ("NEW" -> t("mastery.new")).
function masteryLabel(level) {
  return t("mastery." + String(level || "NEW").toLowerCase());
}

window.t = t;
window.masteryLabel = masteryLabel;
window.setUiLang = setUiLang;
window.applyTranslations = applyTranslations;
window.syncUiLangToNative = syncUiLangToNative;
window.currentUiLang = currentUiLang;
window.I18N_SUPPORTED = I18N_SUPPORTED;
// Pages await this before their DOMContentLoaded logic runs t().
window.i18nReady = initI18n();
