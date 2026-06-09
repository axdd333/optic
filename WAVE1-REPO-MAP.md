# Optic V1 — Wave 1 Repo Terrain Map

**Generated:** 2026-06-06  
**Repository:** `/Users/ahmedm/Developer/Projects/optic/`  
**Purpose:** Map every file, route, data flow, and integration point before merging the two surfaces (JS SPA frontend + V1 backend API) into one product.

---

## 1. Repo Topology — Three Runtimes, One Product Surface

```
/                           Next.js 15 marketing site + auth proxy (:3000)
├── app/                    App Router pages (marketing, login, signup, app shell)
├── app/api/backend/[...path]/route.ts   Proxy → Python backend
├── data/*.ts               Marketing copy constants
├── assets/optic/           Brand images
├── public/marketing/       Marketing photos
└── .env.local              NEXT_PUBLIC_AUDIT_FORM_URL, OPTIC_BACKEND_URL

backend/                    Python backend
├── src/ctxorg/             Original stdlib HTTPServer (:8765 default)
│   ├── server.py           8112 lines — ALL legacy API routes (REAL implementations)
│   ├── workstreams.py      Workstream clustering (real computation)
│   ├── scan.py             Filesystem scanner
│   ├── db.py               SQLite helpers for ctxorg scan database
│   ├── ollama.py           Gemma 4 via Ollama LLM integration
│   ├── ingest.py, embed.py, infer.py, latent.py, graph.py, chat.py
│   └── static/             Vanilla JS SPA (THE FRONTEND)
│       ├── index.html      536 lines — SPA shell, leftnav, glass UI
│       ├── app.js          8218 lines — All mode classes, rendering, API calls
│       └── app.css         1400+ lines — Single stylesheet
│
├── src/optic/              Signal detection engine (deprecated by V1)
│   └── signal/             auditor.py, detectors.py, ml_detector.py, models.py
│
└── src/optic/v1/           ** V1 INTELLIGENCE LAYER (what this report focuses on) **
    ├── server.py            1531 lines — FastAPI server on :3003
    ├── models.py            330 lines — Canonical data classes + enums
    ├── lenses.py            327 lines — 8 audience lens configurations
    ├── contradiction.py     210 lines — Contradiction detection engine
    ├── inference.py         296 lines — Inference card generator
    ├── parsers.py           417 lines — 17 format parsers
    ├── resolver.py          385 lines — Entity extraction + linking
    ├── graph.py             492 lines — SQLite evidence graph
    ├── scrapers.py          399 lines — URL/API scraping providers
    ├── iris_audit.py        176 lines — Conversational audit (LLM or fallback)
    ├── __init__.py          (empty)
    └── static/
        ├── onboarding.html  Onboarding wizard page
        └── dashboard.html   Dashboard page
```

---

## 2. The Frontend Surface — `backend/src/ctxorg/static/app.js` (8218 lines)

### Architecture
- **Vanilla JS SPA** — No React, no build tools. Uses D3.js, Three.js, and marked.js from CDN.
- **Mode Manager** pattern — `ModeManager` class switches between 10 mode objects, each with `mount(container)` / `unmount()` lifecycle.
- **State is global** — `const state = { ... }` object at line 56. All modes read/write it.
- **API calls are thin** — `getJson(url)` and `postJson(url, data)` helpers (lines 7643-7659), plain `fetch`.

### Modes (Left Navigation)
```
workstreams    Home (workstream cards, right panel "digital self")
topology       Map (canvas-based 2D/3D graph view)
timeline       Timeline (canvas)
universe       Universe (Three.js 3D globe)
iris           Iris (LLM chat console)
vault          Vault (duplicates, old downloads, largest files)
audiences      Audiences (audience cards + comparison table)
simulations    Simulations (scenario builder, evaluate/save/compare)
exports        Exports (PDF/JSON/CSV report export config)
onboard        Scan (initial setup, scan folders)
```

### What Each Mode Calls (API Surface Expected by JS)

