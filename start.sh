#!/usr/bin/env bash
# Container entrypoint: apply migrations, then launch the API.
set -o errexit
set -o pipefail
set -o nounset

uv run alembic upgrade head
uv run python -m app.main
