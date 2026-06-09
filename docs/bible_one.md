# bible_one — Frontend Architecture Doctrine

> Recovered from CLAUDE.md, OPTIC-ABOUT.html, and optichyperdoc.rtf
> Original RTF: 1,284 bytes · Agent-built artifact · June 2026

## Architecture Overview

Monorepo with two runtimes:

```
/               ← Next.js 15 frontend (marketing, auth, proxy)
backend/        ← Python ctxorg server (audit engine, workspace, file org)
```

## Frontend Shell (Next.js 15)

**Marketing (public):**
- `app/page.tsx` — landing page, section order in file matches narrative flow
- All copy lives in `data/*.ts` — edit there, not in components
- Brand images in `assets/optic/` (cinematic, generated, zine, logos)
- Marketing photo set in `public/marketing/`

**Auth (local-first):**
- `app/login/`, `app/signup/` → `app/api/auth/login/`, `app/api/auth/signup/`
- Users stored as salted SHA-256 hashes in `.optic/users.json` (gitignored, auto-created)
- Session: httpOnly cookie `optic_session` = user ID, 30-day expiry

**App shell:**
- `app/app/page.tsx` — signal audit UI, calls backend via proxy
- `app/api/backend/[...path]/route.ts` — catch-all proxy to Python backend (strips `/api/backend` prefix, forwards body + headers)

## The SPA Core: app.js

The main application lives in `backend/src/ctxorg/static/app.js` — a vanilla JavaScript SPA:
- Currently 11,732 lines (expanded from 9,140 with V1 wiring)
- 8 dashboard modes
- 198 inference claims
- 42 repair actions
- 33 signal detectors
- V1 API wiring for all intelligence operations

## Design Tokens

In `app/globals.css`: `--color-cream`, `--color-ink`, `--color-muted`, `--color-border`, `--color-section-dark`.
Use `var(--color-*)` or `[var(--color-*)]` in Tailwind.

## Fonts

- `lib/fonts.ts` — Playfair Display (`font-editorial`) + DM Sans (`font-sans`)

## Backend Integration

- Frontend proxy: `/api/backend/*` → Python backend on port 3003
- Python backend serves `backend/src/ctxorg/static/` as static files
- 57+ HTTP routes in `server.py` (expanded for V1)
- SQLite 12-table database at `.optic/v1.db`
- Signal Engine v1: 9 Python modules (graph, lenses, parsers, inference, resolver, scrapers, contradiction)

## Route Dispatch

ctxorg route dispatch is a flat `if path == ...` chain in `server.py`:
- GET routes in `route()` → catch-all at end
- POST routes in `post()` → catch-all at end
- New routes go immediately before the `/api/` catch-all

## Environment

```
NEXT_PUBLIC_AUDIT_FORM_URL=/login        # CTA destination
OPTIC_BACKEND_URL=http://127.0.0.1:3003  # proxy target for /api/backend/*
```

Both in `.env.local` (gitignored). Fallbacks: `https://app.tryoptic.app` and `http://127.0.0.1:3003`.

## V1 Frontend Requirements

From optichyperdoc §20 — Required screens wired into the SPA:
- Onboarding (8-step state machine)
- Dashboard/Home (state-aware CTA)
- Sources and Consent (approval/revocation)
- Audience Selection (9 lenses from V1 package)
- Audit Progress (14-stage pipeline visible)
- Inference Cards with Evidence Drawers
- Contradictions (5 detection types)
- Risks/Exposures
- Repair Queue (filterable, status-tracked)
- Report View + History (persisted snapshots)
- Graph/Topology (V1 overlay on workstream graph)
- Iris Chat (audit-aware, structured context)
- Settings (model, data, connectors)
- Export Center (JSON + Markdown)

## Key Constraints

- The old `src/` Node server and `optic.html` / `optic-investors.html` at root are legacy static files — not served by Next.js
- `next.config.js` has `eslint.ignoreDuringBuilds: true`
- `.optic/`, `backend/.ctxorg/`, and `backend/config.json` are gitignored
- Never commit real user or scan data

## Commands

```sh
# Frontend
npm run dev       # localhost:3000
npm run build
npm run lint

# Backend
cd backend
cp config.example.json config.json
python3 -m src.ctxorg serve --cfg config.json --host 127.0.0.1 --port 3003
```
