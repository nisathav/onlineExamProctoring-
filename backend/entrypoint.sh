#!/bin/sh
# Start-up script run when the backend container starts:
#   1. applies database migrations (creates/updates tables)
#   2. optionally loads demo data (staff1, student1, sample exam) when SEED_DATA=true
#   3. starts the API server (auto-reload in development, several workers in production)
set -e

alembic upgrade head

if [ "${SEED_DATA:-false}" = "true" ]; then
    python -m app.seed
fi

if [ "${ENVIRONMENT:-development}" = "development" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}" --proxy-headers --forwarded-allow-ips="*"
