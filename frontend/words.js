"use strict";

// Dictionary page. CFG/TOKENS/apiFetch come from api.js.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");
let dictTimer = null;
let currentUuid = null;

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast toast--${kind}`;
  show(el);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(el), 2400);
}

async function loadWords(query = "") {
  const list = $("dict-list");
  const path = "/vocabulary?limit=100" + (query ? "&query=" + encodeURIComponent(query) : "");
  const resp = await apiFetch(path);

  if (resp.status === 401) {
    location.href = "index.html"; // session gone — back to login
    return;
  }
  if (!resp.ok) {
    $("dict-count").textContent = "";
    return;
  }

  const page = await resp.json();
  $("dict-count").textContent = "(" + page.total + ")";
  $("dict-empty").classList.toggle("hidden", page.items.length > 0);

  list.innerHTML = "";
  for (const w of page.items) {
    const li = document.createElement("li");
    li.className = "dict__item dict__item--clickable";
    li.tabIndex = 0;
    li.addEventListener("click", () => openDetail(w.uuid));
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter") openDetail(w.uuid);
    });

    const lemma = document.createElement("span");
    lemma.className = "dict__lemma";
    lemma.textContent = w.lemma;

    const lang = document.createElement("span");
    lang.className = "dict__lang";
    lang.textContent = w.language;

    const mastery = document.createElement("span");
    mastery.className = "dict__mastery";
    mastery.textContent = masteryLabel(w.mastery_level);

    // The speaker stops the click from bubbling (see audio.js), so tapping it
    // plays the word instead of opening the detail modal.
    li.append(lemma, lang, mastery, speakButton(w.lemma, w.language));
    list.appendChild(li);
  }
}

// Bold the exact form the user captured inside its sentence, when we have it.
function highlight(sentence, surface) {
  const li = document.createElement("li");
  li.className = "wd__context";
  if (surface && sentence.includes(surface)) {
    const [before, ...rest] = sentence.split(surface);
    li.append(document.createTextNode(before));
    const mark = document.createElement("mark");
    mark.textContent = surface;
    li.append(mark, document.createTextNode(rest.join(surface)));
  } else {
    li.textContent = sentence;
  }
  return li;
}

async function openDetail(uuid) {
  const resp = await apiFetch(`/vocabulary/${uuid}`);
  if (resp.status === 401) return (location.href = "index.html");
  if (!resp.ok) return toast(t("words.open_fail"), "err");
  const w = await resp.json();
  currentUuid = uuid;

  $("wd-lemma").textContent = w.lemma;
  const say = $("wd-speak");
  say.dataset.speak = w.lemma;
  say.dataset.speakLang = w.language;
  $("wd-lang").textContent = w.language;
  $("wd-mastery").textContent = masteryLabel(w.mastery_level);
  const tr = $("wd-translation");
  tr.textContent = w.translation || t("words.no_translation");
  tr.classList.toggle("wd__translation--muted", !w.translation);

  const listEl = $("wd-context-list");
  listEl.innerHTML = "";
  $("wd-no-context").classList.toggle("hidden", w.contexts.length > 0);
  for (const ctx of w.contexts) listEl.appendChild(highlight(ctx.sentence, ctx.surface_form));

  show($("word-modal"));
}

function closeModal() {
  hide($("word-modal"));
  currentUuid = null;
}

async function removeWord() {
  if (!currentUuid) return;
  if (!confirm(t("words.remove_confirm"))) return;
  const btn = $("wd-remove");
  btn.disabled = true;
  const resp = await apiFetch(`/vocabulary/${currentUuid}`, { method: "DELETE" });
  btn.disabled = false;
  if (!resp.ok) return toast(t("words.remove_fail"), "err");
  closeModal();
  toast(t("words.removed"));
  loadWords($("dict-search").value.trim());
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!TOKENS.access) {
    location.href = "index.html"; // not logged in
    return;
  }
  await window.i18nReady;
  $("dict-search").addEventListener("input", (e) => {
    clearTimeout(dictTimer);
    const q = e.target.value.trim();
    dictTimer = setTimeout(() => loadWords(q), 250);
  });
  $("wd-remove").addEventListener("click", removeWord);
  for (const el of document.querySelectorAll("[data-close]")) el.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("word-modal").classList.contains("hidden")) closeModal();
  });
  loadWords();
});
