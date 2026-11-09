#!/bin/bash
# entrypoint.sh — runs on container start (Render).
set -e

echo "Running database migrations..."
alembic upgrade head

# Only a SUPER_ADMIN can create a privileged user, so an empty users table has
# no way back into the admin panel. This seeds the first one when
# ADMIN_BOOTSTRAP_EMAIL/PASSWORD are set, and is a no-op once one exists.
# Deliberately here and not in a migration: a migration runs once, and the case
# that needs this is the SECOND time a database is emptied.
echo "Ensuring an administrator exists..."
# `set -e` is on, so an import failure here would stop the app from
# starting at all — and an instance that cannot seed an admin should still
# serve the learners it already has.
python -m scripts.bootstrap_admin || echo "bootstrap_admin: skipped"

echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
