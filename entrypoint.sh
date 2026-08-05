#!/bin/bash
# entrypoint.sh — runs on container start (Render).
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
