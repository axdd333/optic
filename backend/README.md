# Optic Backend

> **Local-first inference audit engine.** Scan your filesystem, surface what humans and algorithms infer about you, all on-device. No cloud required.

---

## Quick Start

```bash
# Clone and enter the project
git clone <repo-url> optic
cd optic/backend

# Option 1: One-command launch (recommended)
./run_optic.sh

# Option 2: Self-contained startup (auto-creates venv, installs deps)
./scripts/start.sh

# Option 3: Docker
docker compose up
```

Then open **http://localhost:8787** in your browser.

> **First run?** The server auto-scans your `~/Desktop`, `~/Documents`, and `~/Downloads` folders and seeds the database. No configuration needed.

---

## Architecture

| Component | Technology |
|-----------|------------|
| HTTP Server | Python `ThreadingHTTPServer` (stdlib) + FastAPI |
| Default Port | **8787** |
| Database | SQLite (`~/.optic/v1.db`) |
| LLM / Iris Chat | **Ollama local-first** (DeepSeek opt-in) |
| Frontend | Vanilla JS SPA (single `app.js`, ~8700 lines) + `app.css` |
| Graph | D3.js + Three.js (force-directed topology + 3D universe) |
| Deployment | Docker Compose ready |

The server is a stdlib `ThreadingHTTPServer` wrapping a flat route dispatcher in `src/ctxorg/server.py`. FastAPI is available as an alternative runtime layer in `src/optic/v1/server.py` for the V1 intelligence package.

---

## Current Scale

- **108 inference claims** generated across workstreams
- **58 API routes** (GET + POST) covering audit, workstreams, topology, simulations, exports, and Iris chat
- **10 UI modes**: Home, Map, Timeline, Universe, Iris, Vault, Audiences, Simulations, Exports, Scan
- **Auto-scan** on startup — filesystem scanner indexes `Desktop`, `Documents`, `Downloads`, and developer directories
- **Docker Compose** for single-container deployment

---

## Server Startup

### `run_optic.sh` (recommended)

The primary launcher. Kills any stale Optic processes, picks a clean port, auto-seeds the local user, and starts the server.

```bash
./run_optic.sh [PORT]
# Default: 8787
# Example: ./run_optic.sh 3005
```

### `scripts/start.sh`

Self-contained alternative that creates a Python virtual environment, installs dependencies, and starts on a configurable port.

```bash
./scripts/start.sh
# Env overrides: OPTIC_PORT, OPTIC_HOST, OPTIC_DATA_DIR
# For optional cloud LLM (opt-in): DEEPSEEK_API_KEY
OPTIC_PORT=8080 ./scripts/start.sh
```

### Docker

```bash
docker compose up        # port 3003
docker compose up -d     # detached
```

The Dockerfile is a single-stage Python 3.11-slim image. Data persists in a named volume (`optic_data`).

---

## Agent Swarm

Optic uses a **73-agent swarm** organized across **10 departments**, all driven by the canonical hyperdoc (`docs/optichyperdoc.rtf`). Each agent owns a specific capability or surface area.

### Swarm Dashboard

View the live swarm at: **http://localhost:8787/static/swarm.html**

### Departments

| Department | Agents | Responsibility |
|------------|--------|----------------|
| **ONBOARDING** | 5 | Consent ledger, source approval, welcome flow |
| **SCRAPER / OSINT** | 5 | URL scraping, GitHub, search APIs, OSINT research |
| **PIPELINE** | 5 | Signal extraction, evidence gating, contradiction detection |
| **INFERENCE** | 5 | Audience lenses, claim generation, confidence scoring |
| **REPAIR / REPORT** | 5 | Repair queue, report generation, export engine |
| **UI / UX** | 10 | Dashboard, topology UI, Iris chat, charts, animations, a11y |
| **INFRA / DEPLOY** | 5 | Docker, AWS prep, deployment, monitoring |
| **QA / TESTING** | 5 | Adversarial testing, edge cases, performance, audit quality |
| **DOCS / COMMS** | 4 | Documentation, README, release notes, hyperdoc keeper |
| **GOD DEPARTMENT** | 22 | Overseer, doctrine keeper, architect, security, innovation, night watch, and 16 specialist agents |

All agents are hyperdoc-driven: the build contract at `docs/optichyperdoc.rtf` defines what every agent must implement, and no feature ships without matching the hyperdoc spec.

---

## API Routes

### Core (GET)

| Route | Description |
|--------|-------------|
| `/api/health`, `/healthz` | Health check |
| `/api/ready`, `/readyz` | Readiness probe |
| `/api/home` | Home panel: workstreams, narratives, stats, Iris summary |
| `/api/workstreams` | Workstream clusters with confidence, topics, evidence |
| `/api/graph` | Topology graph (nodes + edges) |
| `/api/status` | Current scan/audit status |
| `/api/runs` | Audit run history |
| `/api/report` | Full workstream report |
| `/api/audiences` | Audience lens catalog |
| `/api/simulations` | Saved simulation histories |
| `/api/infer` | Node-level inference |
| `/api/analyze` | Corpus analysis |
| `/api/entity/profile` | Entity profile data |
| `/api/audit/history` | Audit session history |

### V1 Intelligence (GET)

| Route | Description |
|--------|-------------|
| `/api/v1/claims` | All inference claims |
| `/api/v1/claims/workstream/{name}` | Claims filtered by workstream |
| `/api/v1/contradictions` | Detected contradictions |
| `/api/v1/risks` | Risk flags and exposures |
| `/api/v1/repairs` | Repair action queue |
| `/api/v1/status` | V1 pipeline status (stages, progress) |
| `/api/v1/settings` | V1 configuration |
| `/api/v1/artifacts` | Scanned file artifacts |
| `/api/v1/onboarding` | Onboarding state |
| `/api/v1/exports` | Export format catalog |
| `/api/v1/audiences` | Audience lens definitions |
| `/api/v1/simulations` | Simulation payload |
| `/api/v1/health` | V1 health check |
| `/api/v1/audit/general` | Trigger or fetch general audit |

