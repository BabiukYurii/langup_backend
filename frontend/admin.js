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

// Surface the API's error detail, falling back to a generic message.
async function errText(resp, fallback) {
  const body = await resp.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
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

// ---------- create user ----------
async function createUser(e) {
  e.preventDefault();
  const body = {
    email: $("nu-email").value.trim(),
    password: $("nu-password").value,
    full_name: $("nu-name").value.trim() || null,
    role: $("nu-role").value,
  };
  const resp = await apiFetch("/admin/users", { method: "POST", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Не вдалося створити"), "err");
  toast("Користувача створено");
  $("new-user-form").reset();
  hide($("new-user-form"));
  loadUsers();
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
  $("d-name").value = user.full_name || "";
  $("d-role").value = user.role;
  $("d-status").value = user.status;

  hide($("users-view"));
  show($("detail-view"));
  selectTab("vocab");
}

async function saveUser() {
  const body = {
    full_name: $("d-name").value.trim() || null,
    role: $("d-role").value,
    status: $("d-status").value,
  };
  const resp = await apiFetch(`/admin/users/${currentUserId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (bounceIfDenied(resp)) return;
  if (resp.ok) return toast("Збережено");
  toast(await errText(resp, "Не вдалося зберегти"), "err");
}

async function deleteUser() {
  if (!confirm("Видалити цього користувача разом з усіма його даними? Дію не можна скасувати.")) return;
  const resp = await apiFetch(`/admin/users/${currentUserId}`, { method: "DELETE" });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Користувача видалено");
    hide($("detail-view"));
    show($("users-view"));
    return loadUsers();
  }
  toast(await errText(resp, "Не вдалося видалити"), "err");
}

// ---------- tabs ----------
function selectTab(which) {
  const vocab = which === "vocab";
  $("tab-vocab").classList.toggle("chip--on", vocab);
  $("tab-exercises").classList.toggle("chip--on", !vocab);
  $("d-vocab").classList.toggle("hidden", !vocab);
  $("d-exercises").classList.toggle("hidden", vocab);
  $("add-word-form").classList.toggle("hidden", !vocab);
  vocab ? loadVocab() : loadExercises();
}

// ---------- vocabulary ----------
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
    li.className = "dict__item admin__ex";

    const lemma = document.createElement("span");
    lemma.className = "dict__lemma";
    lemma.textContent = w.lemma;
    const lang = document.createElement("span");
    lang.className = "dict__lang";
    lang.textContent = w.language;
    const mastery = document.createElement("span");
    mastery.className = "dict__mastery";
    mastery.textContent = (w.mastery_level || "NEW").toLowerCase();

    const actions = document.createElement("span");
    actions.className = "admin__actions";
    // Edit acts on the SHARED word (affects everyone who has it).
    actions.append(
      iconBtn("✎", "Редагувати спільне слово", () => editWord(w.word_uuid, w.lemma)),
      iconBtn("✕", "Прибрати зі словника юзера", () => removeVocab(w.uuid, w.lemma)),
    );

    li.append(lemma, lang, mastery, actions);
    list.appendChild(li);
  }
}

async function addWord(e) {
  e.preventDefault();
  const body = { word: $("aw-word").value.trim(), language: $("aw-lang").value.trim() };
  const resp = await apiFetch(`/admin/users/${currentUserId}/vocabulary`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Не вдалося додати"), "err");
  $("aw-word").value = "";
  toast("Слово додано");
  loadVocab();
}

async function removeVocab(userWordUuid, lemma) {
  if (!confirm(`Прибрати «${lemma}» зі словника цього користувача?`)) return;
  const resp = await apiFetch(`/admin/users/${currentUserId}/vocabulary/${userWordUuid}`, {
    method: "DELETE",
  });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Прибрано");
    return loadVocab();
  }
  toast(await errText(resp, "Не вдалося прибрати"), "err");
}

async function editWord(wordUuid, currentLemma) {
  const lemma = prompt("Лема спільного слова (впливає на ВСІХ користувачів):", currentLemma);
  if (lemma === null) return;
  const translation = prompt("Переклад (uk). Лишіть порожнім, щоб не змінювати:", "");
  const body = {};
  if (lemma.trim() && lemma.trim() !== currentLemma) body.lemma = lemma.trim();
  if (translation && translation.trim()) body.translation = translation.trim();
  if (Object.keys(body).length === 0) return;
  const resp = await apiFetch(`/admin/words/${wordUuid}`, { method: "PATCH", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Не вдалося змінити слово"), "err");
  toast("Спільне слово оновлено");
  loadVocab();
}

// ---------- exercises ----------
const EX_STATUSES = ["READY", "SERVED", "COMPLETED"];

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

    const statusSel = document.createElement("select");
    statusSel.className = "admin__status-sel";
    for (const s of EX_STATUSES) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s.toLowerCase();
      if (s === ex.status) opt.selected = true;
      statusSel.appendChild(opt);
    }
    statusSel.addEventListener("change", () => changeExerciseStatus(ex.uuid, statusSel.value));

    const answer = document.createElement("span");
    answer.className = "admin__ex-answer";
    answer.textContent = Object.values(ex.answer || {}).join(", ");

    const actions = document.createElement("span");
    actions.className = "admin__actions";
    actions.append(iconBtn("✕", "Видалити вправу", () => deleteExercise(ex.uuid)));

    li.append(type, statusSel, answer, actions);
    list.appendChild(li);
  }
}

async function changeExerciseStatus(uuid, status) {
  const resp = await apiFetch(`/admin/exercises/${uuid}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  if (bounceIfDenied(resp)) return;
  if (resp.ok) return toast("Статус змінено");
  toast(await errText(resp, "Не вдалося змінити статус"), "err");
}

async function deleteExercise(uuid) {
  if (!confirm("Видалити цю вправу?")) return;
  const resp = await apiFetch(`/admin/exercises/${uuid}`, { method: "DELETE" });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Вправу видалено");
    return loadExercises();
  }
  toast(await errText(resp, "Не вдалося видалити"), "err");
}

// ---------- helpers ----------
function iconBtn(text, title, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "admin__icon-btn";
  b.textContent = text;
  b.title = title;
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return b;
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
  $("new-user-btn").addEventListener("click", () => $("new-user-form").classList.toggle("hidden"));
  $("nu-cancel").addEventListener("click", () => hide($("new-user-form")));
  $("new-user-form").addEventListener("submit", createUser);
  $("back-to-users").addEventListener("click", () => {
    hide($("detail-view"));
    show($("users-view"));
  });
  $("d-save").addEventListener("click", saveUser);
  $("d-delete").addEventListener("click", deleteUser);
  $("add-word-form").addEventListener("submit", addWord);
  $("tab-vocab").addEventListener("click", () => selectTab("vocab"));
  $("tab-exercises").addEventListener("click", () => selectTab("exercises"));
  loadUsers();
});
