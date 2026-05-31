# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Structure

Monorepo with two runtimes:

```
/               ← Next.js 15 frontend (web, auth, proxy)
backend/        ← Python ctxorg server (audit engine, workspace, file org)
```

## Commands

**Frontend (root):**
```sh
npm run dev       # localhost:3000
npm run build
npm run lint
```

**Backend:**
```sh
cd backend
cp config.example.json config.json   # edit paths for your machine
python3 -m src.ctxorg serve --cfg config.json --host 127.0.0.1 --port 3003
```

## Environment

```
NEXT_PUBLIC_AUDIT_FORM_URL=/login        # CTA destination across all nav/hero/cta components
OPTIC_BACKEND_URL=http://127.0.0.1:3003  # proxy target for /api/backend/* routes
```

Both live in `.env.local` (gitignored). The frontend falls back to `https://app.tryoptic.app` and `http://127.0.0.1:3003` respectively if unset.

## Frontend Architecture

**Marketing (public):**
- `app/page.tsx` — landing page, section order in file matches narrative flow
- All copy lives in `data/*.ts` — edit there, not in components
- `assets/optic/` — brand images (`cinematic/`, `generated/`, `zine/`, `logos/`)
- `public/marketing/` — newer marketing photo set

**Auth (local-first):**
- `app/login/`, `app/signup/` → `app/api/auth/login/`, `app/api/auth/signup/`
- Users stored as salted SHA-256 hashes in `.optic/users.json` (gitignored, auto-created)
- Session: httpOnly cookie `optic_session` = user ID, 30-day expiry

**App shell:**
- `app/app/page.tsx` — signal audit UI, calls backend via proxy
- `app/api/backend/[...path]/route.ts` — catch-all proxy to Python backend (strips `/api/backend` prefix, forwards body + headers)

**Design tokens** in `app/globals.css`: `--color-cream`, `--color-ink`, `--color-muted`, `--color-border`, `--color-section-dark`. Use `var(--color-*)` or `[var(--color-*)]` in Tailwind.

**Fonts:** `lib/fonts.ts` — Playfair Display (`font-editorial`) + DM Sans (`font-sans`).

## Backend Architecture (`backend/`)

Two Python packages co-located in `backend/src/`:

- `ctxorg/` — main HTTP server (`ThreadingHTTPServer`). Entry: `python3 -m src.ctxorg serve`
- `optic/` — signal detection engine (imported by ctxorg at startup via `sys.path`)

**ctxorg route dispatch** is a flat `if path == ...` chain in `server.py`:
- GET routes in `route()` → catch-all at end
- POST routes in `post()` → catch-all at end
- Add new routes immediately before the `if path.startswith("/api/"): send_err(...not_found...)` catch-all line

**Audit routes** (added to ctxorg, powered by `optic/signal/`):
- `POST /api/audit` — single signal audit
- `POST /api/audit/ml` — ML-only detection
- `POST /api/audit/batch` — batch audit
- `GET /api/audit/history` — in-memory session history

**Config:** `config.json` (gitignored). Copy from `config.example.json` and set `home`, `target`, `state_dir`, `sources` to your local paths. State persists in the path set by `state_dir`.

## Key constraints
- The old `src/` Node server and `optic.html` / `optic-investors.html` at root are legacy static files — not served by Next.js.
- `next.config.js` has `eslint.ignoreDuringBuilds: true`.
- `.optic/`, `backend/.ctxorg/`, and `backend/config.json` are gitignored — never commit real user or scan data.
