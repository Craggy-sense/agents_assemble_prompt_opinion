#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — Simple launcher for the Oncology Care Coordinator (OCC)
# ─────────────────────────────────────────────────────────────────────────────
PORT=8001
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🧬 Oncology Care Coordinator (OCC) — Starting..."

# 1. Free the port
echo "⏹  Freeing port $PORT..."
lsof -ti tcp:$PORT | xargs kill -9 2>/dev/null || true
sleep 1

# 2. Check for Ngrok
if ! pgrep -x "ngrok" > /dev/null
then
    echo "⚠️  Ngrok is not running. Please run 'ngrok http 8001' in a separate terminal."
else
    echo "✅  Ngrok detected."
fi

# 3. Start the server
echo "🚀 Starting server..."
cd "$PROJECT_DIR"
source .venv/bin/activate
uvicorn ecc_agent.app:a2a_app --host 0.0.0.0 --port $PORT
