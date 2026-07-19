"use strict";

// Practice page: serve one exercise from the pool, grade the answer, repeat.
// CFG/TOKENS/apiFetch come from api.js.
const $ = (id) => document.getElementById(id);

let currentExercise = null;
let chosen = {}; // blank index (string) -> chosen word
let shownAt = 0; // for response_time_ms
let activeType = null; // null = practise whatever comes next

const TYPE_LABELS = {
  FILL_IN_BLANKS: "Пропуски",
  MULTIPLE_CHOICE: "Значення",
  FLASHCARD: "Картки",
  MATCH_PAIRS: "Пари",
  TYPING: "Впиши",
};

function show(viewId) {
  for (const id of ["ex-view", "res-view", "empty-view", "loading"]) {
    $(id).classList.toggle("hidden", id !== viewId);
  }
}

// --- picking what to practise ----------------------------------------------

function renderTypes() {
  const list = $("types-list");
  list.innerHTML = "";
  const options = [[null, "Будь-яка"], ...Object.entries(TYPE_LABELS)];

  for (const [type, label] of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (activeType === type ? " chip--on" : "");
    btn.textContent = label;
    btn.addEventListener("click", () => selectType(type));
    list.appendChild(btn);
  }
  $("types-bar").classList.remove("hidden");
}

function selectType(type) {
  stopClock();
  activeType = type;
  renderTypes();
  loadNext();
}

async function loadNext() {
  stopClock();
  show("loading");
  const query = activeType ? "?exercise_type=" + activeType : "";
  const resp = await apiFetch("/exercises/next" + query);

  if (resp.status === 401) {
    location.href = "index.html"; // session gone — back to login
    return;
  }
  if (resp.status === 404) {
    $("empty-text").textContent = activeType
      ? `Вправ типу «${TYPE_LABELS[activeType]}» зараз немає. Вони зʼявляться, коли додаси нові слова — або вибери «Будь-яка».`
      : "Поки що немає готових вправ. Вони генеруються автоматично після того, як ти додаєш нові слова — зазвичай це займає до хвилини.";
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
  $("ex-meter").classList.add("hidden");

  if (ex.exercise_type === "MULTIPLE_CHOICE") {
    renderMultipleChoice(ex);
  } else if (ex.exercise_type === "FLASHCARD") {
    renderFlashcard(ex);
  } else if (ex.exercise_type === "MATCH_PAIRS") {
    renderMatchPairs(ex);
  } else if (ex.exercise_type === "TYPING") {
    renderTyping(ex);
  } else {
    renderFillInBlanks(ex);
  }
}

function promptText(ex) {
  const uk = {
    FILL_IN_BLANKS: "Заповни пропуски правильним словом.",
    MULTIPLE_CHOICE: "Вибери правильне значення слова.",
    FLASHCARD: "Чи пам'ятаєш ти це слово?",
    MATCH_PAIRS: "З'єднай слово з його перекладом.",
    TYPING: "Впиши пропущене слово.",
  };
  return uk[ex.exercise_type] || ex.prompt || "";
}

function renderTyping(ex) {
  // The learner's own sentence with one gap they type into. The translation is
  // an on-demand hint, hidden so it stays a recall exercise, not a copy.
  const textEl = $("ex-text");
  const parts = ex.payload.text.split(/___(\d+)___/g); // [text, "1", text, ...]
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      textEl.appendChild(document.createTextNode(part));
      return;
    }
    const input = document.createElement("input");
    input.type = "text";
    input.className = "ex__input";
    input.autocapitalize = "none";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("aria-label", "пропущене слово");
    input.addEventListener("input", () => {
      chosen = { 1: input.value.trim() };
      $("ex-submit").disabled = !input.value.trim();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !$("ex-submit").disabled) submit();
    });
    textEl.appendChild(input);
  });
  setTimeout(() => textEl.querySelector("input")?.focus(), 0);

  if (ex.payload.hint) {
    const hint = document.createElement("button");
    hint.type = "button";
    hint.className = "ex__hint";
    hint.textContent = "Показати підказку";
    hint.addEventListener("click", () => {
      hint.textContent = "Підказка: " + ex.payload.hint;
      hint.disabled = true;
    });
    $("ex-blanks").appendChild(hint);
  }
}

// --- match pairs -----------------------------------------------------------
//
// A round holds more pairs than fit on screen. Solving one pair removes it but
// does NOT bring in a replacement: new pairs arrive only after the second
// solve, so the board never shrinks to a single obvious choice and the learner
// has to recall rather than deduce.

const PAIRS_PER_REFILL = 2; // solves needed before new pairs are dealt

let mp = null; // match-pairs round state