| Mode | API Calls | Data Sources |
|---|---|---|
| **Home** | `GET /api/workstreams`, `GET /api/home`, `GET /api/audiences` | `state.workstreams`, `state.homeData`, `state.audiences` |
| **Map** | Reads `state.graph` (loaded at boot via `GET /api/graph`) | `state.nodes`, `state.links`, `state.nodeById` |
| **Timeline** | Reads `state.graph` nodes/sorted by mtime | Same as Map |
| **Universe** | Reads `state.graph` nodes for Three.js particle system | Same |
| **Iris** | `POST /api/iris` (streaming, chunked SSE) | Direct streaming |
| **Vault** | `GET /api/analyze?kind=duplicates`, `...kind=old_downloads`, `...kind=largest` | Mock data from V1 server |
| **Audiences** | `GET /api/audiences`, then `openAudienceModal()` calls `GET /api/simulate/{audId}` | `state.audiences` |
| **Simulations** | `POST /api/simulations/evaluate`, `POST /api/simulations/save`, `POST /api/simulations/compare` | `state.simulations` |
| **Exports** | `GET /api/exports/history`, `POST /api/exports`, `GET /api/settings` | `state.settings` |
| **Settings** (overlay) | `GET /api/account`, `POST /api/signup`, `POST /api/signout`, `GET /api/health`, many integration/workspace routes | Multiple endpoints |

### Hardcoded Fallback in JS
```javascript
// line 6417 — defaultAudiences() returns hardcoded 4-audience array if API fails
function defaultAudiences() { return [{id:"recruiter",score:80}, ...]; }
```

### Key JS → API Mismatches (Routes JS Calls That Don't Exist in V1 Server)
1. `POST /api/iris` (streaming) — V1 server has `POST /api/v1/iris/ask` (JSON response, not streaming)
2. `GET /api/simulate/{id}` — **NOT IN V1 SERVER** — JS calls this from audience modal
3. `POST /api/simulations/evaluate` — **NOT IN V1 SERVER**
4. `POST /api/simulations/save` — **NOT IN V1 SERVER**
5. `POST /api/simulations/compare` — **NOT IN V1 SERVER**
6. `GET /api/exports/history` — **NOT IN V1 SERVER** (in ctxorg server but mocked)
7. `GET /api/account` — **NOT IN V1 SERVER** (in ctxorg server)
8. `POST /api/signup` — **NOT IN V1 SERVER** (uses `/api/v1/auth/signup` instead)

---

## 3. The V1 Backend API — `backend/src/optic/v1/server.py` (1531 lines)

### Server Identity
- **FastAPI** on port `:3003` (default, configurable)
- Serves the SPA static files from `backend/src/ctxorg/static/`
- Mounts `/static` directory, serves `index.html` at `/`, `/app.js`, `/app.css`
- Also serves `/onboarding` and `/dashboard` from `backend/src/optic/v1/static/`
- **BUG:** `dashboard_page` route handler is defined twice (lines 82-86) — identical duplicate

### Route Inventory

#### Legacy Mock Routes (serve the SPA — ALL HARDCODED)
| Route | Method | Returns | Status |
|---|---|---|---|
| `/api/runs` | GET | `{"runs": ["20260606-fast-mock"]}` | HARDCODED |
| `/api/workstreams` | GET | `_fast_mock_ws()` — 6 hardcoded workstream clusters | HARDCODED |
| `/api/home` | GET | `_mock_home_payload()` — hardcoded stats | HARDCODED |
| `/api/graph` | GET | `_mock_graph_payload()` — hardcoded nodes+edges | HARDCODED |
| `/api/status` | GET | Hardcoded ready/scanning status | HARDCODED |
| `/api/analyze` | GET | Hardcoded duplicates/old_downloads/largest | HARDCODED |
| `/api/report` | GET | Hardcoded ctxorg report | HARDCODED |
| `/api/simulations` | GET | Hardcoded 3-audience scores | HARDCODED |
| `/api/scan` | POST | Returns `"scanning"` mock | HARDCODED |
| `/api/infer` | GET | Returns empty nodes | HARDCODED |
| `/api/audiences` | GET | Hardcoded 4-audience array | HARDCODED |
| `/api/settings` | GET | Hardcoded ollama config | HARDCODED |
| `/api/rename` | POST | Returns `{"ok": true}` | HARDCODED |
| `/api/embed/run` | POST | Returns `"started"` | HARDCODED |
| `/api/health` | GET | Returns ollama health | HARDCODED |

