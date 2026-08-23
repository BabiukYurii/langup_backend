"use strict";

// Profile page. Shared CFG/TOKENS/apiFetch come from api.js; t()/setUiLang from i18n.js.
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
  const firstName = (user.full_name || "").trim().split(" ")[0];
  $("hero-name").textContent = firstName ? ", " + firstName : "";
  $("p-name").textContent = user.full_name || t("profile.no_name");
  $("p-email").textContent = user.email;
  $("avatar").textContent = (user.full_name || user.email || "?").trim().charAt(0).toUpperCase();
  $("p-role").textContent = user.role;

  const verified = $("p-verified");
  verified.textContent = user.is_email_verified ? t("account.verified") : t("account.not_verified");
  verified.className = `badge ${user.is_email_verified ? "badge--ok" : "badge--muted"}`;
  $("verify-banner").classList.toggle("hidden", user.is_email_verified);

  // The admin panel links only make sense for privileged accounts; the API
  // still enforces the role, this just hides doors that would 403 anyway.
  const isAdmin = user.role === "ADMIN" || user.role === "SUPER_ADMIN";
  $("admin-link").classList.toggle("hidden", !isAdmin);
  $("nav-admin").classList.toggle("hidden", !isAdmin);

  $("f-full_name").value = user.full_name || "";
  ensureLanguageOption($("f-native_language"), user.native_language);
  ensureLanguageOption($("f-target_language"), user.target_language);
  $("f-native_language").value = user.native_language || "";
  $("f-target_language").value = user.target_language || "";
  $("f-ui_language").value = currentUiLang();
  $("p-created").textContent = t("home.since", { date: new Date(user.created_at).toLocaleDateString() });

  hide($("login-view"));
  hide($("lang-view"));
  show($("profile-view"));
  loadSubscription();
  loadExercisePrefs();
}

// Match-pairs "fillers" preference lives on the exercises endpoint. PUT needs the
// whole schema (exercise_types is required), so we keep the current types from
// GET and resend them unchanged when only the flag changes.
let prefExerciseTypes = null;

async function loadExercisePrefs() {
  const resp = await apiFetch("/exercises/preferences");
  if (!resp.ok) return;
  const prefs = await resp.json();
  prefExerciseTypes = prefs.exercise_types;
  $("f-fillers").checked = prefs.match_pairs_fillers !== false;
}

async function saveExercisePrefs() {
  if (!prefExerciseTypes) return;
  const body = { exercise_types: prefExerciseTypes, match_pairs_fillers: $("f-fillers").checked };
  const resp = await apiFetch("/exercises/preferences", { method: "PUT", body: JSON.stringify(body) });
  if (!resp.ok) {
    $("f-fillers").checked = !$("f-fillers").checked; // revert on failure
    return toast(t("toast.save_fail"), "err");
  }
  toast(t("toast.saved"));
}

// Open/close the account dropdown; close it on any outside click.
function toggleAccountMenu(force) {
  const dd = $("account-dropdown");
  const open = force !== undefined ? force : dd.classList.contains("hidden");
  dd.classList.toggle("hidden", !open);
  $("account-btn").setAttribute("aria-expanded", String(open));
}

// Show the current plan and, for free accounts, an Upgrade button.
async function loadSubscription() {
  const box = $("plan-widget");
  const resp = await apiFetch("/payments/subscription");
  if (!resp.ok) return hide(box);
  const sub = await resp.json();
  show(box);
  const upgrade = $("upgrade-btn");
  const manage = $("manage-btn");
  const renew = $("sub-renew");
  const when = sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : null;

  if (sub.status === "TRIALING" && sub.is_active) {
    // Free trial: still premium, but nothing to manage in Stripe yet — nudge to subscribe.
    $("sub-status").textContent = t("plan.premium_trial");
    show(upgrade);
    hide(manage);
    renew.textContent = when ? t("plan.trial_ends", { date: when }) : "";
    renew.classList.toggle("hidden", !when);
  } else if (sub.is_active) {
    $("sub-status").textContent = t("plan.premium");
    hide(upgrade);
    show(manage);
    renew.textContent = when ? (sub.cancel_at_period_end ? t("plan.ends_on", { date: when }) : t("plan.renews_on", { date: when })) : "";
    renew.classList.toggle("hidden", !when);
  } else {
    $("sub-status").textContent = t("plan.free");
    show(upgrade);
    hide(manage);
    hide(renew);
  }
}

// Open Stripe's Customer Portal to manage or cancel the subscription.
async function openPortal() {
  const btn = $("manage-btn");
  btn.disabled = true;
  const resp = await apiFetch("/payments/portal", { method: "POST" });
  btn.disabled = false;
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    return toast(typeof err.detail === "string" ? err.detail : t("toast.portal_fail"), "err");
  }
  const { portal_url } = await resp.json();
  window.location.href = portal_url;
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
    return toast(typeof err.detail === "string" ? err.detail : t("toast.checkout_fail"), "err");
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

// Align the interface language with the account's native language on the first
// load, unless the user already chose a UI language explicitly.
async function alignUiLang(user) {
  if (localStorage.getItem("langup_ui_lang")) return;
  if (user.native_language && window.I18N_SUPPORTED.includes(user.native_language)) {
    await window.setUiLang(user.native_language);
  }
}

async function routeAfterAuth(user) {
  await alignUiLang(user);
  if (!user.native_language) return showLangGate(user);
  renderProfile(user);
}

