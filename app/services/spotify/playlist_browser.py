"""Read a full playlist with a headless browser (Playwright + Chromium).

The embed page (used by playlist_parser) is fast but caps at ~100 tracks and
can't scroll. When PLAYLIST_USE_BROWSER is on, this drives a headless Chromium
that scrolls the virtualized tracklist and collects every row, so large
playlists come through in full. Slower and more fragile (Spotify's DOM can
change) — hence it's opt-in with the embed as a fallback.

Only stable hooks are used (data-testid / href patterns / aria-*), never the
obfuscated class names.
"""

import logging

from app.schemas.playlist import PlaylistTrackOut

logger = logging.getLogger(__name__)

# Collect the rows currently rendered in the virtualized grid, keyed by their
# aria-rowindex so scrolling can't produce duplicates.
_JS_COLLECT = r"""
() => {
  const grid = document.querySelector('[role="grid"]');
  const rowcount = grid ? parseInt(grid.getAttribute('aria-rowcount') || '0', 10) : 0;
  const rows = [];
  for (const row of document.querySelectorAll('div[role="row"][aria-rowindex]')) {
    const link = row.querySelector('a[data-testid="internal-track-link"]');
    if (!link) continue;
    const artist = row.querySelector('a[href^="/artist/"]');
    const href = link.getAttribute('href') || '';
    rows.push({
      index: parseInt(row.getAttribute('aria-rowindex'), 10),
      title: link.textContent.trim(),
      artist: artist ? artist.textContent.trim() : '',
      track_id: href.startsWith('/track/') ? href.slice(7) : null,
    });
  }
  const meta = document.querySelector('meta[property="og:title"]');
  return {rowcount, name: meta ? meta.getAttribute('content') : null, rows};
}
"""

_SCROLL_LAST = """() => {
  const rows = document.querySelectorAll('div[role="row"][aria-rowindex]');
  if (rows.length) rows[rows.length - 1].scrollIntoView();
}"""


def rows_to_tracks(collected: dict[int, dict], limit: int) -> list[PlaylistTrackOut]:
    """Ordered, capped tracks from the {rowindex: row} map. Pure/testable."""
    ordered = [collected[i] for i in sorted(collected)]
    return [
        PlaylistTrackOut(title=r["title"], artist=r["artist"], spotify_id=r.get("track_id"))
        for r in ordered
        if r.get("title")
    ][:limit]


async def fetch_playlist_via_browser(
    playlist_id: str, limit: int, timeout_s: float
) -> tuple[str | None, list[PlaylistTrackOut]]:
    """(name, tracks) for a playlist by scrolling the page in headless Chromium."""
    from playwright.async_api import async_playwright

    url = f"https://open.spotify.com/playlist/{playlist_id}"
    collected: dict[int, dict] = {}
    name: str | None = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            page.set_default_timeout(int(timeout_s * 1000))
            await page.goto(url, wait_until="domcontentloaded")
            try:  # cookie banner, if shown
                await page.click("#onetrust-accept-btn-handler", timeout=4000)
            except Exception:  # noqa: BLE001 — no banner is fine
                pass
            await page.wait_for_selector('a[data-testid="internal-track-link"]')

            expected: int | None = None
            stable = 0
            for _ in range(200):
                data = await page.evaluate(_JS_COLLECT)
                name = data.get("name") or name
                if data.get("rowcount"):
                    expected = data["rowcount"] - 1  # minus the header row
                before = len(collected)
                for r in data["rows"]:
                    collected[r["index"]] = r
                if (expected and len(collected) >= expected) or len(collected) >= limit:
                    break
                stable = stable + 1 if len(collected) == before else 0
                if stable >= 8:  # list stopped growing — assume fully loaded
                    break
                await page.evaluate(_SCROLL_LAST)
                await page.wait_for_timeout(350)
        finally:
            await browser.close()

    return name, rows_to_tracks(collected, limit)