#### Real V1 API Routes (persisted to `backend/.optic/v1.db`)

##### Auth + Onboarding (token-based, no passwords)
| Route | Method | What it does |
|---|---|---|
| `/api/v1/auth/signup` | POST | Create user or return existing token |
| `/api/v1/auth/login` | POST | Return token for existing user |
| `/api/v1/onboarding` | GET | Get onboarding state (step, audit_mode, available lenses) |
| `/api/v1/onboarding/step` | POST | Advance to next onboarding step |

##### Sources + Import (real parsers)
| Route | Method | What it does |
|---|---|---|
| `/api/v1/sources` | GET | List user's sources |
| `/api/v1/sources` | POST | Add a source (URL, handle, or label) |
| `/api/v1/sources/{id}/consent` | POST | Create consent receipt, mark source ready |
| `/api/v1/sources/import` | POST | Upload files or URLs → parse with 17-format parser registry → save artifacts |

##### Audit Pipeline (THE CORE)
| Route | Method | What it does |
|---|---|---|
| `/api/v1/audit/{mode}` | GET | Run FULL 14-stage audit pipeline: load workstreams → signals → claims per lens → contradictions → risks → repairs → report snapshot |
| `/api/v1/claims` | GET | List claims (top 50 by severity) |
| `/api/v1/contradictions` | GET | List contradictions |
| `/api/v1/risks` | GET | List risks |
| `/api/v1/repairs` | GET | List repairs (sorted by priority = impact×urgency×reversibility/effort) |
| `/api/v1/repairs/{id}/complete` | POST | Mark repair as completed |

##### Intelligence Layer (graph, entities, scrapers, iris)
| Route | Method | What it does |
|---|---|---|
| `/api/v1/graph/evidence` | GET | Build SQLite evidence graph from user's sources+artifacts |
| `/api/v1/entities` | GET | Extract + resolve entities from artifacts |
| `/api/v1/scrapers/status` | GET | List available scraper providers + UI states |
| `/api/v1/iris/ask` | POST | Answer audit question (tries Ollama LLM, falls back to deterministic JSON summary) |
| `/api/v1/settings` | GET/POST | Get or update user settings (JSON blob) |
| `/api/v1/report` | GET | Generate audit report summary |
| `/api/v1/export/{format}` | GET | Export report as JSON, Markdown, or PDF |

##### Health
| Route | Method | What it does |
|---|---|---|
| `/api/v1/health` | GET | DB stats: users, sources, active lenses, module list |
| `/api/v1/status` | GET | Backend status: claims, risks, repairs, recent claims, repair queue |

### Data Flow in the V1 Audit Pipeline (GET /api/v1/audit/{mode})
```
1. _load_ctxorg_workstreams()     → Load from ctxorg scan DB (.ctxorg/state/ctx.db)
                                   → Falls back to _fast_mock_ws() if DB unavailable
2. _workstream_to_signals()       → Each workstream → 1-3 Signal objects
                                   → category=frequent_topic|project_velocity|fragmentation
3. InferenceCardGenerator         → For EACH of 8 audience lenses in AUDIENCE_LENSES:
     for each signal:
       generate_claims()           → InferenceClaim with evidence_counts, counterarguments
4. ContradictionEngine.run_full() → Find: title mismatches, timeline gaps, stale context,
                                   → profile mismatches, claim oppositions
5. Hardcoded risks                → 3 RiskFlag objects (stale, fragmentation, missing proof)
6. _generate_repairs()            → From contradictions + high-severity claims + 3 generic repairs
7. Report snapshot                → Store in reports table, return summary
```

---

## 4. V1 Module Breakdown

