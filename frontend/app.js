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
  $("p-name").textContent = user.full_name || "No name";
  $("p-email").textContent = user.email;
  $("avatar").textContent = (user.full_name || user.email || "?").trim().charAt(0).toUpperCase();
  $("p-role").textContent = user.role;

  const verified = $("p-verified");
  verified.textContent = user.is_email_verified ? "email verified" : "not verified";
  verified.className = `badge ${user.is_email_verified ? "badge--ok" : "badge--muted"}`;

  // The admin panel link only makes sense for privileged accounts; the API
  // still enforces the role, this just hides a door that would 403 anyway.
  $("admin-link").classList.toggle("hidden", user.role !== "ADMIN" && user.role !== "SUPER_ADMIN");

  $("f-full_name").value = user.full_name || "";
  $("f-native_language").value = user.native_language || "";
  $("f-target_language").value = user.target_language || "";
  $("p-created").textContent = "With us since " + new Date(user.created_at).toLocaleDateString();

  hide($("login-view"));
  hide($("lang-view"));
  show($("profile-view"));
  loadSubscription();
}

// Show the current plan and, for free accounts, an Upgrade button.
async function loadSubscription() {
  const box = $("sub-box");
  const resp = await apiFetch("/payments/subscription");
  if (!resp.ok) return hide(box);
  const sub = await resp.json();
  show(box);
  const upgrade = $("upgrade-btn");
  if (sub.is_active) {
    $("sub-status").textContent = "Premium — active";
    hide(upgrade);
  } else {
    $("sub-status").textContent = "Free";
    show(upgrade);
  }
}

// Open Stripe Checkout for the premium plan and send the browser there.
async function startCheckout() {
  const btn = $("upgrade-btn");
  btn.disabled = true;
  const resp = await apiFetch("/payments/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_code: "premium_monthly" }),
  });
  btn.disabled = false;
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    return toast(typeof err.detail === "string" ? err.detail : "Could not start checkout", "err");
  }
  const { checkout_url } = await resp.json();
  window.location.href = checkout_url;
}

function showLogin() {
  currentUser = null;
  hide($("profile-view"));
  hide($("lang-view"));
  show($("login-view"));
}

// A native language is mandatory: a brand-new account must pick one before it
// reaches the cabinet. An account that already has it (set here or elsewhere)
// skips this — which is why the extension never needs to ask again.
function showLangGate(user) {
  currentUser = user;
  hide($("login-view"));
  hide($("profile-view"));
  show($("lang-view"));
}

function routeAfterAuth(user) {
  if (!user.native_language) return showLangGate(user);
  renderProfile(user);
}

async function loadProfile() {
  if (!TOKENS.access) return showLogin();
  const resp = await apiFetch("/auth/me");
  if (resp.ok) {
    routeAfterAuth(await resp.json());
  } else {
    TOKENS.clear();
    showLogin();
  }
}

async function saveNativeLanguage(event) {
  event.preventDefault();
  const native_language = $("l-native_language").value;
  if (!native_language || !currentUser) return;
  const resp = await apiFetch(`/users/${currentUser.id}`, {
    method: "PATCH",
    body: JSON.stringify({ native_language }),
  });
  if (resp.ok) {
    renderProfile(await resp.json());
    toast("Done!");
  } else {
    toast("Could not save the language", "err");
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
      return toast(err.detail || "Could not sign in", "err");
    }
    TOKENS.set(await resp.json());
    await loadProfile();
    toast("Welcome to LangUp!");
  } catch {
    toast("Network error", "err");
  }
}

// ---------- email + password ----------
let authMode = "login"; // "login" | "register"

function toggleAuthMode() {
  authMode = authMode === "login" ? "register" : "login";
  const registering = authMode === "register";
  $("a-name-field").classList.toggle("hidden", !registering);
  $("a-password").autocomplete = registering ? "new-password" : "current-password";
  $("auth-submit").textContent = registering ? "Sign up" : "Sign in";
  $("auth-mode-toggle").textContent = registering ? "I already have an account" : "Create account";
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
      const fallback = authMode === "register" ? "Could not sign up" : "Invalid email or password";
      return toast(typeof err.detail === "string" ? err.detail : fallback, "err");
    }
    TOKENS.set(await resp.json());
    await loadProfile();
    toast("Welcome to LangUp!");
  } catch {
    toast("Network error", "err");
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
    toast("Saved");
  } else {
    toast("Could not save", "err");
  }
}

async function logout() {
  await logoutRequest();
  if (window.google?.accounts?.id) window.google.accounts.id.disableAutoSelect();
  showLogin();
  toast("Signed out");
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
  $("lang-form").addEventListener("submit", saveNativeLanguage);
  $("upgrade-btn").addEventListener("click", startCheckout);
  $("logout-btn").addEventListener("click", logout);
  initGoogle();
  loadProfile();
});
