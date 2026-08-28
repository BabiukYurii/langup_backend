"use strict";

// "Understand your playlist": import a Spotify link (parsed + analysed in the
// background), browse saved playlists and their songs with per-song new-word
// counts, open a song to read the lyrics with known words green, learning amber
// and unknown red; tap a red word to translate it and add it (as known or to
// learn). CFG/TOKENS/apiFetch/t from api.js / i18n.js.
const $ = (id) => document.getElementById(id);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

const IMPORT_TASK_KEY = "langup_playlist_import";

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

const statusLabel = (s) => t("playlist.status_" + s) || s;

// ---------- saved playlists ----------
async function loadPlaylists() {
  const resp = await apiFetch("/playlists");
  if (resp.status === 401) return (location.href = "index.html");
  if (!resp.ok) return;
  const items = await resp.json();
  $("playlists-empty").classList.toggle("hidden", items.length > 0);

  const list = $("playlists-list");
  list.innerHTML = "";
  for (const p of items) {
    const li = document.createElement("li");
    li.className = "dict__item admin__ex";

    const name = document.createElement("span");
    name.className = "dict__lemma dict__item--clickable";
    name.textContent = p.name || "—";
    name.addEventListener("click", () => openPlaylist(p.uuid, p.name));

    const meta = document.createElement("span");
    meta.className = "dict__lang";
    meta.textContent = `${p.song_count} · ${statusLabel(p.status)}`;

    const actions = document.createElement("span");
    actions.className = "admin__actions";
    const del = document.createElement("button");
    del.className = "admin__icon-btn";
    del.textContent = "✕";
    del.title = t("playlist.delete");
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deletePlaylist(p.uuid);
    });
    actions.appendChild(del);

    li.append(name, meta, actions);
    li.addEventListener("click", () => openPlaylist(p.uuid, p.name));
    list.appendChild(li);
  }
}

async function deletePlaylist(uuid) {
  if (!confirm(t("playlist.delete_confirm"))) return;
  const resp = await apiFetch(`/playlists/${uuid}`, { method: "DELETE" });
  if (resp.status === 204) {
    toast(t("playlist.deleted"));
    loadPlaylists();
  } else {
    toast(await errText(resp, t("toast.save_fail")), "err");
  }
}

// ---------- import ----------
function showBar(indeterminate, pct) {
  const bar = $("pl-progress");
  show(bar);
  bar.classList.toggle("progress--indeterminate", !!indeterminate);
  bar.firstElementChild.style.width = indeterminate ? "" : `${pct || 0}%`;
}
function finishBar() {
  hide($("pl-progress"));
  $("pl-import").disabled = false;
}

async function importPlaylist() {
  const url = $("pl-url").value.trim();
  if (!url) return;
  $("pl-import").disabled = true;
  showBar(true);
  $("pl-status").textContent = t("playlist.importing_start");

  const resp = await apiFetch("/playlists", { method: "POST", body: JSON.stringify({ url }) });
  if (!resp.ok) {
    finishBar();
    return toast(await errText(resp, t("playlist.fetch_fail")), "err");
  }
  const { task_id } = await resp.json();
  if (!task_id) {
    // Ran in-process (no worker): it's already done.
    $("pl-status").textContent = "";
    $("pl-url").value = "";
    finishBar();
    return loadPlaylists();
  }
  localStorage.setItem(IMPORT_TASK_KEY, task_id);
  trackImport(task_id);
}

