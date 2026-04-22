#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

python server.py &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

cd frontend && pnpm dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
cd ..

echo "JARVIS starting. Open http://localhost:5173 in Chrome."
wait
