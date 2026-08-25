"use strict";

// "Understand your playlist": paste a Spotify link -> tracks -> open a song ->
// lyrics with known words green, unknown red; tap a red word to translate it in
// context and add it to your dictionary. CFG/TOKENS/apiFetch/t from api/i18n.js.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

let currentSong = null; // {title, artist} of the open song

function toast(message, kind = "ok") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast toast--${kind}`;
  show(el);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(el), 2400);
}

async function errText(resp, fallback) {
  const body = await resp.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

// ---------- playlist ----------
async function loadPlaylist() {
  const url = $("pl-url").value.trim();
  if (!url) return;
  $("pl-load").disabled = true;
  $("pl-status").textContent = t("common.loading");
  hide($("lyrics-view"));
  hide($("pl-warning"));

  const resp = await apiFetch("/playlists/preview", { method: "POST", body: JSON.stringify({ url }) });
  $("pl-load").disabled = false;
  $("pl-status").textContent = "";
  if (!resp.ok) return toast(await errText(resp, t("playlist.fetch_fail")), "err");

  const data = await resp.json();
  if (data.truncated) {
    $("pl-warning").textContent = t("playlist.truncated_warning", { total: data.total, limit: data.limit });
    show($("pl-warning"));
  }
  renderTracks(data);
}

function renderTracks(data) {
  const name = $("pl-name");
  name.textContent = data.name || "";
  name.classList.toggle("hidden", !data.name);

  const list = $("tracks-list");
  list.innerHTML = "";
  if (!data.tracks.length) {
    $("pl-status").textContent = t("playlist.no_tracks");
    return;
  }
  for (const track of data.tracks) {
    const li = document.createElement("li");
    li.className = "dict__item dict__item--clickable";
    li.tabIndex = 0;

    const title = document.createElement("span");
    title.className = "dict__lemma";
    title.textContent = track.title;
    const artist = document.createElement("span");
    artist.className = "dict__lang";
    artist.textContent = track.artist;

    li.append(title, artist);
    const open = () => openSong(track.title, track.artist);
    li.addEventListener("click", open);
    li.addEventListener("keydown", (e) => e.key === "Enter" && open());
    list.appendChild(li);
  }
}

// ---------- one song ----------
async function openSong(title, artist) {
  currentSong = { title, artist };
  $("ly-title").textContent = title;
  $("ly-artist").textContent = artist;
  $("lyrics-body").innerHTML = "";
  $("ly-status").textContent = t("playlist.loading_lyrics");
  show($("lyrics-view"));
  $("lyrics-view").scrollIntoView({ behavior: "smooth" });

  const resp = await apiFetch("/playlists/song/analyze", {
    method: "POST",
    body: JSON.stringify({ title, artist }),
  });
  if (!resp.ok) {
    const detail = await errText(resp, t("playlist.fetch_fail"));
    const known = { lyrics_not_found: "playlist.lyrics_not_found", language_unknown: "playlist.language_unknown" };
    $("ly-status").textContent = known[detail] ? t(known[detail]) : detail;
    return;
  }
  $("ly-status").textContent = "";
  renderLyrics(await resp.json());
}

function renderLyrics(data) {
  const body = $("lyrics-body");
  body.innerHTML = "";
  for (const line of data.lines) {
    const p = document.createElement("p");
    p.className = "lyrics__line";
    if (!line.tokens.length) p.innerHTML = "&nbsp;"; // keep blank lines visible
    for (const tok of line.tokens) {
      if (tok.status === "skip") {
        p.appendChild(document.createTextNode(tok.surface));
        continue;
      }
      const span = document.createElement("span");
      span.className = "w w--" + tok.status;
      span.textContent = tok.surface;
      if (tok.status === "unknown") {
        span.tabIndex = 0;
        span.addEventListener("click", () => translateWord(tok, line, span, data.language));
        span.addEventListener("keydown", (e) => e.key === "Enter" && translateWord(tok, line, span, data.language));
      }
      p.appendChild(span);
    }
    body.appendChild(p);
  }
}

// Tap an unknown word -> translate in its line context -> offer to add it.
async function translateWord(tok, line, span, language) {
  closePopover();
  const lineText = line.tokens.map((x) => x.surface).join("");
  const pop = popover(span);
  pop.textContent = t("playlist.translating");

  const resp = await apiFetch("/playlists/song/translate", {
    method: "POST",
    body: JSON.stringify({ lemma: tok.lemma, line: lineText, language }),
  });
  if (!resp.ok) {
    pop.textContent = t("playlist.fetch_fail");
    return;
  }
  const { translation } = await resp.json();
  pop.innerHTML = "";
  const tr = document.createElement("span");
  tr.className = "pop__tr";
  tr.textContent = `${tok.lemma} — ${translation || "—"}`;
  const add = document.createElement("button");
  add.className = "btn btn--primary btn--sm";
  add.textContent = t("playlist.add_word");
  add.addEventListener("click", () => addWord(tok.lemma, language, span, add));
  pop.append(tr, add);
}

async function addWord(lemma, language, span, btn) {
  btn.disabled = true;
  const resp = await apiFetch("/vocabulary", {
    method: "POST",
    body: JSON.stringify({ word: lemma, language }),
  });
  if (!resp.ok) {
    btn.disabled = false;
    return toast(await errText(resp, t("toast.save_fail")), "err");
  }
  // Now it's known: recolor and drop the popover.
  span.className = "w w--known";
  span.replaceWith(span.cloneNode(true)); // strip listeners
  closePopover();
  toast(t("playlist.added"));
}

// ---------- tiny popover ----------
function popover(anchor) {
  closePopover();
  const pop = document.createElement("div");
  pop.id = "pl-popover";
  pop.className = "pl-popover";
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.top = `${window.scrollY + r.bottom + 6}px`;
  pop.style.left = `${window.scrollX + r.left}px`;
  return pop;
}

function closePopover() {
  document.getElementById("pl-popover")?.remove();
}

// ---------- boot ----------
document.addEventListener("DOMContentLoaded", async () => {
  if (!TOKENS.access) {
    location.href = "index.html";
    return;
  }
  await window.i18nReady;
  $("pl-load").addEventListener("click", loadPlaylist);
  $("pl-url").addEventListener("keydown", (e) => e.key === "Enter" && loadPlaylist());
  $("ly-back").addEventListener("click", () => {
    hide($("lyrics-view"));
    closePopover();
  });
  document.addEventListener("click", (e) => {
    const pop = document.getElementById("pl-popover");
    if (pop && !pop.contains(e.target) && !e.target.classList.contains("w--unknown")) closePopover();
  });
});
