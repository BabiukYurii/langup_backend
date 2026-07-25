# LangUp — project context for Claude

AI-powered vocabulary learning SaaS. A browser extension + web cabinet let a user
save words (with sentence context) from web pages; the backend stores them as the
user's personal vocabulary, generates practice exercises, and schedules
spaced-repetition reviews.

## Repositories / paths
- **Backend + web cabinet:** `D:\ceva_part_time\langup_backend` (this repo). FastAPI.
- **Browser extension:** `D:\ceva_part_time\lang_extension\engup_exstention` (separate git repo, branch `main`, Chromium MV3).
- Web cabinet is static files in `frontend/`, served by the backend at `/app`.

## Deploy (self-hosted, NOT Render)
- Runs on a **home Ubuntu server** (`piatek@100.85.70.77`), behind **Cloudflare** at
  `https://langup.piatek-magazyn.com`. Render is no longer used.
- Deploy branch is **`dev`**. Steps on the server:
  `cd /home/piatek/Desktop/apps/langup_backend && git pull origin dev && docker compose up -d --build app`
  (frontend is baked into the image, so frontend changes need `--build`).
- **Prod DB** = Postgres **container** `langup-db` (`docker exec langup-db psql -U langup -d langup`).
  The API container is `langup-api` (listens on `8008` on the server). Redis container too.
- **AI gateway**: separate Ollama service at `https://ai.piatek-magazyn.com`
  (default model `aya-expanse:8b` for Ukrainian). The backend calls it for exercise generation.

## Architecture
Layered modular monolith, async-first. Request flow: **router → service → repository → model (SQLAlchemy async) → Postgres**. Pydantic `schemas/` cross the boundaries. DI via FastAPI `Depends` aliases in `app/dependencies.py`.

New feature = one **vertical**, always in this order:
`model → migration → repository → schema → service → router (+ dependencies.py) → tests`.

## Implemented so far (real, not scaffold)
- **Auth:** email/password `register`/`login`; Google OAuth (client sends Google `id_token`
  → `POST /api/auth/google`); JWT access + **rotating refresh tokens** (hashed store,
  reuse-detection); `logout` / `logout-all`; `GET /api/auth/me`. **Rate limiting**
  (per-IP + per-account lockout) and **security headers** middleware are live.
- **RBAC + admin panel:** `require_roles` (`core/security/rbac.py`); `/api/admin/*` gives
  full CRUD over users (create/edit/delete with guardrails), a user's vocabulary
  (add/remove), the shared dictionary (edit lemma/translation), and exercises
  (status/delete). Cabinet page at `/app/admin.html`, shown only to ADMIN/SUPER_ADMIN.
- **Users:** CRUD `/api/users`.
- **Words (shared dictionary):** get-or-create keyed by lemma+language.
  Capture **lemmatizes** the word offline via `simplemma` (`utils/lemmatize.py`),
  so inflections fold onto one entry; the captured surface form lives in `word_contexts`.
- **Capture (personal vocabulary):** `POST /api/vocabulary` (auth) → Word + Source +
  WordContext + `UserWord`; `GET /api/vocabulary` — my words + search.
- **Review (SM-2):** `GET /api/review/next`, `POST /api/review/{user_word_uuid}`.
- **Exercises (pre-generated pool):** per-user pool, statuses **READY → SERVED → COMPLETED**,
  5 types rotated (`FILL_IN_BLANKS, MULTIPLE_CHOICE, FLASHCARD, MATCH_PAIRS, TYPING`).
  `GET /api/exercises/next`, `POST /api/exercises/{uuid}/attempt` (grades + feeds SM-2),
  refill endpoints. Generation calls the Ollama gateway; runs on **Celery + Redis**
  (`CELERY_ENABLED`, worker concurrency 1) with a **BackgroundTasks fallback**.

Still **scaffold stubs** (planned, not implemented): payments vertical, most of the AI
layer beyond exercise generation (context analysis, difficulty, explanations), websockets,
S3/MinIO storage, observability (OTel/Prometheus/Sentry).

## DB migrations
`00001` users · `00002` words · `00003` oauth_accounts · `00004` sources/word_contexts/user_words ·
`00005` exercises/attempts · `00006` refresh_tokens. Hand-written (`down_revision` = previous).
Run automatically on deploy (`entrypoint.sh` → `alembic upgrade head`).

## Commands (uv)
- Tests: `uv run pytest -q`  (sqlite in-memory, no real DB)
- Lint/format: `uv run ruff check . && uv run ruff format .`  (both must pass before finishing)
- Apply migration: `uv run alembic upgrade head`
- Run app locally: `uv run python -m app.main`  → cabinet at http://localhost:8000/app/

## Conventions
- **Do NOT commit/push/deploy unless explicitly asked — each time separately.** Small logical commits.
- **Never add co-authorship / "Generated with Claude".** Author = the user. Commit without gpg-sign.
- Models must be **cross-dialect** (sqlite tests + Postgres): `UUIDType` from `models/base.py`;
  `JSONB().with_variant(JSON(), "sqlite")` for JSON columns.
- Repositories extend `repositories/base.py` (generic async CRUD).
- Tests: `tests/conftest.py` builds an in-memory sqlite engine (add new tables to `TEST_TABLES`),
  overrides `get_session`; for auth, register + login via `/api/auth`, or override
  `get_google_verifier` with a fake (no network).

## Gotchas
- **DATABASE_URL required** at import (settings). Local `.env` (gitignored); the server has its own.
- **db config** rewrites postgres URLs to asyncpg (+ssl); sqlite passes through untouched.
- After `repo.update_one` (calls `refresh`), relationships expire → reload with an eager-join
  query before reading them (avoids `MissingGreenlet`).
- **Cloudflare caching:** HTML is `no-cache` (always fresh); JS/CSS assets are cache-busted via
  `practice.js?v={mtime}` (`main.py _asset_version`) so a deploy auto-serves fresh JS. No manual purge.
- `mypy` is advisory in CI; `ruff` + `pytest` must pass.

## Extension (Chromium, `engup_exstention`)
- MV3. Popup login by **email/password** (`/api/auth/register|login`) **or** Google via
  `chrome.identity.launchWebAuthFlow` (redirect URI `https://<ext-id>.chromiumapp.org/`
  registered in the Google OAuth client).
- `content.js` shows a "+" on text selection → `background.js` posts to `POST /api/vocabulary`
  (word + sentence + source url). Also a right-click **context menu** (works in Chrome's PDF viewer).
- Shared config/token helpers in `config.js` (`langupApiFetch` with rotating-refresh retry).
- Being prepared for the Chrome Web Store: icons wired, unused permissions dropped; still needs
  a privacy-policy URL + permission justification in the Developer Dashboard.

## Roadmap (next verticals)
1. **Usage limits** — pick metric (generations vs completed exercises) + model (config threshold
   vs Plan+Subscription). Foundation for paid plans. `Plan`/`UsageLimit` scaffolds exist.
2. **Bulk dictionary import** (EN-UK / UK-PL tables → Redis queue → LLM only validates JSON).
3. **Paid subscriptions** (practice only).
