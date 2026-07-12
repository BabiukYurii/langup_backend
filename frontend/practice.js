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
  $("ex-prompt").textContent = promptText(ex);
  $("ex-text").innerHTML = "";
  $("ex-blanks").innerHTML = "";
  $("ex-status").textContent = "";
  $("ex-submit").disabled = true;
  $("ex-submit").classList.remove("hidden");

  if (ex.exercise_type === "MULTIPLE_CHOICE") {
    renderMultipleChoice(ex);
  } else if (ex.exercise_type === "FLASHCARD") {
    renderFlashcard(ex);
  } else {
    renderFillInBlanks(ex);
  }
}

function promptText(ex) {
  const uk = {
    FILL_IN_BLANKS: "Заповни пропуски правильним словом.",
    MULTIPLE_CHOICE: "Вибери правильне значення слова.",
    FLASHCARD: "Чи пам'ятаєш ти це слово?",
  };
  return uk[ex.exercise_type] || ex.prompt || "";
}

function renderFillInBlanks(ex) {
  // Text with ___N___ placeholders turned into visual blanks.
  const textEl = $("ex-text");
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
}

function renderMultipleChoice(ex) {
  const word = document.createElement("span");
  word.className = "ex__word";
  word.textContent = ex.payload.word;
  $("ex-text").appendChild(word);

  const row = document.createElement("div");
  row.className = "ex__options ex__options--column";
  for (const option of shuffle([...ex.payload.options])) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "opt";
    btn.textContent = option;
    btn.addEventListener("click", () => pick(1, option, btn, row));
    row.appendChild(btn);
  }
  $("ex-blanks").appendChild(row);
}

function renderFlashcard(ex) {
  const word = document.createElement("span");
  word.className = "ex__word";
  word.textContent = ex.payload.front;
  $("ex-text").appendChild(word);

  $("ex-submit").classList.add("hidden"); // flashcard has its own buttons

  const area = $("ex-blanks");
  const reveal = document.createElement("button");
  reveal.type = "button";
  reveal.className = "btn btn--primary";
  reveal.textContent = "Показати відповідь";
  reveal.addEventListener("click", () => {
    reveal.remove();

    const back = document.createElement("p");
    back.className = "ex__back";
    back.textContent = ex.payload.back;
    area.appendChild(back);
    if (ex.payload.example) {
      const example = document.createElement("p");
      example.className = "meta";
      example.textContent = ex.payload.example;
      area.appendChild(example);
    }

    const row = document.createElement("div");
    row.className = "ex__options";
    const knew = document.createElement("button");
    knew.type = "button";
    knew.className = "opt opt--know";
    knew.textContent = "Знав ✓";
    knew.addEventListener("click", () => {
      chosen = { 1: "know" };
      submit();
    });
    const forgot = document.createElement("button");
    forgot.type = "button";
    forgot.className = "opt opt--forgot";
    forgot.textContent = "Не знав ✗";
    forgot.addEventListener("click", () => {
      chosen = { 1: "dont_know" };
      submit();
    });
    row.append(knew, forgot);
    area.appendChild(row);
  });
  area.appendChild(reveal);
}

function pick(index, option, btn, row) {
  chosen[String(index)] = option;
  for (const other of row.querySelectorAll(".opt")) other.classList.remove("opt--selected");
  btn.classList.add("opt--selected");

  // reflect the choice inside the sentence
  const blank = document.querySelector('.ex__blank[data-index="' + index + '"]');
  if (blank) blank.textContent = option;

  const total =
    currentExercise.exercise_type === "FILL_IN_BLANKS" ? currentExercise.payload.blanks.length : 1;
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

  if (currentExercise.exercise_type === "FLASHCARD") {
    // self-graded: no "correct answer" to reveal
    banner.textContent = result.is_correct
      ? "✓ Чудово, слово засвоюється!"
      : "✗ Нічого страшного — повторимо його пізніше.";
  } else if (result.is_correct) {
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
