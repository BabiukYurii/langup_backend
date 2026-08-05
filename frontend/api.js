"use strict";

// Shared config + authenticated fetch, used by every page of the cabinet.
const CFG = window.LANGUP_CONFIG || { API_BASE: "/api", GOOGLE_CLIENT_ID: "" };

const TOKENS = {
  get access() {
    return localStorage.getItem("langup_access");
  },
  get refresh() {
    return localStorage.getItem("langup_refresh");
  },
  set({ access_token, refresh_token }) {
    localStorage.setItem("langup_access", access_token);
    localStorage.setItem("langup_refresh", refresh_token);
  },
  clear() {
    localStorage.removeItem("langup_access");
    localStorage.removeItem("langup_refresh");
  },
};

// Refresh tokens rotate: the server retires each one as it is used, and
// replaying a spent token is treated as theft and ends every session. So two
// requests must never refresh with the same token — everyone waits on one call.
let refreshInFlight = null;

async function tryRefresh() {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => (refreshInFlight = null));
  }
  return refreshInFlight;
}

async function doRefresh() {
  const token = TOKENS.refresh;
  if (!token) return false;
  try {
    const resp = await fetch(`${CFG.API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
    });
    if (!resp.ok) {
      // The session is gone for good; keeping dead tokens would only make
      // every later request retry against them.
      TOKENS.clear();
      return false;
    }
    TOKENS.set(await resp.json());
    return true;
  } catch {
    return false; // network blip — keep the tokens and let the caller retry
  }
}

async function logoutRequest() {
  // Tell the server too, otherwise the refresh token stays usable for a month.
  const token = TOKENS.refresh;
  TOKENS.clear();
  if (!token) return;
  try {
    await fetch(`${CFG.API_BASE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
    });
  } catch {
    /* already signed out locally; nothing useful to do */
  }
}

async function apiFetch(path, options = {}, retry = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (TOKENS.access) headers.Authorization = `Bearer ${TOKENS.access}`;

  const resp = await fetch(`${CFG.API_BASE}${path}`, { ...options, headers });
  if (resp.status === 401 && retry && TOKENS.refresh && (await tryRefresh())) {
    return apiFetch(path, options, false);
  }
  return resp;
}

// ---------- languages ----------
// One curated list, shared by every language <select> in the cabinet. These are
// the languages the AI model handles well (Russian intentionally excluded).
const LANGUAGES = [
  { code: "uk", name: "Ukrainian" },
  { code: "pl", name: "Polish" },
  { code: "en", name: "English" },
  { code: "de", name: "German" },
  { code: "es", name: "Spanish" },
  { code: "fr", name: "French" },
  { code: "it", name: "Italian" },
  { code: "pt", name: "Portuguese" },
];

function languageName(code) {
  const found = LANGUAGES.find((l) => l.code === code);
  return found ? found.name : code || "—";
}

// Make sure a stored language code is selectable even if it's not in our
// curated list (older accounts may hold legacy codes like "ua"). Without this,
// the <select> would fall back to the placeholder and a profile save would
// silently blank the user's language.
function ensureLanguageOption(select, code) {
  if (!select || !code) return;
  if ([...select.options].some((o) => o.value === code)) return;
  const opt = document.createElement("option");
  opt.value = code;
  opt.textContent = languageName(code);
  select.appendChild(opt);
}

// Populate a <select> from LANGUAGES, optionally with a disabled placeholder.
function fillLanguageSelect(select, placeholder) {
  if (!select) return;
  select.innerHTML = "";
  if (placeholder) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.disabled = true;
    opt.selected = true;
    opt.textContent = placeholder;
    select.appendChild(opt);
  }
  for (const lang of LANGUAGES) {
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = lang.name;
    select.appendChild(opt);
  }
}
