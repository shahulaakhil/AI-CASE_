#!/usr/bin/env bash
# Start script for hosts that prefer a shell entry point.
set -euo pipefail
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-1}" --timeout-keep-alive 65
