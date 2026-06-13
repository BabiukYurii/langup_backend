# LangUp — Backend

AI-powered vocabulary learning SaaS. A browser extension captures words (with their
sentence, page context and optional HTML) as the user reads the web; the backend stores
them, uses AI to analyze context and generate exercises, and drives a personalized,
spaced-repetition learning system with subscriptions and payments.

> Status: **architecture skeleton**. Files are intentionally stubs with English comments
> describing what each module will contain. Models are mocked with field-level comments.

## Stack

FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic · PostgreSQL · Redis ·
Celery · aiokafka (event bus) · S3/MinIO · Anthropic/OpenAI · Stripe/PayPal/BLIK ·
structlog/loguru · OpenTelemetry/Sentry/Prometheus · Docker/K8s. Managed with **uv**.

## Layered architecture

Request flow: **router → service → repository → model (DB)**. Schemas (Pydantic) cross
the boundaries; integrations (AI/payment providers) and the event bus sit beside services.

```
routers/        HTTP endpoints (thin; delegate to services)
services/       business logic (auth, vocabulary, learning, ai, payments)
repositories/   data access over SQLAlchemy async
models/         ORM tables (mocked here with field comments)
schemas/        Pydantic v2 DTOs
events/         event-driven layer (Kafka producers/consumers/handlers)
celery/         background jobs (AI generation, SRS, billing, email)
core/           config, security, exceptions, logging
middlewares/    request-id, rate limit, security headers, audit
storage/ websockets/ utils/ database/ (+ alembic)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
(phased plan + git branches), [`docs/PAYMENTS.md`](docs/PAYMENTS.md), [`docs/AI.md`](docs/AI.md).

## Getting started (with uv)

```bash
uv sync                       # create venv + install from pyproject/uv.lock
cp .env.sample .env           # fill in secrets
docker compose up -d postgres redis minio
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
uv run python -m app.main     # or: docker compose up
```
