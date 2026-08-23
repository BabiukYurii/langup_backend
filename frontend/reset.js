"use strict";

// Password-reset page, opened from the emailed link (?token=...). Posts the new
// password to /auth/reset-password; no session is needed — the token is the auth.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

const token = new URLSearchParams(location.search).get("token");

function setStatus(msg, kind = "err") {
  const el = $("status");
  el.textContent = msg || "";
  el.className = `notice notice--${kind}`;
  el.classList.toggle("hidden", !msg);
}

// Pull a readable message from a 400 (bad link) or 422 (weak password) body.
function detailMsg(body, fallback) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return body.detail[0].msg.replace(/^Value error, /, "");
  }
  return fallback;
}

async function onSubmit(event) {
  event.preventDefault();
  const password = $("password").value;
  if (password !== $("confirm").value) {
    return setStatus(t("reset.mismatch"));
  }
  setStatus("");
  $("submit").disabled = true;
  try {
    const resp = await fetch(`${CFG.API_BASE}/auth/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    });
    if (resp.ok) {
      hide($("form-view"));
      show($("done-view"));
      return;
    }
    const body = await resp.json().catch(() => null);
    if (resp.status === 400) {
      // Stale/invalid token — the form can't recover, point them to restart.
      hide($("form-view"));
      show($("invalid-view"));
      return;
    }
    setStatus(detailMsg(body, t("reset.update_fail")));
  } catch {
    setStatus(t("reset.network"));
  } finally {
    $("submit").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await window.i18nReady;
  if (!token) {
    hide($("form-view"));
    show($("invalid-view"));
    return;
  }
  $("reset-form").addEventListener("submit", onSubmit);
});
