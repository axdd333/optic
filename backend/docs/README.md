# Optic V1 Backend

FastAPI server for the Optic signal intelligence engine. Analyzes your local file system to surface what can be inferred about you — all private and on-device.

## Quick Start

### Prerequisites

- Python 3.11+
- pip (or uv)

### Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Configure environment
cp .env.example .env
# Edit .env if you need to change host/port

# 3. Start the server
./start.sh
```

The server will be available at `http://localhost:3003`.

### One-liner

```bash
cd backend && pip install -r requirements.txt && python3 -c "
import sys
sys.path.insert(0, 'src')
from optic.v1.server import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=3003)
"
```

## Docker

### Build & Run

```bash
docker build -t optic-v1 .
docker run -p 3003:3003 -v optic_data:/app/.optic optic-v1
```

### Docker Compose

```bash
docker compose up -d
```

This persists the SQLite database in a named volume (`optic_data`).

## Endpoints

| Method | Path | Description |
|---------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/home` | Home panel data |
| GET | `/api/sources` | Connected data sources |
| GET | `/api/graph` | Topology graph |
| GET | `/api/workstreams` | Workstream clusters |
| GET | `/api/report` | Workstream report |
| GET | `/api/audiences` | Audience simulation |
| GET | `/api/contradictions` | Detected contradictions |
| POST | `/api/scan` | Trigger a filesystem scan |
| POST | `/api/iris` | Streaming LLM chat |

## Project Structure

```
backend/
├── src/
│   ├── optic/v1/        # V1 FastAPI server & intelligence engine
│   │   ├── server.py    # FastAPI app with all routes
│   │   ├── models.py    # Pydantic models
│   │   ├── lenses.py    # Audience lens definitions
│   │   ├── inference.py # Inference card generator
│   │   ├── contradiction.py
│   │   ├── graph.py
│   │   ├── iris_audit.py
│   │   ├── parsers.py
│   │   ├── resolver.py
│   │   └── scrapers.py
│   └── ctxorg/static/   # SPA frontend (served as static files)
├── .optic/v1.db         # SQLite database (auto-created)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── start.sh
└── .env.example
```

## Configuration

Set these environment variables in `.env` (or pass them directly):

| Variable | Default | Description |
|-----------|---------|-------------|
| `OPTIC_HOST` | `0.0.0.0` | Bind address |
| `OPTIC_PORT` | `3003` | Listen port |
| `OPTIC_PYTHON` | `python3` | Python interpreter path |

## Database

The server uses SQLite at `.optic/v1.db` (created automatically on first run). All data stays local — nothing is sent off-device.
