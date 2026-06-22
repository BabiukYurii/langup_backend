# Dockerfile — production image for Render (Docker runtime).
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/venv

WORKDIR /app

# Install dependencies first (cached layer) using the lockfile.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the source and install the project itself.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM base

ENV UV_PROJECT_ENVIRONMENT=/app/venv

COPY --from=builder /app /app

WORKDIR /app
ENV PATH="/app/venv/bin:$PATH"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