### `models.py` (330 lines) — Canonical Data Model
- **14 enums:** AuditMode (6 values), Severity (4), ConfidenceBand (3), RiskCategory (25!), SourceType (19), SourceStatus (6), RepairStatus (5)
- **15 dataclasses:** User, ConsentReceipt, Source, Artifact, ParsedSpan, Entity, Signal, InferenceClaim, EvidenceLink, Contradiction, RiskFlag, RepairAction, AudienceLens, Report
- **Key invariants:** `not_a_verdict=True` on every claim. Repair priority = impact×urgency×reversibility/effort

### `lenses.py` (327 lines) — 8 Audience Lenses
Each lens has: priorities, evidence_preferences, common_false_positives, risk_sensitivity, repair_preferences, forbidden_outputs, confidence_rules.
- recruiter, investor, admissions, creator, stranger, customer, collaborator, ad_platform, future_agent

### `contradiction.py` (210 lines) — Contradiction Engine
5 detection methods:
- `find_job_title_mismatches()` — different titles across profiles
- `find_timeline_conflicts()` — gaps > 2 years between dated artifacts
- `find_stale_context()` — public artifacts older than 365 days
- `find_profile_mismatches()` — entities appearing as multiple types
- `find_claim_contradictions()` — claims with opposition markers

### `inference.py` (296 lines) — Inference Card Generator
- Takes signals + artifacts + audience lens → structured InferenceClaims
- Template-based claim text generation from signal categories
- Confidence band: HIGH (≥2× min evidence), MEDIUM (≥min), LOW otherwise
- Counterargument generation from weakening evidence or alt claims

### `parsers.py` (417 lines) — 17 Format Parsers
- FORMAT_MAP: .zip, .json, .csv, .html, .pdf, .docx, .txt/.md/.rst, .mbox, .eml, .ics/.ical, .vcf, .jpg/.png/.webp/.heic, .xml/.plist, .sqlite/.db
- MAGIC_BYTES detection for format sniffing
- ParserRegistry: detect_format(name, content) → parse → ParseResult(artifacts, errors, warnings)

### `resolver.py` (385 lines) — Entity Extraction + Linking
- Regex-based extraction: EMAIL_RE, URL_RE, HANDLE_RE, ORG_RE, PERSON_RE, PLATFORM_HANDLE_RE
- Union-Find for entity merging (same entity from multiple sources)
- False positive filtering: generic local parts, common name phrases
- Output: canonical Entity objects with aliases, confidence scores

### `graph.py` (492 lines) — SQLite Evidence Graph
- 32 allowed NODE_TYPES (user, account, handle, ... report_snapshot)
- 19 EDGE_TYPES (authored, owned, mentions, supports, weakens, contradicts, ...)
- EvidenceGraph class: add_node(), add_edge(), neighbors(), traversal helpers

### `scrapers.py` (399 lines) — URL/API Scraping
- ProviderUIState: status per scraper provider
- RateLimiter: per-minute rate limiting
- USER_AGENT = "OpticV1/0.1 local-self-audit", MAX_FETCH_BYTES = 2MB
- Used by server.py's `_fetch_url()` and `/api/v1/sources/import`

### `iris_audit.py` (176 lines) — Conversational Audit
- IrisAuditChat: gathers DB context (claims, contradictions, risks, repairs, sources)
- Tries ctxorg ollama for LLM response, falls back to deterministic JSON summary
- IRIS_PROMPT template: context injection, rule enforcement

---

## 5. The ctxorg Server — `backend/src/ctxorg/server.py` (8112 lines)

### What it is
The **original backend** using Python stdlib `ThreadingHTTPServer`. Real filesystem scanning, real workstream clustering, real Ollama-powered Iris chat. This is where all the routes the JS SPA really needs are actually implemented.