function renderMatchPairs(ex) {
  const all = new Map(ex.payload.pairs.map((p) => [String(p.id), p]));
  const ids = [...all.keys()];
  const visible = ex.payload.visible || 4;

  mp = {
    all,
    queue: ids.slice(visible), // not dealt yet
    left: shuffle(ids.slice(0, visible)), // word column
    right: shuffle(ids.slice(0, visible)), // translation column, shuffled apart
    picked: null, // {side, id}
    solved: {}, // pair id -> translation, submitted at the end
    mistakes: 0,
    maxMistakes: ex.payload.max_mistakes || 3,
    sinceRefill: 0,
  };

  $("ex-submit").classList.add("hidden"); // the round submits itself
  $("ex-meter").classList.remove("hidden");
  drawLives();
  drawBoard();
  startClock(ex.payload.time_limit || 60);
}

function startClock(seconds) {
  stopClock();
  mp.left_seconds = seconds;
  drawClock();
  mp.timer = setInterval(() => {
    mp.left_seconds -= 1;
    drawClock();
    if (mp.left_seconds <= 0) finishRound(true); // out of time fails the round
  }, 1000);
}

function stopClock() {
  if (mp && mp.timer) {
    clearInterval(mp.timer);
    mp.timer = null;
  }
}

function drawClock() {
  const left = Math.max(0, mp.left_seconds);
  const el = $("ex-timer");
  el.textContent = `${left} с`;
  el.classList.toggle("timer--low", left <= 10);
}

function drawLives() {
  const left = mp.maxMistakes - mp.mistakes;
  $("ex-lives").innerHTML = "";
  for (let i = 0; i < mp.maxMistakes; i++) {
    const dot = document.createElement("span");
    dot.className = "life" + (i < left ? "" : " life--lost");
    $("ex-lives").appendChild(dot);
  }
}

function drawBoard() {
  const board = $("ex-blanks");
  board.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "pairs";
  grid.append(buildColumn("left"), buildColumn("right"));
  board.appendChild(grid);

  const left = Object.keys(mp.solved).length;
  $("ex-status").textContent = `${left} з ${mp.all.size}`;
}

function buildColumn(side) {
  const column = document.createElement("div");
  column.className = "pairs__col";
  for (const id of mp[side]) {
    const pair = mp.all.get(id);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "pair";
    card.dataset.id = id;
    card.dataset.side = side;
    card.textContent = side === "left" ? pair.word : pair.translation;
    if (mp.picked && mp.picked.side === side && mp.picked.id === id) {
      card.classList.add("pair--picked");
    }
    card.addEventListener("click", () => pickCard(side, id));
    column.appendChild(card);
  }
  return column;
}

function pickCard(side, id) {
  if (!mp.picked) {
    mp.picked = { side, id };
    drawBoard();
    return;
  }
  if (mp.picked.side === side) {
    mp.picked = { side, id }; // same column — just move the selection
    drawBoard();
    return;
  }

  const chosen = mp.picked;
  mp.picked = null;
  if (chosen.id === id) {
    solvePair(id);
  } else {
    missPair(chosen, { side, id });
  }
}

function solvePair(id) {
  mp.solved[id] = mp.all.get(id).translation;
  mp.left = mp.left.filter((x) => x !== id);
  mp.right = mp.right.filter((x) => x !== id);
  mp.sinceRefill += 1;

  // Deal new pairs only every other solve — see the note above.
  if (mp.sinceRefill >= PAIRS_PER_REFILL) {
    mp.sinceRefill = 0;
    for (let i = 0; i < PAIRS_PER_REFILL && mp.queue.length; i++) {
      const next = mp.queue.shift();
      insertAtRandom(mp.left, next);
      insertAtRandom(mp.right, next);
    }
  }

  drawBoard();
  if (!mp.left.length) finishRound();
}

function missPair(a, b) {
  mp.mistakes += 1;
  drawLives();
  drawBoard();

  for (const { side, id } of [a, b]) {
    const card = document.querySelector(`.pair[data-side="${side}"][data-id="${id}"]`);
    if (card) card.classList.add("pair--wrong");
  }
  setTimeout(() => {
    for (const card of document.querySelectorAll(".pair--wrong")) card.classList.remove("pair--wrong");
    if (mp.mistakes >= mp.maxMistakes) finishRound();
  }, 550);
}

function insertAtRandom(list, id) {
  list.splice(Math.floor(Math.random() * (list.length + 1)), 0, id);
}

