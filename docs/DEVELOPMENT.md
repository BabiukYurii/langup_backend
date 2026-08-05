# Development strategy & branch plan

A phased, dependency-ordered plan. Each phase produces something runnable and testable
before the next builds on it. This document is kept in sync with reality.

**Status legend:** ✅ done · 🟨 partial · ⬜ not started.

## Current snapshot
- ✅ **Phase 0 — Foundation** (config, exceptions, async DB, alembic, app factory, health).
- 🟨 **Phase 1 — Auth**: Google OAuth + email/password login + JWT with **rotating refresh
  tokens** (hashed store, reuse-detection) + users + **RBAC/admin panel** + **rate limiting**
  + security headers — done; email verification, reset, sessions/devices UI, 2FA — not yet.
- ✅ **Phase 2 — Vocabulary capture** (personal vocabulary with sentence context; offline
  lemmatization via `simplemma`).
- 🟨 **Phase 3 — Learning core**: SM-2 + **exercise pool** (5 types, READY→SERVED→COMPLETED,
  grade→SM-2, Celery/Redis with BackgroundTasks fallback) done; learning sessions, progress
  metrics, websockets — not yet.
- 🟨 **Phase 4 — AI**: exercise generation calls the **live llama.cpp gateway** (Gemma-4-26B-A4B); the rest of the
  AI layer (context analysis, difficulty, explanations) — not yet.
- ⬜ **Phase 5 — Payments**.
- 🟨 **Phase 6 — Hardening**: CI + self-hosted Docker deploy + rate limiting + security headers
  + DB resilience done; observability, event bus, object storage — not yet.

Deployed on a **self-hosted Ubuntu server** (Docker Compose, branch `dev`) behind
**Cloudflare** at `https://langup.piatek-magazyn.com`; prod DB is a **Postgres container**
(`langup-db`). Web cabinet served at `/app`; Chromium extension writes to the same API.

## Key decisions (diverged from the original plan)
- **Auth: both Google (extension-driven) and email/password.**
- **AI runs on a local LLM** — a llama.cpp server behind a FastAPI gateway (`langup_ai`),
  model **Gemma-4-26B-A4B** on an AMD 780M iGPU (Vulkan), reached at
  `https://ai.piatek-magazyn.com` — not Anthropic/OpenAI.
- **Events: Redis Streams only, plus Celery** for background jobs — Kafka is dropped.
- **Deploy: self-hosted Ubuntu + Docker Compose** (was Render). Kubernetes is optional/later.

## Git workflow
- Long-lived branches: **`main`** (releasable) and **`dev`** (integration).
- Work on a feature branch → merge into `dev` (`--no-ff`); release `dev → main`.
  Small fixes may go directly on `dev`.
- Naming: `feat/<area>-<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- Migrations: never edit an applied one — add a new `000NN_*`. The server runs
  `alembic upgrade head` automatically on deploy (`entrypoint.sh`).

```
main
 └── dev
      └── feat/...
