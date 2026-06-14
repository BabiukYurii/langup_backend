# Architecture

## Goals

Modular · scalable · maintainable · async-first · event-driven · clean-architecture
oriented · DDD-inspired · microservice-ready · cloud-ready.

The codebase is a **modular monolith**: one deployable, internally split by domain and by
layer. Each domain can later be extracted into its own service because the only coupling
between domains goes through **services** and the **event bus**, never across repositories.

## Layers

```
            HTTP / WebSocket
                  │
            ┌─────▼─────┐
            │  routers  │   thin controllers, auth deps, request validation
            └─────┬─────┘
            ┌─────▼─────┐
            │  schemas  │   Pydantic v2 DTOs (in/out), no business logic
            └─────┬─────┘
            ┌─────▼─────┐
            │ services  │   business logic, orchestration, transactions
            └──┬─────┬──┘
   ┌───────────▼─┐ ┌─▼───────────┐
   │ repositories│ │ integrations│  AI providers, payment providers, oauth, storage
   └──────┬──────┘ └─────┬───────┘
   ┌──────▼──────┐       │
   │   models    │       │ external systems
   └──────┬──────┘       │
   ┌──────▼──────────────▼───────┐
   │  PostgreSQL · Redis · S3   │
   └────────────────────────────┘
```

Cross-cutting: `core/` (config, security, exceptions, logging), `middlewares/`
(request-id, rate limiting / IP throttling, security headers, audit), `events/` (async
domain events), `celery/` (background jobs), `websockets/` (realtime push).

## Dependency rule

Dependencies point **inward**: routers → services → repositories → models. Services depend
on repository and integration **interfaces** (e.g. `PaymentProvider`, `Storage`, the AI
`client`), so providers are swappable and unit tests can mock the edges. DI is wired with
FastAPI `Depends` aliases in `app/dependencies.py` (and `dependency-injector` where a richer
container helps).

## Domains

| Domain      | Responsibility                                                        |
|-------------|----------------------------------------------------------------------|
| auth        | JWT + refresh rotation, Google OAuth, sessions/devices, email verify, reset, RBAC, 2FA |
| users       | profile, preferences, languages                                      |
| vocabulary  | words, sources (captured pages), contexts; extension ingest          |
| learning    | exercises, spaced repetition, adaptive difficulty, recommendations, weakness analysis, paths, progress |
| ai          | context analysis, difficulty, exercise/explanation/quiz generation   |
| payments    | plans, subscriptions (state machine), payments, invoices, promo codes, webhooks, usage limits |

## Capture → learning flow

1. Extension sends structured JSON to `POST /api/capture` (`schemas/capture.py`).
2. `CaptureService` normalizes the word, upserts `Source` + `WordContext`, creates/updates
   the user's `UserWord`, and **emits an event** / enqueues a Celery job for AI analysis.
3. AI (`services/ai/*`) resolves the sense in context and estimates difficulty.
4. `SpacedRepetitionService` seeds the SM-2 schedule (`UserWord`, `ReviewSchedule`).
5. When the user studies, `ExerciseService` builds exercises via per-type generators
   (`services/learning/generators/*`), grades attempts, updates mastery and SRS state, and
   pushes realtime progress over WebSocket.

## Event-driven layer

Domain events (`events/topics.py`) are published to Redis Streams (`events/producer.py`) and
consumed by `events/consumer.py`, which dispatches to handlers. This decouples slow/optional
work (AI generation, receipts, analytics rollups) from the request path and keeps domains
loosely coupled. Idempotency is enforced for payment webhooks via the `webhook_events` table.

## Reliability & observability

- **Resilience:** `tenacity` retries around AI and payment provider calls; idempotency keys
  on payments and webhooks; Celery retry policies for failed payments / renewals.
- **Observability:** `structlog`/`loguru` structured logs with a request id, OpenTelemetry
  traces, Prometheus metrics, Sentry error reporting.
- **Security:** RBAC, rate limiting + IP throttling, secure cookies, CSRF/XSS protections,
  audit logs, secrets only via env/secret manager.
