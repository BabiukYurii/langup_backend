"use strict";

// Admin panel. CFG/TOKENS/apiFetch come from api.js. Guarded twice: the API
// enforces the role, this only decides what to render.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

let searchTimer = null;
let currentUserId = null;

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast toast--${kind}`;
  show(el);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(el), 2600);
}

// A 401 means the session is gone; a 403 means this account isn't an admin.
// Either way the panel is off-limits — send them back to the profile.
function bounceIfDenied(resp) {
  if (resp.status === 401 || resp.status === 403) {
    location.href = "index.html";
    return true;
  }
  return false;
}

// ---------- users list ----------
async function loadUsers(query = "") {
  const path = "/admin/users?limit=100" + (query ? "&query=" + encodeURIComponent(query) : "");
  const resp = await apiFetch(path);
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return;

  const page = await resp.json();
  $("users-count").textContent = "(" + page.total + ")";
  $("users-empty").classList.toggle("hidden", page.items.length > 0);

  const list = $("users-list");
  list.innerHTML = "";
  for (const u of page.items) {
    const li = document.createElement("li");
    li.className = "dict__item admin__row";
    li.tabIndex = 0;

    const email = document.createElement("span");
    email.className = "dict__lemma";
    email.textContent = u.full_name ? `${u.full_name} · ${u.email}` : u.email;

    const role = document.createElement("span");
    role.className = "dict__lang";
    role.textContent = u.role;

    const status = document.createElement("span");
    status.className = "dict__mastery";
    status.textContent = u.status.toLowerCase();

    li.append(email, role, status);
    li.addEventListener("click", () => openDetail(u.id));
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter") openDetail(u.id);
    });
    list.appendChild(li);
  }
}

// ---------- user detail ----------
async function openDetail(userId) {
  currentUserId = userId;
  const resp = await apiFetch(`/admin/users/${userId}`);
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast("Не вдалося завантажити користувача", "err");

  const user = await resp.json();
  $("d-email").textContent = user.full_name || user.email;
  $("d-id").textContent = `#${user.id} · ${user.email}`;
  $("d-role").value = user.role;
  $("d-status").value = user.status;

  hide($("users-view"));
  show($("detail-view"));
  selectTab("vocab");
}

async function saveUser() {
  const body = { role: $("d-role").value, status: $("d-status").value };
  const resp = await apiFetch(`/admin/users/${currentUserId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (bounceIfDenied(resp)) return;
  if (resp.ok) return toast("Збережено");
  const err = await resp.json().catch(() => ({}));
  toast(typeof err.detail === "string" ? err.detail : "Не вдалося зберегти", "err");
}

// ---------- tabs ----------
function selectTab(which) {
  const vocab = which === "vocab";
  $("tab-vocab").classList.toggle("chip--on", vocab);
  $("tab-exercises").classList.toggle("chip--on", !vocab);
  $("d-vocab").classList.toggle("hidden", !vocab);
  $("d-exercises").classList.toggle("hidden", vocab);
  vocab ? loadVocab() : loadExercises();
}

async function loadVocab() {
  const resp = await apiFetch(`/admin/users/${currentUserId}/vocabulary?limit=100`);
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return;
  const page = await resp.json();
  const list = $("d-vocab");
  list.innerHTML = "";
  $("d-empty").classList.toggle("hidden", page.items.length > 0);
  for (const w of page.items) {
    const li = document.createElement("li");
    li.className = "dict__item";
    const lemma = document.createElement("span");
    lemma.className = "dict__lemma";
    lemma.textContent = w.lemma;
    const lang = document.createElement("span");
    lang.className = "dict__lang";
    lang.textContent = w.language;
    const mastery = document.createElement("span");
    mastery.className = "dict__mastery";
    mastery.textContent = (w.mastery_level || "NEW").toLowerCase();
    li.append(lemma, lang, mastery);
    list.appendChild(li);
  }
}

async function loadExercises() {
  const resp = await apiFetch(`/admin/users/${currentUserId}/exercises?limit=100`);
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return;
  const page = await resp.json();
  const list = $("d-exercises");
  list.innerHTML = "";
  $("d-empty").classList.toggle("hidden", page.items.length > 0);
  for (const ex of page.items) {
    const li = document.createElement("li");
    li.className = "dict__item admin__ex";

    const type = document.createElement("span");
    type.className = "dict__lang";
    type.textContent = ex.exercise_type;

    const status = document.createElement("span");
    status.className = "dict__mastery";
    status.textContent = ex.status.toLowerCase();

    const answer = document.createElement("span");
    answer.className = "admin__ex-answer";
    answer.textContent = Object.values(ex.answer || {}).join(", ");

    li.append(type, status, answer);
    list.appendChild(li);
  }
}

// ---------- boot ----------
document.addEventListener("DOMContentLoaded", () => {
  if (!TOKENS.access) {
    location.href = "index.html";
    return;
  }
  $("users-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    searchTimer = setTimeout(() => loadUsers(q), 250);
  });
  $("back-to-users").addEventListener("click", () => {
    hide($("detail-view"));
    show($("users-view"));
  });
  $("d-save").addEventListener("click", saveUser);
  $("tab-vocab").addEventListener("click", () => selectTab("vocab"));
  $("tab-exercises").addEventListener("click", () => selectTab("exercises"));
  loadUsers();
});