```

---

## Phase 0 — Foundation ✅

- ✅ uv project, pyproject, ruff/mypy/pre-commit, `.env.sample`.
- ✅ docker-compose (dev), Dockerfile + `entrypoint.sh` for Render.
- ✅ `core/config/*` settings aggregator.
- ✅ exception hierarchy + handlers.
- ✅ async engine/session, `models/base.py` (cross-dialect UUID/JSON), base repository.
- ✅ alembic async env + migrations.
- ✅ `main.py` app factory, router wiring, `/api/health`.

## Phase 1 — Auth & security 🟨

- ✅ `feat/user-model` — `users` table + repository + schemas.
- ✅ `feat/auth-jwt` — JWT access + **rotating refresh tokens** (hashed store, reuse-detection),
  `get_current_user`, `logout` / `logout-all`.
- ✅ `feat/auth-google-oauth` — Google ID-token verification, get-or-create user, `oauth_accounts`.
- ✅ `feat/auth-password` — register/login with password (cabinet + extension).
- ✅ `feat/rbac` — roles + `require_roles` + admin panel (`/api/admin/*`, full CRUD with guardrails).
- ✅ `feat/security-middleware` — rate limiting (per-IP + per-account lockout) + security headers.
- ⬜ `feat/auth-email-verification` · ⬜ `feat/auth-password-reset`.
- ⬜ `feat/auth-sessions-devices` — device/session management UI (refresh-token store exists).
- ⬜ `feat/auth-2fa` — TOTP (later, feature-flagged).

## Phase 2 — Vocabulary capture ✅

- ✅ `feat/vocabulary-models` — `words`, `sources`, `word_contexts`, `user_words` + repositories.
- ✅ `feat/capture-endpoint` — `POST /api/vocabulary` + `CaptureService` (get-or-create, dedup).
- ✅ `feat/vocabulary-api` — `GET /api/vocabulary` (my words + search); cabinet + extension wired.

## Phase 3 — Learning core (no AI yet) 🟨

- ✅ `feat/spaced-repetition` — SM-2 scheduler; `GET /api/review/next`, `POST /api/review/{uuid}`.
- ✅ `feat/exercise-pool` — pre-generated per-user pool, 5 types
  (`FILL_IN_BLANKS, MULTIPLE_CHOICE, FLASHCARD, MATCH_PAIRS, TYPING`), statuses
  READY→SERVED→COMPLETED, `GET /api/exercises/next`, `POST /api/exercises/{uuid}/attempt`
  (grades + feeds SM-2), refill via Celery/Redis with a BackgroundTasks fallback.
- ⬜ `feat/exercise-generators` — remaining types (sentence reconstruction, timed challenge, listening).
- ⬜ `feat/learning-sessions` — start session, fetch due items, submit attempts, grade + update SRS.
- ⬜ `feat/progress-tracking` — streaks, mastery counts, retention metrics.
- ⬜ `feat/realtime-websocket` — push exercise-ready / progress events.

## Phase 4 — AI features (local small LLM) ⬜

Runs against a **local llama.cpp service** (OpenAI-compatible /v1), not a cloud provider.

- ✅ `feat/ai-service` — separate FastAPI gateway (`langup_ai`) in front of llama.cpp +
  structured-JSON validation (model: Gemma-4-26B-A4B, QAT-Q4 GGUF, iGPU/Vulkan).
- ⬜ `feat/ai-client` — provider-agnostic client in the backend pointing at the local endpoint
  (retries/timeouts/structured output/token log).
- ⬜ `feat/ai-context-analysis` — resolve the word's sense in its captured sentence.
- ⬜ `feat/ai-difficulty-estimation` — per-user difficulty scoring + adaptive difficulty.
- ⬜ `feat/ai-exercise-generation` — AI contextual exercises + dynamic quizzes.
- ⬜ `feat/ai-explanations` — explanations/hints for words and mistakes.
- ⬜ `feat/async-ai-jobs` — run AI work **asynchronously** (Celery + Redis Streams events),
  never in the request path; persist `ai_generations`.

> Since the backend is now self-hosted on the same home network as the AI mini-PC, it reaches
> the llama.cpp gateway directly (`https://ai.piatek-magazyn.com`) — no cloud→home tunnel needed.

## Phase 5 — Payments & subscriptions ⬜

- ⬜ `feat/payment-models` — plans, subscriptions, payments, invoices, promo codes,
  webhook events, usage limits.
- ⬜ `feat/payment-provider-abstraction` — `PaymentProvider` protocol + base.
- ⬜ `feat/stripe-provider` — first concrete provider + checkout.
- ⬜ `feat/subscription-state-machine` — transitions + lifecycle (trial, active, past_due, cancel).
- ⬜ `feat/webhooks-idempotency` — `/webhooks/{provider}` verify + dedup + dispatch events.
- ⬜ `feat/billing-invoices` · ⬜ `feat/promo-codes` · ⬜ `feat/usage-limits`.
- ⬜ `feat/failed-payment-retries` — Celery retries, dunning, auto-renewal.
- ⬜ `feat/paypal-provider`, `feat/blik-provider` (Poland), additional providers.

## Phase 6 — Hardening & production 🟨

- ✅ `chore/ci-cd` — GitHub Actions (ruff/format/pytest; mypy advisory).
- ✅ deploy — Dockerfile + `entrypoint.sh` on a self-hosted Ubuntu server (Docker Compose,
  Postgres container) behind Cloudflare; auto-migrations on deploy.
- ✅ `feat/security` — rotating refresh tokens, rate limiting, security headers, RBAC.
- 🟨 `feat/db-resilience` — `pool_pre_ping` + `pool_recycle` for idle connections (done).
- ⬜ `feat/observability` — OpenTelemetry traces, Prometheus metrics, Sentry.
- ⬜ `feat/event-bus-redis` — promote in-process events to **Redis Streams** + consumer service.
- ⬜ `feat/feature-flags` · ⬜ `chore/k8s-manifests` (optional).
- ⬜ `feat/object-storage` — S3/MinIO for TTS audio + exports.
- ⬜ `test/coverage` — broaden unit/integration/e2e.

---

## Recommended next order

`usage limits → bulk dictionary import → payments → AI layer → progress/observability`.

Immediate next vertical: **usage limits** (pick the metric — generations vs completed
exercises — and the model — config threshold vs `Plan`+`Subscription`), which is the
foundation for **paid subscriptions**. The `Plan`/`UsageLimit` scaffolds already exist.
