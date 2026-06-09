#!/usr/bin/env bash
set -euo pipefail
# ── Optic V1 Server — Robust Launcher ──────────────────────────────
# Kills old processes, picks a clean port, auto-seeds user, starts server.
# Usage: ./run_optic.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-3005}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-ef42d79c0ff64ba9bd21c011638397f6}"

# ── Kill old instances ─────────────────────────────────────────────
echo "Optic: cleaning old processes..."
for p in 3000 3003 3004 3005 3006; do
    pid=$(lsof -ti :$p 2>/dev/null) || true
    [ -n "$pid" ] && kill -9 $pid 2>/dev/null && echo "  killed port $p"
done
sleep 1

# ── Ensure user with valid UUID ─────────────────────────────────────
python3 -c "
import sqlite3, os
db = os.path.join(os.path.dirname(os.path.abspath('__file__')), '.optic', 'v1.db')
conn = sqlite3.connect('.optic/v1.db')
conn.row_factory = sqlite3.Row
user = conn.execute('SELECT * FROM users LIMIT 1').fetchone()
if not user:
    from uuid import uuid4
    conn.execute('INSERT INTO users(id,email,settings,local_mode,created_at) VALUES(?,?,?,?,?)',
                 (str(uuid4()),'local@optic.app','{}',1,'2026-01-01'))
    conn.commit()
conn.close()
" 2>/dev/null || true

# ── Start ───────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       Optic V1 — Inference Audit        ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  → http://localhost:${PORT}"
echo ""

cd "$SCRIPT_DIR"
python3 -c "
import sys; sys.path.insert(0,'src')
from optic.v1.server import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=${PORT}, log_level='info')
"