async function loadProfile() {
  if (!TOKENS.access) return showLogin();
  const resp = await apiFetch("/auth/me");
  if (resp.ok) {
    await routeAfterAuth(await resp.json());
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
    const user = await resp.json();
    await alignUiLang(user);
    renderProfile(user);
    toast(t("common.done"));
  } else {
    toast(t("toast.lang_save_fail"), "err");
  }
}

// Pull a readable message out of an error body: a plain string detail, or the
// first field message from a 422 validation error (e.g. a weak password).
function detailMsg(err, fallback) {
  if (typeof err?.detail === "string") return err.detail;
  if (Array.isArray(err?.detail) && err.detail[0]?.msg) {
    return err.detail[0].msg.replace(/^Value error, /, "");
  }
  return fallback;
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
      return toast(err.detail || t("toast.signin_fail"), "err");
    }
    TOKENS.set(await resp.json());
    await loadProfile();
    toast(t("toast.welcome"));
  } catch {
    toast(t("toast.network_error"), "err");
  }
}

// ---------- email + password ----------
let authMode = "login"; // "login" | "register"

function toggleAuthMode() {
  authMode = authMode === "login" ? "register" : "login";
  const registering = authMode === "register";
  $("a-name-field").classList.toggle("hidden", !registering);
  $("a-password").autocomplete = registering ? "new-password" : "current-password";
  $("auth-submit").textContent = registering ? t("auth.signup") : t("auth.signin");
  $("auth-mode-toggle").textContent = registering ? t("auth.have_account") : t("auth.create_account");
  // "Forgot password?" only makes sense when signing in.
  $("forgot-link").classList.toggle("hidden", registering);
}

// Email a reset link for the address typed in the sign-in form. The response is
// deliberately the same whether or not the email exists (no enumeration).
async function onForgotPassword() {
  const email = $("a-email").value.trim();
  if (!email) return toast(t("toast.enter_email_first"), "err");
  try {
    await fetch(`${CFG.API_BASE}/auth/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
  } catch {
    /* even on a network error we don't want to hint at account existence */
  }
  toast(t("toast.reset_sent"));
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
      const fallback = authMode === "register" ? t("toast.signup_fail") : t("toast.invalid_credentials");
      return toast(detailMsg(err, fallback), "err");
    }
    TOKENS.set(await resp.json());
    await loadProfile();
    toast(t("toast.welcome"));
  } catch {
    toast(t("toast.network_error"), "err");
  }
}

async function saveProfile(event) {
  event.preventDefault();
  if (!currentUser) return;
  const payload = {
    full_name: $("f-full_name").value.trim() || null,
    native_language: $("f-native_language").value || null,
    target_language: $("f-target_language").value || null,
  };
  const resp = await apiFetch(`/users/${currentUser.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    renderProfile(await resp.json());
    toast(t("toast.saved"));
  } else {
    toast(t("toast.save_fail"), "err");
  }
}

// Re-send the confirmation email for an unverified account.
async function resendVerification() {
  const btn = $("resend-verify-btn");
  btn.disabled = true;
  const resp = await apiFetch("/auth/verify-email/resend", { method: "POST" });
  btn.disabled = false;
  if (!resp.ok) return toast(t("toast.verify_send_fail"), "err");
  const { status } = await resp.json();
  toast(status === "already_verified" ? t("toast.already_verified") : t("toast.verify_sent"));
}

async function logout() {
  await logoutRequest();
  if (window.google?.accounts?.id) window.google.accounts.id.disableAutoSelect();
  showLogin();
  toast(t("toast.signed_out"));
}

// Change the interface language on the fly and re-render JS-built strings.
async function onUiLanguageChange(event) {
  await window.setUiLang(event.target.value);
  if (currentUser) renderProfile(currentUser);
  else window.applyTranslations();
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
document.addEventListener("DOMContentLoaded", async () => {
  await window.i18nReady; // translations ready before any t() call

  // One shared language list for every dropdown in the cabinet.
  fillLanguageSelect($("l-native_language"), t("common.select_language"));
  fillLanguageSelect($("f-native_language"), t("common.not_set"));
  fillLanguageSelect($("f-target_language"), t("common.not_set"));
  fillLanguageSelect($("f-ui_language"));
  $("f-ui_language").value = currentUiLang();

  $("profile-form").addEventListener("submit", saveProfile);
  $("email-auth-form").addEventListener("submit", onEmailAuth);
  $("auth-mode-toggle").addEventListener("click", toggleAuthMode);
  $("forgot-link").addEventListener("click", onForgotPassword);
  $("lang-form").addEventListener("submit", saveNativeLanguage);
  $("upgrade-btn").addEventListener("click", startCheckout);
  $("manage-btn").addEventListener("click", openPortal);
  $("logout-btn").addEventListener("click", logout);
  $("resend-verify-btn").addEventListener("click", resendVerification);
  $("f-ui_language").addEventListener("change", onUiLanguageChange);
  $("f-fillers").addEventListener("change", saveExercisePrefs);

  // Account dropdown: toggle on the avatar, close on any outside click.
  $("account-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    toggleAccountMenu();
  });
  document.addEventListener("click", (e) => {
    if (!$("account").contains(e.target)) toggleAccountMenu(false);
  });

  // Landing back from the verification link.
  const verified = new URLSearchParams(location.search).get("verified");
  if (verified === "1") toast(t("toast.email_confirmed"));
  else if (verified === "0") toast(t("toast.link_invalid"), "err");
  initGoogle();
  loadProfile();
});
