"use strict";

// Profile page. Shared CFG/TOKENS/apiFetch come from api.js.
let currentUser = null;

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

  // The admin panel link only makes sense for privileged accounts; the API
  // still enforces the role, this just hides a door that would 403 anyway.
  $("admin-link").classList.toggle("hidden", user.role !== "ADMIN" && user.role !== "SUPER_ADMIN");

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

// ---------- email + password ----------
let authMode = "login"; // "login" | "register"

function toggleAuthMode() {
  authMode = authMode === "login" ? "register" : "login";
  const registering = authMode === "register";
  $("a-name-field").classList.toggle("hidden", !registering);
  $("a-password").autocomplete = registering ? "new-password" : "current-password";
  $("auth-submit").textContent = registering ? "Зареєструватися" : "Увійти";
  $("auth-mode-toggle").textContent = registering ? "У мене вже є акаунт" : "Створити акаунт";
}

async function onEmailAuth(event) {
  event.preventDefault();
  const body = { email: $("a-email").value.trim(), password: $("a-password").value };
  if (authMode === "register") body.full_name = $("a-name").value.trim() || null;
  try {
    const resp = await fetch(`${CFG.API_BASE}/auth/${authMode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      const fallback = authMode === "register" ? "Не вдалося зареєструватися" : "Невірний email або пароль";
      return toast(typeof err.detail === "string" ? err.detail : fallback, "err");
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

async function logout() {
  await logoutRequest();
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
  $("email-auth-form").addEventListener("submit", onEmailAuth);
  $("auth-mode-toggle").addEventListener("click", toggleAuthMode);
  $("logout-btn").addEventListener("click", logout);
  initGoogle();
  loadProfile();
});
