#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Starting D-Bus session bus..."
eval $(dbus-launch --sh-syntax)

echo "[entrypoint] Starting jami-daemon..."
/usr/libexec/jamid &
JAMI_PID=$!
sleep 3

echo "[entrypoint] Starting API server..."
exec python3 -m uvicorn app.main:app \
    --host "${JAMI_API_HOST:-0.0.0.0}" \
    --port "${JAMI_API_PORT:-8080}" \
    --log-level "${JAMI_API_LOG_LEVEL:-info}"
