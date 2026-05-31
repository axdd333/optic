# Optic

Private perception intelligence for high-stakes professional identity.

## Overview

Monorepo with two runtimes:

| Directory | Runtime | Default port |
|-----------|---------|-------------|
| `/` | Next.js 15 — marketing site, auth, app shell | 3000 |
| `backend/` | Python — ctxorg server + optic signal engine | 3003 |

The Next.js site proxies all backend requests through `/api/backend/*` → `backend/` at port 3003.

## Setup

### Frontend

```sh
npm install
npm run dev        # http://localhost:3000
```

Copy `.env.local` from the example below and set your backend URL:

```sh
# .env.local
NEXT_PUBLIC_AUDIT_FORM_URL=/login
OPTIC_BACKEND_URL=http://127.0.0.1:3003
```

### Backend

```sh
cd backend
cp config.example.json config.json   # edit home/target/sources for your machine
python3 -m src.ctxorg serve --cfg config.json --host 127.0.0.1 --port 3003
```

Requires Python 3.11+ and [Ollama](https://ollama.ai) running locally with `phi4-mini` pulled.

## Architecture

```
browser
  └── localhost:3000  (Next.js)
        ├── /                    marketing site
        ├── /login, /signup      local-first auth → .optic/users.json
        ├── /app                 signal audit UI
        └── /api/backend/*  ──► localhost:3003  (ctxorg Python server)
                                      ├── /api/audit        signal audit
                                      ├── /api/audit/ml     ML detection
                                      ├── /api/audit/batch  batch audit
                                      ├── /api/scan         file scan
                                      ├── /api/chat         AI chat
                                      ├── /api/graph        workspace graph
                                      └── /healthz
```

## Signal Audit

The audit engine (`backend/src/optic/signal/`) detects:

- **Loaded language** — emotionally charged or manipulative phrasing
- **Absolute language** — overgeneralisation (everyone, always, never)
- **Anomalies** — unusual repetition, caps, punctuation density
- **ML patterns** — keyword density, sentiment divergence (optional, `include_ml: true`)

Example request through the proxy:

```sh
curl http://localhost:3000/api/backend/api/audit \
  -X POST -H 'Content-Type: application/json' \
  -d '{"content": "Everyone knows this is obviously true.", "include_ml": false}'
```

## Legal

Full legal stack in `docs/legal/` — privacy, terms, cookies, compliance roadmap.
GDPR / UK GDPR / Swiss-style rights language. B2C-first, no minors, no targeted advertising.
