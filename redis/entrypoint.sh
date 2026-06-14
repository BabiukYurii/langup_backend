#!/usr/bin/env sh
# Redis entrypoint: start the server with the project config (password from env).
set -e
exec redis-server --requirepass "${REDIS_PASSWORD}" --appendonly yes
