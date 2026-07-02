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

async function tryRefresh() {
  try {
    const resp = await fetch(`${CFG.API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: TOKENS.refresh }),
    });
    if (!resp.ok) return false;
    TOKENS.set(await resp.json());
    return true;
  } catch {
    return false;
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