### Key Route Implementations (all REAL, not mocked)
- `GET /api/runs` — reads scan runs from state directory
- `GET /api/graph` — builds graph from scan data
- `GET /api/workstreams` — real workstream clustering (may trigger LLM naming)
- `GET /api/home` — real filesystem stats (file_count, total_size, signal_count)
- `GET /api/status` — real scan progress
- `POST /api/scan` — triggers filesystem scan
- `POST /api/iris` — **streaming** LLM chat via Ollama (chunked SSE)
- `GET /api/audiences` — computed audience scores (heuristic, not LLM)
- `GET /api/simulations` — simulation run results
- `GET /api/account` — auth state
- `GET /api/settings` — loaded from config
- `GET /api/analyze` — duplicates, old downloads, largest files
- `POST /api/rename` — rename files
- `POST /api/signup`, `POST /api/signout` — email-based auth
- Plus 30+ integration, workspace, billing, ops routes

### State Management
- Thread-locked caches: `_scan_state`, `_ws_cache`, `_home_jobs`, `_aud_cache`, `_audit_history`
- Persists scan data to `.ctxorg/state/ctx.db` (SQLite items table)
- Config loaded from `backend/config.json`

---

## 6. Integration Status — What's Connected vs Disconnected

### Connected ✓
| From | To | How |
|---|---|---|
| JS SPA Home mode | V1 server `GET /api/workstreams` | Works — but returns mock data |
| JS SPA Home mode | V1 server `GET /api/home` | Works — but returns mock data |
| JS SPA Map mode | V1 server `GET /api/graph` | Works — but returns mock data |
| JS SPA Audiences mode | V1 server `GET /api/audiences` | Works — but returns mock data |
| JS SPA Vault mode | V1 server `GET /api/analyze` | Works — but returns mock data |
| JS SPA Settings | V1 server `GET /api/settings` | Works — but returns mock data |
| V1 audit pipeline | ctxorg scan DB (`.ctxorg/state/ctx.db`) | Works — `_load_ctxorg_workstreams()` queries it directly |
| V1 server SPA serving | Static files | Works — serves index.html, app.js, app.css |

### Disconnected/Unimplemented ✗
| What | Status |
|---|---|
| `GET /api/simulate/{id}` | **MISSING** — JS calls it from audience modal; returns 404 on V1 server |
| `POST /api/simulations/evaluate` | **MISSING** — JS calls it from SimulationsMode |
| `POST /api/simulations/save` | **MISSING** |
| `POST /api/simulations/compare` | **MISSING** |
| `GET /api/exports/history` | **MISSING** |
| `POST /api/exports` | **MISSING** |
| `GET /api/account` | **MISSING** |
| `POST /api/signup` (legacy) | Uses `/api/v1/auth/signup` instead — different auth model |
| `POST /api/iris` (streaming) | V1 has `POST /api/v1/iris/ask` (JSON, not streaming) |

### Broken 🗴
| What | Details |
|---|---|
| Duplicate `dashboard_page` route | server.py lines 82-86: same route defined twice — FastAPI raises error on startup |
| `_row_to_claim()` | server.py line 1415-1416: `return row` — does NOT convert row to InferenceClaim, returns sqlite3.Row object directly. This means `run_full_audit()` in audit pipeline receives Row objects instead of proper InferenceClaim instances |
| `_fast_mock_ws()` hardcoded paths | Contains `/Users/ahmedm/OpticMock` paths — will break for other users |
| `_load_ctxorg_workstreams()` hardcoded paths | SQL query (lines 893-908) has hardcoded `/Users/ahmedm/Developer/...` path prefixes |
| No SPA→V1 API integration | The JS frontend makes ZERO calls to any `/api/v1/*` route |
| No auth in SPA | The JS SPA doesn't use tokens — it calls legacy routes directly. V1 endpoints require `token: str` query params |
| Ollama dependency | `iris_audit.py` tries to import ctxorg ollama (which may not be available when running standalone V1) |

### Hardcoded vs Real
| Component | Status |
|---|---|
| All legacy routes in V1 server | **100% hardcoded** — 6 mock workstreams, no filesystem access |
| V1 audit pipeline (`/api/v1/audit/{mode}`) | **Real** — reads ctxorg DB, generates real signals/claims/contradictions |
| V1 import pipeline (`/api/v1/sources/import`) | **Real** — parses actual files/URLs through parsers |
| V1 models + engines | **Real** — concrete logic, no stubs |
| ctxorg server routes | **Real** — all implemented, tested against real filesystem |

