"use strict";

// Spaced-repetition review. Pulls the due queue from /review/next, shows one
// card at a time (word -> reveal translation -> self-grade), and posts the
// grade to /review/{uuid}, which reschedules via SM-2 on the server.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

let queue = [];
let index = 0;
let reviewed = 0;
let busy = false;

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast toast--${kind}`;
  show(el);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(el), 2400);
}

function showDone() {
  hide($("card-view"));
  hide($("loading"));
  $("done-text").textContent = reviewed
    ? t("review.done_count", { count: reviewed })
    : t("review.done_default");
  show($("done-view"));
}

// Render the card at `index` face-down (translation hidden).
function renderCard() {
  const item = queue[index];
  $("rc-lang").textContent = item.language;
  $("rc-word").textContent = item.lemma;
  const say = $("rc-speak");
  say.dataset.speak = item.lemma;
  say.dataset.speakLang = item.language || "";
  say.classList.toggle("hidden", !item.language);
  const tr = $("rc-translation");
  tr.textContent = item.translation || t("review.no_translation_cached");
  tr.classList.toggle("rc__translation--muted", !item.translation);
  hide(tr);
  hide($("grades"));
  show($("show-btn"));
  $("rc-progress").textContent = `${index + 1} / ${queue.length}`;
  hide($("loading"));
  hide($("done-view"));
  show($("card-view"));
}

function revealAnswer() {
  show($("rc-translation"));
  hide($("show-btn"));
  show($("grades"));
}

async function grade(quality) {
  if (busy) return;
  const item = queue[index];
  busy = true;
  const resp = await apiFetch(`/review/${item.uuid}`, {
    method: "POST",
    body: JSON.stringify({ quality }),
  });
  busy = false;
  if (resp.status === 401) return (location.href = "index.html");
  if (!resp.ok) return toast(t("review.save_fail"), "err");

  reviewed += 1;
  index += 1;
  if (index < queue.length) {
    renderCard();
  } else {
    // The batch is done; there may be more still due (queue was capped).
    loadQueue({ append: true });
  }
}

async function loadQueue({ append = false } = {}) {
  const resp = await apiFetch("/review/next?limit=20");
  if (resp.status === 401) return (location.href = "index.html");
  if (!resp.ok) {
    hide($("loading"));
    return toast(t("review.load_fail"), "err");
  }
  const items = await resp.json();
  if (!items.length) return showDone();
  queue = items;
  index = 0;
  renderCard();
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!TOKENS.access) {
    location.href = "index.html";
    return;
  }
  await window.i18nReady;
  $("show-btn").addEventListener("click", revealAnswer);
  for (const btn of document.querySelectorAll(".grade")) {
    btn.addEventListener("click", () => grade(Number(btn.dataset.q)));
  }
  // Space / Enter reveals; 1-4 grade once revealed — quick keyboard reviewing.
  document.addEventListener("keydown", (e) => {
    if ($("card-view").classList.contains("hidden")) return;
    const graded = !$("grades").classList.contains("hidden");
    if (!graded && (e.key === " " || e.key === "Enter")) {
      e.preventDefault();
      revealAnswer();
    } else if (graded && ["1", "2", "3", "4"].includes(e.key)) {
      grade([1, 3, 4, 5][Number(e.key) - 1]);
    }
  });
  loadQueue();
});