async function finishRound(timedOut = false) {
  stopClock();
  mp.timedOut = timedOut; // remembered so the result can say why the round ended
  chosen = mp.solved;
  await submit(mp.mistakes, timedOut);
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

// Bold every occurrence of `word` in `sentence`, case-insensitive, building the
// nodes by hand so the sentence text can never be treated as markup.
function boldWordInto(el, sentence, word) {
  const lower = sentence.toLowerCase();
  const needle = word.toLowerCase();
  let from = 0;
  let at = needle ? lower.indexOf(needle, from) : -1;

  while (at !== -1) {
    if (at > from) el.appendChild(document.createTextNode(sentence.slice(from, at)));
    const strong = document.createElement("strong");
    strong.textContent = sentence.slice(at, at + word.length);
    el.appendChild(strong);
    from = at + word.length;
    at = lower.indexOf(needle, from);
  }
  if (from < sentence.length) el.appendChild(document.createTextNode(sentence.slice(from)));
}

function renderFlashcard(ex) {
  // A card is the sentence the word was met in, the word in bold; the
  // translation is the answer, revealed on demand. Review only, no grading.
  const card = document.createElement("p");
  card.className = "ex__sentence";
  if (ex.payload.sentence) {
    boldWordInto(card, ex.payload.sentence, ex.payload.word);
  } else {
    const only = document.createElement("strong");
    only.textContent = ex.payload.word;
    card.appendChild(only);
  }
  $("ex-text").appendChild(card);

  $("ex-submit").classList.add("hidden"); // flashcard has its own buttons

  const area = $("ex-blanks");
  const reveal = document.createElement("button");
  reveal.type = "button";
  reveal.className = "btn btn--primary";
  reveal.textContent = "Показати переклад";
  reveal.addEventListener("click", () => {
    reveal.remove();

    const back = document.createElement("p");
    back.className = "ex__back";
    back.textContent = ex.payload.translation;
    area.appendChild(back);

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

async function submit(mistakes = null, timedOut = false) {
  $("ex-submit").disabled = true;
  const resp = await apiFetch("/exercises/" + currentExercise.uuid + "/attempt", {
    method: "POST",
    body: JSON.stringify({
      answers: chosen,
      response_time_ms: Date.now() - shownAt,
      mistakes,
      timed_out: timedOut,
    }),
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

  if (currentExercise.exercise_type === "MATCH_PAIRS") {
    const total = Object.keys(result.correct_answers).length;
    const solved = Object.keys(chosen).length;
    if (result.is_correct) {
      banner.textContent = `✓ Раунд пройдено — ${solved} з ${total} пар!`;
    } else if (mp.timedOut) {
      banner.textContent = `⏱ Час вийшов: ${solved} з ${total} пар.`;
    } else {
      banner.textContent = `✗ Раунд завершено: ${solved} з ${total} пар, помилок забагато.`;
    }
  } else if (currentExercise.exercise_type === "FLASHCARD") {
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

async function generateMore(statusId) {
  const status = $(statusId);
  const buttons = [$("empty-generate"), $("res-generate")];
  for (const b of buttons) b.disabled = true;

  // Generation is CPU-bound and can take half a minute; a silent wait reads as
  // a broken button, so count the seconds out loud.
  let elapsed = 0;
  status.textContent = "Генеруємо… 0 с";
  const ticker = setInterval(() => {
    elapsed += 1;
    status.textContent = `Генеруємо… ${elapsed} с`;
  }, 1000);

  const done = (text) => {
    clearInterval(ticker);
    for (const b of buttons) b.disabled = false;
    status.textContent = text;
  };

  // ask for the type the learner is looking at, not just "anything"
  const query = activeType ? "?exercise_type=" + activeType : "";
  const resp = await apiFetch("/exercises/refill" + query, { method: "POST" });
  if (!resp.ok) return done("Не вдалося згенерувати. Спробуй ще раз.");

  const body = await resp.json();
  // A worker took the job -> poll it. No worker -> it already ran inline.
  const created = body.status === "queued" ? await pollRefill(body.task_id) : body.created;

  if (created === null) return done("Генерація не завершилась. Спробуй ще раз.");
  if (!created) return done("Нових вправ не вийшло — збережи ще кілька слів.");
  done("");
  loadNext();
}

// Give up after this long rather than polling a job nobody is working on.
const REFILL_POLL_LIMIT_MS = 180000;

async function pollRefill(taskId) {
  const until = Date.now() + REFILL_POLL_LIMIT_MS;
  while (Date.now() < until) {
    await new Promise((r) => setTimeout(r, 2000));
    const resp = await apiFetch("/exercises/refill/" + taskId);
    if (!resp.ok) return null;
    const { status, created } = await resp.json();
    if (status === "done") return created ?? 0;
    if (status === "failed") return null;
  }
  return null;
}

document.addEventListener("DOMContentLoaded", () => {
  if (!TOKENS.access) {
    location.href = "index.html"; // not logged in
    return;
  }
  // Wrapped, not passed directly: a bare handler receives the click event as
  // the first argument, which would land in submit()'s `mistakes` param.
  $("ex-submit").addEventListener("click", () => submit());
  $("res-next").addEventListener("click", loadNext);
  $("empty-retry").addEventListener("click", loadNext);
  $("empty-generate").addEventListener("click", () => generateMore("empty-status"));
  $("res-generate").addEventListener("click", () => generateMore("res-mastery"));
  renderTypes();
  loadNext();
});