---

## 7. Data Storage

| Database | Location | Schema | Used By |
|---|---|---|---|
| V1 DB | `backend/.optic/v1.db` | users, sessions, sources, consent_receipts, artifacts, signals, claims, contradictions, risks, repairs, reports, onboarding | V1 FastAPI server |
| ctxorg scan DB | `.ctxorg/state/ctx.db` | items table (path, kind, size, ext, mtime) | ctxorg scanner, read by V1 audit pipeline |
| Next.js auth | `.optic/users.json` | Salted SHA-256 user hashes | Next.js frontend auth |

---

## 8. The Two Surfaces That Need to Become One

### Surface A: The JS Frontend (what users see)
- Lives in `backend/src/ctxorg/static/`
- Rich UI: 10 modes, canvas rendering, Three.js globe, streaming chat
- Expects legacy API routes from ctxorg server
- Makes ZERO V1 API calls
- Client-side state management, workstream filtering, audience simulations

### Surface B: The V1 Intelligence Layer (what the product IS)
- Lives in `backend/src/optic/v1/`
- Complete audit pipeline: sources→artifacts→signals→claims→contradictions→risks→repairs→report
- Sophisticated domain model: 8 audience lenses with priorities, risk sensitivity, forbidden outputs
- Token-based auth, consent receipts, 17 format parsers, entity resolution
- But returns mock data for the legacy routes the frontend actually calls

### The Gap
```
┌─────────────────────┐       calls legacy routes       ┌──────────────────────┐
│   JS SPA Frontend   │ ──────────────────────────────→ │  V1 FastAPI Server   │
│   (app.js 8218ln)   │                                 │  (server.py 1531ln)  │
│                     │  ← mock data                    │                      │
│  expects:           │                                 │  returns:            │
│  /api/workstreams   │                                 │  _fast_mock_ws()     │
│  /api/home          │                                 │  _mock_home_payload()│
│  /api/graph         │                                 │  _mock_graph_payload │
│  /api/audiences     │                                 │  hardcoded 4 items   │
│  /api/simulate/{id} │ ← 404 ── NOT IMPLEMENTED ───────│                      │
│  /api/iris (stream) │                                  │  /api/v1/iris/ask    │
└─────────────────────┘                                 └──────────────────────┘
                                                                    │
                                                          reads ctxorg scan DB
                                                                    │
                                                          ┌─────────▼──────────┐
                                                          │  V1 Intelligence   │
                                                          │  - models.py       │
                                                          │  - lenses.py       │
                                                          │  - contradiction.py│
                                                          │  - inference.py    │
                                                          │  - parsers.py      │
                                                          │  - resolver.py     │
                                                          │  (never called     │
                                                          │   by frontend!)    │
                                                          └───────────────────┘
```

---

## 9. Quick Reference Card

**To run everything:**
```bash
# V1 server (serves SPA + V1 API on :3003)
cd backend
python3 -m uvicorn src.optic.v1.server:app --host 127.0.0.1 --port 3003

# Original ctxorg server (:8765 — not needed if using V1)
python3 -m src.ctxorg serve --cfg config.json --host 127.0.0.1 --port 8765

# Next.js marketing site (:3000)
npm run dev
```

**To run an audit (V1):**
```bash
curl "http://127.0.0.1:3003/api/v1/auth/signup" -X POST -H "Content-Type: application/json" -d '{"email":"test@example.com"}'
# Use returned token:
curl "http://127.0.0.1:3003/api/v1/audit/general?token=YOUR_TOKEN"
```

**Key files to edit (by size/importance):**
1. `backend/src/optic/v1/server.py` (1531L) — add missing routes, wire real data to legacy routes
2. `backend/src/ctxorg/static/app.js` (8218L) — add V1 API calls, token management
3. `backend/src/optic/v1/models.py` (330L) — domain model (stable)
4. `backend/src/optic/v1/inference.py` (296L) — inference generation
5. `backend/src/ctxorg/static/app.css` (~1400L) — styling
