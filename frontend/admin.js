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
  if (!resp.ok) return toast(await errText(resp, "Could not create"), "err");
  toast("User created");
  $("new-user-form").reset();
  hide($("new-user-form"));
  loadUsers();
}

// ---------- user detail ----------
async function openDetail(userId) {
  currentUserId = userId;
  const resp = await apiFetch(`/admin/users/${userId}`);
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast("Could not load the user", "err");

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
  if (resp.ok) return toast("Saved");
  toast(await errText(resp, "Could not save"), "err");
}

async function deleteUser() {
  if (!confirm("Delete this user and all their data? This cannot be undone.")) return;
  const resp = await apiFetch(`/admin/users/${currentUserId}`, { method: "DELETE" });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("User deleted");
    hide($("detail-view"));
    show($("users-view"));
    return loadUsers();
  }
  toast(await errText(resp, "Could not delete"), "err");
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
      iconBtn("✎", "Edit the shared word", () => editWord(w.word_uuid, w.lemma)),
      iconBtn("✕", "Remove from the user's vocabulary", () => removeVocab(w.uuid, w.lemma)),
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
  if (!resp.ok) return toast(await errText(resp, "Could not add"), "err");
  $("aw-word").value = "";
  toast("Word added");
  loadVocab();
}

async function removeVocab(userWordUuid, lemma) {
  if (!confirm(`Remove "${lemma}" from this user's vocabulary?`)) return;
  const resp = await apiFetch(`/admin/users/${currentUserId}/vocabulary/${userWordUuid}`, {
    method: "DELETE",
  });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Removed");
    return loadVocab();
  }
  toast(await errText(resp, "Could not remove"), "err");
}

async function editWord(wordUuid, currentLemma) {
  const lemma = prompt("Shared word lemma (affects ALL users):", currentLemma);
  if (lemma === null) return;
  const translation = prompt("Translation (uk). Leave empty to keep it unchanged:", "");
  const body = {};
  if (lemma.trim() && lemma.trim() !== currentLemma) body.lemma = lemma.trim();
  if (translation && translation.trim()) body.translation = translation.trim();
  if (Object.keys(body).length === 0) return;
  const resp = await apiFetch(`/admin/words/${wordUuid}`, { method: "PATCH", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Could not change the word"), "err");
  toast("Shared word updated");
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
    actions.append(iconBtn("✕", "Delete exercise", () => deleteExercise(ex.uuid)));

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
  if (resp.ok) return toast("Status changed");
  toast(await errText(resp, "Could not change status"), "err");
}

async function deleteExercise(uuid) {
  if (!confirm("Delete this exercise?")) return;
  const resp = await apiFetch(`/admin/exercises/${uuid}`, { method: "DELETE" });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Exercise deleted");
    return loadExercises();
  }
  toast(await errText(resp, "Could not delete"), "err");
}

// ---------- shared dictionary (CRUD, split by language) ----------
const DICT_LIMIT = 20;
const dictState = { language: null, query: "", page: 1 };

function openDict() {
  hide($("users-view"));
  show($("dict-view"));
  dictState.page = 1;
  loadDictLangs();
  loadDictWords();
}

// The language chips ("split by language"), each with its word count.
async function loadDictLangs() {
  const resp = await apiFetch("/admin/words/languages");
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return;
  const langs = await resp.json();
  const total = langs.reduce((n, l) => n + l.count, 0);
  const bar = $("dict-langs");
  bar.innerHTML = "";

  const chip = (label, code) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip" + (dictState.language === code ? " chip--on" : "");
    b.textContent = label;
    b.addEventListener("click", () => {
      dictState.language = code;
      dictState.page = 1;
      loadDictLangs();
      loadDictWords();
    });
    return b;
  };

  bar.appendChild(chip(`All (${total})`, null));
  for (const l of langs) bar.appendChild(chip(`${languageName(l.language)} (${l.count})`, l.language));
}

