"use strict";

// Speech playback for the cabinet. Every page that wants a 🔊 button includes
// this file; nothing else has to know how audio is fetched.
//
// Two things it guarantees:
//   * only ONE clip plays at a time — clicking a second button stops the first,
//     rather than layering two voices over each other;
//   * a clip is fetched once per device, ever. The backend URL contains a hash
//     of exactly what was spoken and is served immutable, so the browser cache
//     does the real work here; the in-page map below only avoids re-asking the
//     API for the URL.
//
// Failure is deliberately quiet: audio is an enhancement, and a learner should
// never get an error dialog because the TTS box is busy. The button just stops
// spinning.

const AUDIO_STATE = {
  el: null, // the single shared <audio>
  button: null, // whichever button is currently playing
  urls: new Map(), // "text|lang|voice" -> resolved url
  // Incremented on every request. A click that resolves after a newer one
  // started must not hijack playback: without this, tapping two words in quick
  // succession on a slow connection can leave the first word playing under the
  // second word's highlighted button.
  token: 0,
};

function audioElement() {
  if (!AUDIO_STATE.el) {
    AUDIO_STATE.el = new Audio();
    AUDIO_STATE.el.preload = "none";
    AUDIO_STATE.el.addEventListener("ended", () => markButton(null));
    AUDIO_STATE.el.addEventListener("error", () => markButton(null));
  }
  return AUDIO_STATE.el;
}

// Only the active button carries the playing state, so the classes cannot drift
// out of sync when playback moves from one button to another.
function markButton(button, state) {
  const previous = AUDIO_STATE.button;
  if (previous && previous !== button) {
    previous.classList.remove("speak--loading", "speak--playing");
  }
  AUDIO_STATE.button = button;
  if (!button) return;
  button.classList.toggle("speak--loading", state === "loading");
  button.classList.toggle("speak--playing", state === "playing");
}

// Drop the remembered URLs. Called when the learner changes voice: a request
// that names no voice is resolved server-side from their profile, so the SAME
// key would otherwise keep returning the clip in the voice they just left.
function forgetAudioUrls() {
  AUDIO_STATE.urls.clear();
}

async function resolveAudioUrl(text, language, voice) {
  const key = `${text}|${language}|${voice || ""}`;
  if (AUDIO_STATE.urls.has(key)) return AUDIO_STATE.urls.get(key);

  const resp = await apiFetch("/audio", {
    method: "POST",
    body: JSON.stringify({ text, language, voice: voice || null }),
  });
  if (!resp.ok) throw new Error(`audio ${resp.status}`);
  const { url } = await resp.json();
  AUDIO_STATE.urls.set(key, url);
  return url;
}

// Speak `text`. `button` is optional and only drives the visual state.
async function speak(text, language, { voice = null, button = null } = {}) {
  const player = audioElement();

  // A second click on the button that is already playing means "stop".
  if (button && AUDIO_STATE.button === button && !player.paused) {
    player.pause();
    markButton(null);
    return;
  }

  player.pause();
  markButton(button, "loading");
  const token = ++AUDIO_STATE.token;
  try {
    const url = await resolveAudioUrl(text, language, voice);
    if (token !== AUDIO_STATE.token) return; // a newer click won the race
    player.src = `${CFG.API_BASE.replace(/\/api$/, "")}${url}`;
    await player.play();
    if (token !== AUDIO_STATE.token) return;
    markButton(button, "playing");
  } catch {
    if (token === AUDIO_STATE.token) markButton(null); // never interrupt the learner
  }
}

// One delegated listener for the whole page, so buttons rendered later (a new
// exercise, a lyrics line) work without anyone remembering to re-bind.
//
// Registered in the CAPTURE phase, which is what makes a 🔊 safe to nest inside
// something clickable — a vocabulary row that opens a modal, a match-pairs card
// that selects itself. A bubbling listener on `document` runs LAST, after those
// handlers have already fired, so stopping propagation there is too late.
// Capturing runs first, so the click never reaches the element underneath.
function initAudio() {
  document.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest("[data-speak]");
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      const text = button.dataset.speak;
      const language = button.dataset.speakLang;
      if (!text || !language) return;
      speak(text, language, { voice: button.dataset.speakVoice || null, button });
    },
    true,
  );
}

// Build a speaker button. Callers that render HTML strings use speakButtonHtml.
function speakButton(text, language, { voice = null, title = null } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "speak";
  button.dataset.speak = text;
  button.dataset.speakLang = language;
  if (voice) button.dataset.speakVoice = voice;
  button.setAttribute("aria-label", title || (window.t ? t("audio.listen") : "Listen"));
  button.textContent = "🔊";
  return button;
}

function speakButtonHtml(text, language, { voice = null } = {}) {
  const label = window.t ? t("audio.listen") : "Listen";
  const attrs = [
    `class="speak"`,
    `type="button"`,
    `data-speak="${escapeAttr(text)}"`,
    `data-speak-lang="${escapeAttr(language)}"`,
    voice ? `data-speak-voice="${escapeAttr(voice)}"` : "",
    `aria-label="${escapeAttr(label)}"`,
  ].filter(Boolean);
  return `<button ${attrs.join(" ")}>🔊</button>`;
}

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

document.addEventListener("DOMContentLoaded", initAudio);
