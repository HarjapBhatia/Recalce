#!/bin/bash
set -e

# Start FastAPI server (Render binds to $PORT dynamically)
echo "Starting FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
