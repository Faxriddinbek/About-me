#!/usr/bin/env sh
# Production entrypoint: apply migrations, then serve.
#
# Migrations run BEFORE Gunicorn binds, so the app never accepts traffic against
# an out-of-date schema. `exec` replaces this shell with Gunicorn so it becomes
# PID 1 and receives signals (SIGTERM) directly for clean shutdowns.
set -eu

echo "==> Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "==> Starting Gunicorn with ${WEB_CONCURRENCY:-2} Uvicorn worker(s) on port ${PORT:-8000}..."
exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-2}" \
    --bind "0.0.0.0:${PORT:-8000}" \
    --access-logfile - \
    --error-logfile -