### Mutation (POST)

| Route | Description |
|--------|-------------|
| `/api/scan` | Trigger filesystem scan |
| `/api/iris` | Streaming Iris chat (local Ollama, DeepSeek opt-in) |
| `/api/chat` | Non-streaming chat |
| `/api/signup`, `/api/signin`, `/api/signout` | Local auth |
| `/api/settings` | Update settings |
| `/api/exports` | Create export |
| `/api/simulations/evaluate` | Run audience simulation |
| `/api/simulations/save` | Save simulation result |
| `/api/audit` | Single signal audit |
| `/api/audit/ml` | ML-only detection |
| `/api/audit/batch` | Batch audit |
| `/api/embed/run` | Run embedding pipeline |
| `/api/v1/reset` | Reset V1 state |
| `/api/v1/iris/ask` | Iris audit question |
| `/api/v1/audit/general` | Trigger general audit |
| `/api/v1/export/{format}` | Export in specified format |
| `/api/v1/repairs/{id}/complete` | Mark repair complete |
| `/api/ops/backup` | Create backup |
| `/api/ops/restore` | Restore from backup |

### Workspace, Billing, Integrations

Full routes for workspace management, API keys, billing webhooks, integrations catalog/state/secrets/OAuth, and more — all documented inline in `src/ctxorg/server.py`.

---

## Project Structure

```
backend/
├── run_optic.sh              # Primary launcher (recommended)
├── scripts/start.sh          # Self-contained venv-based launcher
├── restart_v1.sh             # Mac dev restart helper
├── Dockerfile                # Single-stage Python 3.11-slim
├── docker-compose.yml        # Single-container deployment
├── requirements.txt          # Python dependencies
├── config.example.json       # Config template (copy to config.json)
├── src/
│   ├── ctxorg/               # Main server runtime
│   │   ├── server.py         # HTTP server + route dispatcher (~10,500 lines)
│   │   ├── cli.py            # CLI entry point (default port 8765)
│   │   ├── scan.py           # Filesystem scanner
│   │   ├── workstreams.py    # Workstream clustering
│   │   ├── iris.py           # Iris chat agent
│   │   ├── deep.py           # Deep file analysis
│   │   ├── ollama.py         # Local Ollama model provider
│   │   ├── db.py             # SQLite helpers
│   │   ├── planner.py        # File organization planner
│   │   └── static/           # Vanilla JS SPA
│   │       ├── index.html    # Single-page shell
│   │       ├── app.js        # ~8,700 lines of frontend logic
│   │       ├── app.css       # Styles
│   │       └── swarm.html    # Agent swarm dashboard
│   └── optic/                # V1 intelligence package
│       ├── v1/
│       │   ├── server.py     # FastAPI server (3795 lines)
│       │   ├── models.py     # Canonical data models (14 models)
│       │   ├── lenses.py     # 9 audience lens definitions
│       │   ├── inference.py  # Evidence-gated claim generator
│       │   ├── contradiction.py  # Contradiction engine (5 types)
│       │   ├── risk.py       # Risk flag generator
│       │   ├── graph.py      # Evidence graph builder
│       │   ├── parsers.py    # Artifact parsers
│       │   ├── resolver.py   # Entity resolution
│       │   ├── scrapers.py   # External data scrapers
│       │   ├── iris_audit.py # Iris audit context
│       │   └── startup.py    # Workstream builder + scanner
│       └── signal/           # Signal detection engine
│           ├── auditor.py    # SignalAuditor
│           ├── detectors.py  # Pattern, anomaly, threshold detectors
│           └── ml_detector.py    # ML-based detection
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | (none) | DeepSeek API key (opt-in — system works fully offline without it) |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model for DeepSeek (only used if `DEEPSEEK_API_KEY` is set) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek API base URL (only used if `DEEPSEEK_API_KEY` is set) |
| `OPTIC_PORT` | `8787` | Server port |
| `OPTIC_HOST` | `127.0.0.1` | Bind address |
| `OPTIC_DATA_DIR` | `~/.optic` | Database and state directory |
| `OPTIC_DB_PATH` | `~/.optic/v1.db` | SQLite database path |
| `LOCAL_MODE` | — | Enable local-only mode |
| `ENABLE_EXTERNAL_SCRAPERS` | — | Enable external data collection |
| `OLLAMA_BASE_URL` | — | Ollama endpoint (for local models) |

Missing optional variables disable corresponding features with clear UI status — the core loop always works.

---

## Key Principles

- **Local-first**: All analysis runs on-device. No data leaves your machine.
- **Evidence-gated**: Every inference claim must cite supporting evidence. Weakening evidence is shown alongside.
- **Consent-scoped**: Sources must be approved before processing. Revoked sources are excluded from future audits.
- **Confidence-banded**: Claims show Low/Medium/High confidence, never fake hyper-precision.
- **Repair-oriented**: Every risk and contradiction links to a concrete repair action.
- **No universal identity score**: Optic shows what specific audiences can infer, not a single judgment.

---

## Docs

- **Hyperdoc (build contract)**: `docs/optichyperdoc.rtf`
- **Frontend README**: `../README.md` (Next.js marketing site)
- **Agent swarm dashboard**: `http://localhost:8787/static/swarm.html`
- **CLAUDE.md**: Developer guidance at repo root and `backend/CLAUDE.md`
