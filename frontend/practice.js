"use strict";

// Practice page: serve one exercise from the pool, grade the answer, repeat.
// CFG/TOKENS/apiFetch come from api.js.
const $ = (id) => document.getElementById(id);

let currentExercise = null;
let chosen = {}; // blank index (string) -> chosen word
let shownAt = 0; // for response_time_ms

function show(viewId) {
  for (const id of ["ex-view", "res-view", "empty-view", "loading"]) {
    $(id).classList.toggle("hidden", id !== viewId);
  }
}

async function loadNext() {
  show("loading");
  const resp = await apiFetch("/exercises/next");

  if (resp.status === 401) {
    location.href = "index.html"; // session gone — back to login
    return;
  }
  if (resp.status === 404) {
    show("empty-view");
    return;
  }
  if (!resp.ok) {
    $("loading").textContent = "Не вдалося завантажити вправу. Спробуй оновити сторінку.";
    return;
  }

  currentExercise = await resp.json();
  chosen = {};
  shownAt = Date.now();
  renderExercise(currentExercise);
  show("ex-view");
}

function renderExercise(ex) {
  $("ex-prompt").textContent = ex.prompt || "Заповни пропуски правильним словом.";

  // Text with ___N___ placeholders turned into visual blanks.
  const textEl = $("ex-text");
  textEl.innerHTML = "";
  const parts = ex.payload.text.split(/___(\d+)___/g);
  // split() gives [text, "1", text, "2", ...] — odd positions are blank indexes.
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      textEl.appendChild(document.createTextNode(part));
    } else {
      const blank = document.createElement("span");
      blank.className = "ex__blank";
      blank.dataset.index = part;
      blank.textContent = "…";
      textEl.appendChild(blank);
    }
  });

  // One options row per blank (multiple blanks are possible).
  const blanksEl = $("ex-blanks");
  blanksEl.innerHTML = "";
  for (const blank of ex.payload.blanks) {
    const row = document.createElement("div");
    row.className = "ex__options";
    if (ex.payload.blanks.length > 1) {
      const label = document.createElement("span");
      label.className = "meta";
      label.textContent = "Пропуск " + blank.index + ":";
      row.appendChild(label);
    }
    for (const option of shuffle([...blank.options])) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "opt";
      btn.textContent = option;
      btn.addEventListener("click", () => pick(blank.index, option, btn, row));
      row.appendChild(btn);
    }
    blanksEl.appendChild(row);
  }

  $("ex-status").textContent = "";
  $("ex-submit").disabled = true;
}

function pick(index, option, btn, row) {
  chosen[String(index)] = option;
  for (const other of row.querySelectorAll(".opt")) other.classList.remove("opt--selected");
  btn.classList.add("opt--selected");

  // reflect the choice inside the sentence
  const blank = document.querySelector('.ex__blank[data-index="' + index + '"]');
  if (blank) blank.textContent = option;

  const total = currentExercise.payload.blanks.length;
  $("ex-submit").disabled = Object.keys(chosen).length < total;
}

async function submit() {
  $("ex-submit").disabled = true;
  const resp = await apiFetch("/exercises/" + currentExercise.uuid + "/attempt", {
    method: "POST",
    body: JSON.stringify({ answers: chosen, response_time_ms: Date.now() - shownAt }),
  });
  if (!resp.ok) {
    $("ex-status").textContent = "Не вдалося надіслати відповідь, спробуй ще раз.";
    $("ex-submit").disabled = false;
    return;
  }
  const result = await resp.json();
  renderResult(result);
  show("res-view");
}

function renderResult(result) {
  const banner = $("res-banner");
  banner.className = "ex__result " + (result.is_correct ? "ex__result--ok" : "ex__result--err");

  if (result.is_correct) {
    banner.textContent = "✓ Правильно!";
  } else {
    const correct = Object.entries(result.correct_answers)
      .map(([, word]) => word)
      .join(", ");
    banner.textContent = "✗ Неправильно. Правильна відповідь: " + correct;
  }

  $("res-mastery").textContent = result.mastery_level
    ? "Рівень засвоєння: " + result.mastery_level.toLowerCase()
    : "";
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

document.addEventListener("DOMContentLoaded", () => {
  if (!TOKENS.access) {
    location.href = "index.html"; // not logged in
    return;
  }
  $("ex-submit").addEventListener("click", submit);
  $("res-next").addEventListener("click", loadNext);
  $("empty-retry").addEventListener("click", loadNext);
  loadNext();
});