async function trackImport(taskId) {
  $("pl-import").disabled = true;
  const until = Date.now() + 30 * 60 * 1000;
  while (Date.now() < until) {
    const resp = await apiFetch(`/playlists/import/${taskId}`);
    if (resp.ok) {
      const { status, done, total } = await resp.json();
      if (status === "done") {
        $("pl-status").textContent = "";
        $("pl-url").value = "";
        localStorage.removeItem(IMPORT_TASK_KEY);
        finishBar();
        return loadPlaylists();
      }
      if (status === "failed") {
        $("pl-status").textContent = t("playlist.import_failed");
        localStorage.removeItem(IMPORT_TASK_KEY);
        return finishBar();
      }
      if (total) {
        const pct = Math.round((done / total) * 100);
        showBar(false, pct);
        $("pl-status").textContent = t("playlist.importing", { done, total });
      }
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  finishBar();
}

function resumeImportIfAny() {
  const taskId = localStorage.getItem(IMPORT_TASK_KEY);
  if (!taskId) return;
  showBar(true);
  $("pl-status").textContent = t("playlist.importing_start");
  trackImport(taskId);
}

// ---------- one playlist ----------
async function openPlaylist(uuid, name) {
  hide($("lyrics-view"));
  $("sv-name").textContent = name || "";
  $("songs-list").innerHTML = "";
  show($("songs-view"));
  $("songs-view").scrollIntoView({ behavior: "smooth" });

  $("songs-search").value = "";
  const resp = await apiFetch(`/playlists/${uuid}`);
  if (!resp.ok) return toast(await errText(resp, t("playlist.fetch_fail")), "err");
  currentSongs = (await resp.json()).songs;
  renderSongs(currentSongs);
}

let currentSongs = []; // songs of the open playlist, for client-side search

function filterSongs(query) {
  const q = query.trim().toLowerCase();
  renderSongs(q ? currentSongs.filter((s) => s.title.toLowerCase().includes(q)) : currentSongs);
}

function renderSongs(songs) {
  const list = $("songs-list");
  list.innerHTML = "";
  $("songs-empty").classList.toggle("hidden", songs.length > 0);
  for (const s of songs) {
    const li = document.createElement("li");
    li.className = "dict__item dict__item--clickable admin__ex";

    const title = document.createElement("span");
    title.className = "dict__lemma";
    title.textContent = s.title;
    const artist = document.createElement("span");
    artist.className = "dict__lang";
    artist.textContent = s.artist;

    const badge = document.createElement("span");
    badge.className = "song-badge";
    if (s.language) badge.textContent = s.language;
    if (s.unknown_count !== null && s.unknown_count !== undefined) {
      const nw = document.createElement("span");
      nw.className = "song-new";
      nw.textContent = t("playlist.new_words", { n: s.unknown_count });
      li.append(title, artist, badge, nw);
    } else {
      li.append(title, artist, badge);
    }

    const open = () => openSong(s.title, s.artist);
    li.addEventListener("click", open);
    li.addEventListener("keydown", (e) => e.key === "Enter" && open());
    li.tabIndex = 0;
    list.appendChild(li);
  }
}

// ---------- one song (lyrics) ----------
async function openSong(title, artist) {
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
    if (!line.tokens.length) p.innerHTML = "&nbsp;";
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

// Tap an unknown word -> translate in context -> "I know it" / "Learn it".
async function translateWord(tok, line, span, language) {
  closePopover();
  const lineText = line.tokens.map((x) => x.surface).join("");
  const pop = popover(span);
  pop.textContent = t("playlist.translating");

  // Send the word as it appears in the song (surface form), not our lemma: the
  // offline lemmatizer occasionally mangles words, which mistranslated them.
  const resp = await apiFetch("/playlists/song/translate", {
    method: "POST",
    body: JSON.stringify({ word: tok.surface, lemma: tok.lemma, line: lineText, language }),
  });
  if (!resp.ok) {
    pop.textContent = t("playlist.fetch_fail");
    return;
  }
  const { translation } = await resp.json();
  pop.innerHTML = "";
  const tr = document.createElement("span");
  tr.className = "pop__tr";
  tr.textContent = `${tok.surface} — ${translation || "—"}`;

  const actions = document.createElement("div");
  actions.className = "pop__actions";
  actions.append(
    actionBtn("btn--ghost", t("playlist.add_known"), () => addWord(tok.surface, language, span, true)),
    actionBtn("btn--primary", t("playlist.add_learn"), () => addWord(tok.surface, language, span, false)),
  );
  pop.append(tr, actions);
}

function actionBtn(variant, label, onClick) {
  const b = document.createElement("button");
  b.className = `btn ${variant} btn--sm`;
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

async function addWord(lemma, language, span, known) {
  closePopover();
  const resp = await apiFetch("/playlists/song/word", {
    method: "POST",
    body: JSON.stringify({ lemma, language, known }),
  });
  if (!resp.ok) return toast(await errText(resp, t("toast.save_fail")), "err");
  span.className = "w w--" + (known ? "known" : "learning");
  span.replaceWith(span.cloneNode(true));
  toast(known ? t("playlist.added_known") : t("playlist.added_learn"));
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
  $("pl-import").addEventListener("click", importPlaylist);
  $("pl-url").addEventListener("keydown", (e) => e.key === "Enter" && importPlaylist());
  $("sv-back").addEventListener("click", () => {
    hide($("songs-view"));
    hide($("lyrics-view"));
  });
  $("songs-search").addEventListener("input", (e) => filterSongs(e.target.value));
  $("ly-back").addEventListener("click", () => {
    hide($("lyrics-view"));
    closePopover();
  });
  document.addEventListener("click", (e) => {
    const pop = document.getElementById("pl-popover");
    if (pop && !pop.contains(e.target) && !e.target.classList.contains("w--unknown")) closePopover();
  });
  loadPlaylists();
  resumeImportIfAny();
});
