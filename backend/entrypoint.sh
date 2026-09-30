#!/bin/sh
set -e

alembic upgrade head

if [ "${SEED_DATA:-false}" = "true" ]; then
    python -m app.seed
fi

if [ "${ENVIRONMENT:-development}" = "development" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}" --proxy-headers --forwarded-allow-ips="*"
