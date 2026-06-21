"use strict";

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

let currentUser = null;

// ---------- DOM helpers ----------
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast toast--${kind}`;
  show(el);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(el), 2600);
}

// ---------- API ----------
async function apiFetch(path, options = {}, retry = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (TOKENS.access) headers.Authorization = `Bearer ${TOKENS.access}`;

  const resp = await fetch(`${CFG.API_BASE}${path}`, { ...options, headers });

  if (resp.status === 401 && retry && TOKENS.refresh) {
    const refreshed = await tryRefresh();
    if (refreshed) return apiFetch(path, options, false);
  }
  return resp;
}

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

// ---------- views ----------
function renderProfile(user) {
  currentUser = user;
  $("p-name").textContent = user.full_name || "Без імені";
  $("p-email").textContent = user.email;
  $("avatar").textContent = (user.full_name || user.email || "?").trim().charAt(0).toUpperCase();
  $("p-role").textContent = user.role;

  const verified = $("p-verified");
  verified.textContent = user.is_email_verified ? "email підтверджено" : "не підтверджено";
  verified.className = `badge ${user.is_email_verified ? "badge--ok" : "badge--muted"}`;

  $("f-full_name").value = user.full_name || "";
  $("f-native_language").value = user.native_language || "";
  $("f-target_language").value = user.target_language || "";
  $("p-created").textContent = "З нами з " + new Date(user.created_at).toLocaleDateString();

  hide($("login-view"));
  show($("profile-view"));
}

function showLogin() {
  currentUser = null;
  hide($("profile-view"));
  show($("login-view"));
}

async function loadProfile() {
  if (!TOKENS.access) return showLogin();
  const resp = await apiFetch("/auth/me");
  if (resp.ok) {
    renderProfile(await resp.json());
  } else {
    TOKENS.clear();
    showLogin();
  }
}

// ---------- actions ----------
async function onGoogleCredential(response) {
  try {
    const resp = await fetch(`${CFG.API_BASE}/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: response.credential }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return toast(err.detail || "Не вдалося увійти", "err");
    }
    TOKENS.set(await resp.json());
    await loadProfile();
    toast("Вітаємо у LangUp!");
  } catch {
    toast("Помилка мережі", "err");
  }
}

async function saveProfile(event) {
  event.preventDefault();
  if (!currentUser) return;
  const payload = {
    full_name: $("f-full_name").value.trim() || null,
    native_language: $("f-native_language").value.trim() || null,
    target_language: $("f-target_language").value.trim() || null,
  };
  const resp = await apiFetch(`/users/${currentUser.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    renderProfile(await resp.json());
    toast("Збережено");
  } else {
    toast("Не вдалося зберегти", "err");
  }
}

function logout() {
  TOKENS.clear();
  if (window.google?.accounts?.id) window.google.accounts.id.disableAutoSelect();
  showLogin();
  toast("Ви вийшли");
}

// ---------- Google Sign-In init ----------
function initGoogle() {
  if (!CFG.GOOGLE_CLIENT_ID) {
    show($("google-missing"));
    return;
  }
  if (!window.google?.accounts?.id) {
    // GIS script not ready yet — retry shortly.
    return setTimeout(initGoogle, 200);
  }
  window.google.accounts.id.initialize({
    client_id: CFG.GOOGLE_CLIENT_ID,
    callback: onGoogleCredential,
  });
  window.google.accounts.id.renderButton($("google-btn"), {
    theme: "filled_blue",
    size: "large",
    shape: "pill",
    text: "continue_with",
    width: 280,
  });
}

// ---------- boot ----------
document.addEventListener("DOMContentLoaded", () => {
  $("profile-form").addEventListener("submit", saveProfile);
  $("logout-btn").addEventListener("click", logout);
  initGoogle();
  loadProfile();
});
