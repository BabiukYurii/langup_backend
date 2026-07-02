"use strict";

// Dictionary page. CFG/TOKENS/apiFetch come from api.js.
const $ = (id) => document.getElementById(id);
let dictTimer = null;

async function loadWords(query = "") {
  const list = $("dict-list");
  const path = "/words?limit=100" + (query ? "&query=" + encodeURIComponent(query) : "");
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
    li.className = "dict__item";

    const lemma = document.createElement("span");
    lemma.className = "dict__lemma";
    lemma.textContent = w.lemma;

    const lang = document.createElement("span");
    lang.className = "dict__lang";
    lang.textContent = w.language;

    li.append(lemma, lang);
    list.appendChild(li);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!TOKENS.access) {
    location.href = "index.html"; // not logged in
    return;
  }
  $("dict-search").addEventListener("input", (e) => {
    clearTimeout(dictTimer);
    const q = e.target.value.trim();
    dictTimer = setTimeout(() => loadWords(q), 250);
  });
  loadWords();
});