async function loadDictWords() {
  const params = new URLSearchParams({ page: dictState.page, limit: DICT_LIMIT });
  if (dictState.language) params.set("language", dictState.language);
  if (dictState.query) params.set("query", dictState.query);
  const resp = await apiFetch("/admin/words?" + params.toString());
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return;

  const page = await resp.json();
  $("dict-count").textContent = "(" + page.total + ")";
  $("dict-empty").classList.toggle("hidden", page.items.length > 0);

  const list = $("dict-list");
  list.innerHTML = "";
  for (const w of page.items) {
    const li = document.createElement("li");
    li.className = "dict__item admin__ex";

    const lemma = document.createElement("span");
    lemma.className = "dict__lemma";
    lemma.textContent = w.lemma;
    const lang = document.createElement("span");
    lang.className = "dict__lang";
    lang.textContent = w.language;
    const tr = document.createElement("span");
    tr.className = "admin__ex-answer";
    tr.textContent = dictTranslation(w.definitions);

    const actions = document.createElement("span");
    actions.className = "admin__actions";
    actions.append(
      iconBtn("✎", "Edit the shared word", () => editDictWord(w)),
      iconBtn("✕", "Delete from the shared dictionary", () => deleteDictWord(w.uuid, w.lemma)),
    );

    li.append(lemma, lang, tr, actions);
    list.appendChild(li);
  }

  const pages = Math.max(1, Math.ceil(page.total / DICT_LIMIT));
  $("dict-page").textContent = `Page ${page.page} / ${pages}`;
  $("dict-prev").disabled = page.page <= 1;
  $("dict-next").disabled = page.page >= pages;
}

// Prefer the Ukrainian sense; otherwise show whatever translations exist.
function dictTranslation(definitions) {
  if (!Array.isArray(definitions) || definitions.length === 0) return "—";
  const uk = definitions.find((d) => d.lang === "uk");
  const sense = uk || definitions[0];
  return sense.translation || "—";
}

