#!/usr/bin/env bash
set -euo pipefail

# ── Optic V1 — Self-Contained Startup ──────────────────────────────────────
# Starts the Optic inference audit server. Auto-seeds demo data on first run.
# No external dependencies required (ollama optional for richer iris chat).
#
# Usage:
#   ./start.sh                    # start on port 3003
#   OPTIC_PORT=8080 ./start.sh    # custom port
#   OPTIC_DATA_DIR=~/my-optic ./start.sh  # custom data directory

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── Config ──────────────────────────────────────────────────────────────────
export OPTIC_HOST="${OPTIC_HOST:-0.0.0.0}"
export OPTIC_PORT="${OPTIC_PORT:-3003}"
export OPTIC_DATA_DIR="${OPTIC_DATA_DIR:-$HOME/.optic}"
export OPTIC_DB_PATH="${OPTIC_DB_PATH:-$OPTIC_DATA_DIR/v1.db}"

# ── LLM inference (optional — iris chat uses DeepSeek if key is provided) ──
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-ef42d79c0ff64ba9bd21c011638397f6}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"

# ── Python setup ────────────────────────────────────────────────────────────
PYTHON="${OPTIC_PYTHON:-python3}"

if [ ! -d "venv" ]; then
    echo "Optic: creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

if [ ! -f "venv/.deps_installed" ]; then
    echo "Optic: installing dependencies..."
    pip install -q -r requirements.txt
    touch venv/.deps_installed
fi

# ── Database ────────────────────────────────────────────────────────────────
mkdir -p "$OPTIC_DATA_DIR"

# ── Start ───────────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       Optic V1 — Inference Audit        ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  Data:   $OPTIC_DATA_DIR"
echo "  Server: http://${OPTIC_HOST}:${OPTIC_PORT}"
echo ""
echo "  Open http://localhost:${OPTIC_PORT} in your browser."
echo ""

PYTHONPATH="src:$PYTHONPATH" uvicorn optic.v1.server:app \
    --host "$OPTIC_HOST" \
    --port "$OPTIC_PORT" \
    --log-level info
