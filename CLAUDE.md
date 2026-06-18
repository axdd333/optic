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
- `app/app/profile/page.tsx` — persistent signal profile dashboard (Vana data)
- `app/api/backend/[...path]/route.ts` — catch-all proxy to Python backend (strips `/api/backend` prefix, forwards body + headers)

**Onboarding (Vana DataConnect):**
- `app/onboarding/page.tsx` — post-signup flow: intro → connect → audit → signal profile payoff. Signup redirects here. Primary path (hosted, tryoptic.app): customer drags DataConnect export JSONs into the dropzone; files are parsed client-side, batched under the serverless request cap, uploaded to `POST /api/vana/upload`. Desktop path: local exports auto-detected via `/api/vana/status` poll → one-click direct ingest.
- `components/vana/SignalProfile.tsx` — shared profile renderer (onboarding payoff + `/app/profile`)
- DataConnect (github.com/vana-com/data-connect) is the open-source desktop app customers use to export their platform data (ChatGPT, LinkedIn, Instagram, GitHub, …) to their own disk.

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

**Vana DataConnect routes** (powered by `optic/vana_ingest.py`; profiles keyed per user via `optic_session` cookie hash):
- `GET /api/vana/status` — discover local DataConnect export stores (desktop mode)
- `POST /api/vana/ingest` — desktop mode: scan local exports, normalize per-platform (conversations/memories/posts/bios audited; orders/history/playlists profiled), audit, persist. Body: `{roots?, include_ml?, max_items?}`
- `POST /api/vana/upload` — hosted mode (tryoptic.app): batched browser upload of export files into a per-user spool; `{session, files:[{name,data}]}` per batch, `{session, final:true}` triggers the audit. 8MB body cap (vs 64KB default); client batches at ~2.5MB and splits oversized conversation files
- `GET /api/vana/profile` — persisted per-user profile (`{state_dir}/vana_profile_{uid}.json`)

**Config:** `config.json` (gitignored). Copy from `config.example.json` and set `home`, `target`, `state_dir`, `sources` to your local paths. State persists in the path set by `state_dir`.

## Key constraints
- The old `src/` Node server and `optic.html` / `optic-investors.html` at root are legacy static files — not served by Next.js.
- `next.config.js` has `eslint.ignoreDuringBuilds: true`.
- `.optic/`, `backend/.ctxorg/`, and `backend/config.json` are gitignored — never commit real user or scan data.