async function createDictWord(e) {
  e.preventDefault();
  const body = {
    lemma: $("dw-lemma").value.trim(),
    language: $("dw-lang").value,
    translation: $("dw-translation").value.trim() || null,
  };
  if (!body.lemma) return;
  const resp = await apiFetch("/admin/words", { method: "POST", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Could not create the word"), "err");
  toast("Word added");
  $("dw-form").reset();
  $("dw-lang").value = dictState.language || "en";
  hide($("dw-form"));
  loadDictLangs();
  loadDictWords();
}

async function editDictWord(word) {
  const lemma = prompt("Shared lemma (affects ALL users who have it):", word.lemma);
  if (lemma === null) return;
  const translation = prompt("Translation (uk). Leave empty to keep unchanged:", dictTranslation(word.definitions) === "—" ? "" : dictTranslation(word.definitions));
  const body = {};
  if (lemma.trim() && lemma.trim() !== word.lemma) body.lemma = lemma.trim();
  if (translation && translation.trim()) body.translation = translation.trim();
  if (Object.keys(body).length === 0) return;
  const resp = await apiFetch(`/admin/words/${word.uuid}`, { method: "PATCH", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) return toast(await errText(resp, "Could not update"), "err");
  toast("Shared word updated");
  loadDictWords();
}

async function deleteDictWord(uuid, lemma) {
  if (!confirm(`Delete "${lemma}" from the shared dictionary? It disappears from every user who has it.`)) return;
  const resp = await apiFetch(`/admin/words/${uuid}`, { method: "DELETE" });
  if (bounceIfDenied(resp)) return;
  if (resp.status === 204) {
    toast("Word deleted");
    loadDictLangs();
    return loadDictWords();
  }
  toast(await errText(resp, "Could not delete"), "err");
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

// ---------- dictionary import ----------
const IMPORT_TASK_KEY = "langup_import_task"; // survives a page reload so we can resume

async function importDictionary(e) {
  e.preventDefault();
  const body = {
    source_language: $("di-source").value,
    target_language: $("di-target").value,
    raw_text: $("di-text").value,
    normalize: $("di-normalize").checked,
  };
  $("di-submit").disabled = true;
  showBar(true);
  $("di-status").textContent = body.normalize ? "Sending… (LLM normalize is slower)" : "Sending…";

  const resp = await apiFetch("/admin/dictionary/import", { method: "POST", body: JSON.stringify(body) });
  if (bounceIfDenied(resp)) return;
  if (!resp.ok) {
    finishImport();
    return toast(await errText(resp, "Could not import"), "err");
  }
  const { queued, task_id } = await resp.json();
  if (!task_id) {
    // Ran in-process (no worker): already done by the time we're here.
    $("di-status").textContent = `Imported ${queued} entrie(s).`;
    return finishImport();
  }
  // Remember it so a reload can resume the progress instead of losing it.
  localStorage.setItem(IMPORT_TASK_KEY, task_id);
  trackImport(task_id);
}

// The bar is determinate (width = %) when we know the chunk count, else it slides.
function showBar(indeterminate, pct) {
  const bar = $("di-progress");
  show(bar);
  bar.classList.toggle("progress--indeterminate", !!indeterminate);
  bar.firstElementChild.style.width = indeterminate ? "" : `${pct || 0}%`;
}

// Poll the task until it finishes; keep the button locked + bar running meanwhile.
async function trackImport(taskId) {
  $("di-submit").disabled = true;
  const until = Date.now() + 60 * 60 * 1000;
  while (Date.now() < until) {
    const resp = await apiFetch(`/admin/dictionary/import/${taskId}`);
    if (resp.ok) {
      const { status, done, total, created, updated } = await resp.json();
      if (status === "done") {
        $("di-status").textContent = `Done — ${created ?? 0} added, ${updated ?? 0} updated.`;
        $("di-text").value = "";
        localStorage.removeItem(IMPORT_TASK_KEY);
        return finishImport();
      }
      if (status === "failed") {
        $("di-status").textContent = "Import failed — check the server logs.";
        localStorage.removeItem(IMPORT_TASK_KEY);
        return finishImport();
      }
      if (total) {
        const pct = Math.round((done / total) * 100);
        showBar(false, pct);
        $("di-status").textContent = `Importing… chunk ${done}/${total} (${pct}%)`;
      } else {
        showBar(true);
        $("di-status").textContent = "Importing… (starting)";
      }
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  $("di-status").textContent = "Still importing… reopen the panel later to check.";
  finishImport();
}

// Cancel: revoke a running import; if nothing is running, just close the form.
async function cancelImport() {
  const taskId = localStorage.getItem(IMPORT_TASK_KEY);
  if (!taskId) {
    hide($("dict-import-form"));
    return;
  }
  await apiFetch(`/admin/dictionary/import/${taskId}`, { method: "DELETE" });
  localStorage.removeItem(IMPORT_TASK_KEY);
  $("di-status").textContent = "Import cancelled.";
  finishImport();
}

function finishImport() {
  hide($("di-progress"));
  $("di-submit").disabled = false;
}

// On load, resume tracking an import that was still running before a reload.
function resumeImportIfAny() {
  const taskId = localStorage.getItem(IMPORT_TASK_KEY);
  if (!taskId) return;
  show($("dict-import-form"));
  showBar(true);
  $("di-status").textContent = "Resuming import progress…";
  trackImport(taskId);
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
  // Language pickers for the dictionary import (from the shared LANGUAGES list).
  fillLanguageSelect($("di-source"));
  fillLanguageSelect($("di-target"));
  $("di-source").value = "en";
  $("di-target").value = "uk";
  $("dict-import-btn").addEventListener("click", () => $("dict-import-form").classList.toggle("hidden"));
  // Shared dictionary view.
  fillLanguageSelect($("dw-lang"));
  $("dw-lang").value = "en";
  $("dict-words-btn").addEventListener("click", openDict);
  $("back-from-dict").addEventListener("click", () => {
    hide($("dict-view"));
    show($("users-view"));
  });
  $("dict-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    dictState.query = e.target.value.trim();
    dictState.page = 1;
    searchTimer = setTimeout(loadDictWords, 250);
  });
  $("dw-new-btn").addEventListener("click", () => {
    $("dw-lang").value = dictState.language || "en";
    $("dw-form").classList.toggle("hidden");
  });
  $("dw-cancel").addEventListener("click", () => hide($("dw-form")));
  $("dw-form").addEventListener("submit", createDictWord);
  $("dict-prev").addEventListener("click", () => {
    if (dictState.page > 1) {
      dictState.page--;
      loadDictWords();
    }
  });
  $("dict-next").addEventListener("click", () => {
    dictState.page++;
    loadDictWords();
  });
  $("di-cancel").addEventListener("click", cancelImport);
  $("dict-import-form").addEventListener("submit", importDictionary);
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
  resumeImportIfAny(); // pick up an import that was still running before a reload
});
