#!/bin/bash
set -e

# Start Celery worker in the background (concurrency=1 to stay well within free tier 512MB RAM)
echo "Starting Celery worker in the background..."
celery -A app.core.celery_app worker --loglevel=info --concurrency=1 &

# Start FastAPI in the foreground (Render binds to $PORT dynamically)
echo "Starting FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
