# Optic V1 — Wave 2 Frontend-to-V1 Endpoint Map

**Generated:** 2026-06-06
**Source:** WAVE1-REPO-MAP.md (Sections 2, 3, 6)
**Purpose:** Map each JS SPA mode to the V1 endpoint that should supply real data, replacing all hardcoded mocks.

---

## 1. Master Mapping Table

| # | JS Mode | Legacy Route(s) Called | V1 Endpoint That Should Supply Real Data | Status |
|---|---------|----------------------|------------------------------------------|--------|
| 1 | **Home** (workstreams) | `GET /api/workstreams` | `GET /api/v1/audit/{mode}` → extract workstreams from pipeline step 1 | Needs adapter |
| | | `GET /api/home` | `GET /api/v1/status` (claims/risks/repairs counts) | Needs adapter |
| | | `GET /api/audiences` | `GET /api/v1/claims` → aggregate by lens/severity | Needs adapter |
| 2 | **Map** (topology) | `GET /api/graph` | `GET /api/v1/graph/evidence` (SQLite evidence graph nodes+edges) | Direct match |
| 3 | **Timeline** | `GET /api/graph` (same as Map) | `GET /api/v1/graph/evidence` (nodes sorted by timestamp fields) | Direct match |
| 4 | **Universe** | `GET /api/graph` (same as Map) | `GET /api/v1/graph/evidence` (all nodes for 3D particle system) | Direct match |
| 5 | **Iris** | `POST /api/iris` (streaming SSE) | `POST /api/v1/iris/ask` (JSON response, NOT streaming) | Protocol mismatch |
| 6 | **Vault** | `GET /api/analyze?kind=duplicates` | **NO V1 EQUIVALENT** — filesystem analysis belongs to ctxorg, not V1 intelligence layer | Gap |
| | | `GET /api/analyze?kind=old_downloads` | Same as above | Gap |
| | | `GET /api/analyze?kind=largest` | Same as above | Gap |
| 7 | **Audiences** | `GET /api/audiences` | `GET /api/v1/audit/{mode}` → extract lens-scored claims per audience | Needs adapter |
| | | `GET /api/simulate/{audId}` | **NO V1 EQUIVALENT** — needs new route or adaptation | Gap |
| 8 | **Simulations** | `POST /api/simulations/evaluate` | **NO V1 EQUIVALENT** — needs new route | Gap |
| | | `POST /api/simulations/save` | **NO V1 EQUIVALENT** — needs new route | Gap |
| | | `POST /api/simulations/compare` | **NO V1 EQUIVALENT** — needs new route | Gap |
| 9 | **Exports** | `GET /api/exports/history` | **NO V1 EQUIVALENT** — needs new route tracking export history | Gap |
| | | `POST /api/exports` | `GET /api/v1/export/{format}` (JSON, Markdown, PDF) | Direct match (verb diff) |
| | | `GET /api/settings` | `GET /api/v1/settings` | Direct match |
| 10 | **Onboard** (Scan) | `POST /api/scan` | `POST /api/v1/sources/import` (upload files → parse → save artifacts) | Semantic match |
| | | (implicit setup) | `GET /api/v1/onboarding` + `POST /api/v1/onboarding/step` | Direct match |
| — | **Auth** (settings overlay) | `GET /api/account` | **NO V1 EQUIVALENT** — needs new route returning user profile | Gap |
| | | `POST /api/signup` | `POST /api/v1/auth/signup` (token-based, different model) | Protocol mismatch |
| | | `POST /api/signout` | **NO V1 EQUIVALENT** — V1 uses tokens, not sessions | Gap |
| | | `GET /api/health` | `GET /api/v1/health` (DB stats: users, sources, modules) | Direct match |

---

## 2. Detailed Mapping Per Mode

### 2.1 Home Mode (workstreams)

**What the JS expects:**
- `GET /api/workstreams` → array of workstream objects with id, name, signals, file_count
- `GET /api/home` → stats object: {file_count, total_size, signal_count, workstream_count}
- `GET /api/audiences` → array of 4 audience score objects

**V1 source of truth:**
```
GET /api/v1/audit/{mode}?token=...
  → Pipeline step 1: _load_ctxorg_workstreams() reads ctxorg scan DB
  → Returns full audit report with workstreams, signals, claims
```

**Recommended V1 adapter route:** `GET /api/v1/home`
- Calls `_load_ctxorg_workstreams()` standalone (not full audit pipeline)
- Aggregates signal counts, file counts from ctxorg DB
- Returns the shape JS expects: `{workstreams: [...], stats: {...}}`
- Falls back to `_fast_mock_ws()` only when ctxorg DB is unavailable (graceful degradation)

**Why not just run the full audit pipeline?** The full `GET /api/v1/audit/{mode}` runs 14 stages (signal detection → claims per lens → contradictions → risks → repairs → report). Home mode only needs workstream clustering + basic stats. Running the full pipeline on every Home load would be too slow and expensive (Ollama LLM calls for claim generation).

---

### 2.2 Map / Timeline / Universe Modes (graph)

**What the JS expects:**
- `GET /api/graph` → `{nodes: [...], links: [...]}`
- Nodes have: id, label, type, group, size, x, y (optional layout coords)
- Links have: source, target, type, value

**V1 source of truth:**
```
GET /api/v1/graph/evidence?token=...
  → EvidenceGraph class (graph.py, 492 lines)
  → SQLite-backed graph with 32 NODE_TYPES, 19 EDGE_TYPES
  → Real entities, artifacts, sources, claims, contradictions as nodes
```

**This is a DIRECT MATCH.** The V1 evidence graph produces exactly what the Map/Timeline/Universe modes render. The JS just needs the data in the shape it expects.

**Recommended V1 adapter route:** `GET /api/v1/graph/evidence` (already exists — just needs JS to call it)
- Map mode: uses all nodes + links for 2D/3D canvas view
- Timeline mode: filters graph nodes by timestamp fields, sorts by mtime
- Universe mode: maps all nodes to Three.js particle system

**Shape translation needed:**
- V1 nodes have: `{id, type, label, properties: {...}}`
- JS expects: `{id, label, type, group, size}`
- Adapter should map V1 node types to JS group categories and compute size from edge count

---

### 2.3 Iris Mode (chat)

**What the JS expects:**
- `POST /api/iris` with `{message: "...", context: {...}}`
- **Streaming SSE response** (chunked text via EventSource)
- Fallback: `getJson()` for non-streaming JSON response

**V1 source of truth:**
```
POST /api/v1/iris/ask?token=...
  → IrisAuditChat (iris_audit.py, 176 lines)
  → Gathers DB context (claims, contradictions, risks, repairs, sources)
  → Tries Ollama LLM via ctxorg's ollama module
  → Falls back to deterministic JSON summary
  → Returns: {"answer": "...", "sources": [...], "mode": "llm"|"fallback"}
```

**Protocol mismatch:** JS expects streaming SSE; V1 returns single JSON response.

**Recommended approach:**
1. **Option A (quick):** Modify JS Iris mode to accept non-streaming JSON from `/api/v1/iris/ask`. The JS fallback path already handles this (`getJson()` instead of streaming fetch).
2. **Option B (full):** Create new streaming endpoint `POST /api/v1/iris/stream` that wraps `IrisAuditChat` with SSE chunked output. Requires ctxorg's Ollama to be available for streaming.
3. **Option C (hybrid):** Add SSE wrapper to existing `/api/v1/iris/ask` using FastAPI's `StreamingResponse`. This is the cleanest approach — same endpoint, streaming when Ollama is available, fallback JSON otherwise.

---

### 2.4 Vault Mode (filesystem analysis)

**What the JS expects:**
- `GET /api/analyze?kind=duplicates` → list of duplicate files by hash
- `GET /api/analyze?kind=old_downloads` → files last modified > N days ago
- `GET /api/analyze?kind=largest` → largest files by size

**V1 source of truth:** **NONE.** The V1 intelligence layer operates on sources, artifacts, and claims — not on raw filesystem metadata. These features belong to the ctxorg server, which has direct filesystem access and a scanner (`scan.py`).

**Gap analysis:** This is a fundamental architecture gap. V1 is designed for evidence-based intelligence (parsed artifacts → signals → claims), not filesystem housekeeping. The vault features (duplicate detection, disk cleanup) are ctxorg's domain.

**Recommended approach:**
1. Keep ctxorg server running alongside V1 for filesystem operations
2. Proxy `/api/analyze` through V1 to ctxorg (or call ctxorg directly)
3. Long-term: port ctxorg's scanner logic into a V1 module (`vault.py`) that reads from ctxorg scan DB (`items` table with path, size, ext, mtime)

**Shortest path:** Add 3 new routes to V1 server that query ctxorg's scan DB directly:
```
GET /api/v1/vault/duplicates  → SELECT path, size FROM items GROUP BY size, kind HAVING COUNT(*) > 1
GET /api/v1/vault/stale       → SELECT path, mtime FROM items WHERE mtime < datetime('now','-365 days')
GET /api/v1/vault/largest     → SELECT path, size FROM items ORDER BY size DESC LIMIT 20
```

---

### 2.5 Audiences Mode

**What the JS expects:**
- `GET /api/audiences` → array of 4 audience objects: `[{id: "recruiter", score: 80, ...}, ...]`
- `GET /api/simulate/{audId}` → detailed audience report with claims, risks, recommendations

**V1 source of truth:**
- **8 audience lenses** defined in `lenses.py` (327 lines): recruiter, investor, admissions, creator, stranger, customer, collaborator, ad_platform, future_agent
- Each lens has: priorities, evidence_preferences, common_false_positives, risk_sensitivity, repair_preferences, forbidden_outputs, confidence_rules
- `GET /api/v1/audit/{mode}` generates claims through ALL 8 lenses via `InferenceCardGenerator`
- `GET /api/v1/claims` returns top 50 claims by severity
- `GET /api/v1/risks` returns risk flags (stale, fragmentation, missing proof)

**Recommended V1 adapter route:** `GET /api/v1/audiences`
- Runs a lightweight audit that generates claims per lens
- Computes audience scores: aggregate claim severity × confidence per lens
- Returns the 8-audience array (JS currently expects 4 — needs JS update)

**For `GET /api/simulate/{audId}` (MISSING):**
- This is the audience detail/modal view
- **Recommended new route:** `GET /api/v1/audiences/{lens_id}`
  - Returns all claims filtered to that lens
  - Sorted by severity, with evidence links and counterarguments
  - Includes risk flags relevant to that audience

**JS SPA change needed:** `defaultAudiences()` (line 6417) returns hardcoded 4 audiences. Update to 8 (or keep 4 as default subset and add "show all 8" toggle).

---

### 2.6 Simulations Mode

**What the JS expects:**
- `POST /api/simulations/evaluate` → run a scenario evaluation
- `POST /api/simulations/save` → save a scenario config
- `POST /api/simulations/compare` → compare two saved scenarios

**V1 source of truth:** **NONE.** The V1 server has no simulation engine. Simulations mode in the JS is a scenario builder where users tweak parameters and see how audience scores change.

**Gap analysis:** This is a product feature that exists only in the frontend. The V1 audit pipeline (`GET /api/v1/audit/{mode}`) supports different `mode` values (6 AuditMode enums in models.py), but there's no "simulation" mode with parameterized inputs.

**Recommended new V1 routes:**
```
POST /api/v1/simulations/evaluate  → Accept scenario config (selected lenses, parameter overrides)
                                     → Run audit with those parameters
                                     → Return scored results per lens

POST /api/v1/simulations/save      → Store scenario config in V1 DB (new 'simulations' table)
                                     → Return simulation ID

POST /api/v1/simulations/compare   → Accept two simulation IDs
                                     → Run both, diff the results
                                     → Return comparison report

GET  /api/v1/simulations           → List saved simulations
GET  /api/v1/simulations/{id}      → Get saved simulation config + results
```

**Data model needed:** New `Simulation` class in `models.py`:
- id, user_id, name, config (lens selection, parameter overrides), results (JSON), created_at

---

### 2.7 Exports Mode

**What the JS expects:**
- `GET /api/exports/history` → list of past exports
- `POST /api/exports` → trigger a new export (format, scope)
- `GET /api/settings` → user settings for export defaults

**V1 source of truth:**
```
GET /api/v1/export/{format}?token=...   → Export as JSON, Markdown, or PDF
GET /api/v1/report?token=...            → Audit report summary
GET /api/v1/settings?token=...          → User settings (JSON blob)
```

**Direct match for export + settings.** Missing: export history tracking.

**Recommended new V1 route:**
```
GET /api/v1/exports/history  → SELECT * FROM exports WHERE user_id = ? ORDER BY created_at DESC
```
This requires adding an `exports` table to the V1 DB schema (track format, scope, created_at).

**JS adapter needed:** Change `POST /api/exports` to call `GET /api/v1/export/{format}` with the requested format. The JS currently POSTs — simple frontend change.

---

### 2.8 Onboard Mode (Scan)

**What the JS expects:**
- `POST /api/scan` → trigger filesystem scan, return "scanning" status
- Implicit: folder selection, scan progress, onboarding steps

**V1 source of truth:**
```
POST /api/v1/sources/import       → Upload files/URLs → parse with 17 parsers → save artifacts
GET  /api/v1/onboarding           → Get onboarding state (step, audit_mode, available lenses)
POST /api/v1/onboarding/step      → Advance to next onboarding step
GET  /api/v1/sources              → List user's sources
POST /api/v1/sources              → Add source (URL, handle, or label)
```

**Semantic match.** The V1 onboarding + sources/import flow replaces the old ctxorg scan workflow. Key differences:
- Old: scan local folders → workstreams computed from filesystem
- New: add sources → import files/URLs → parse → artifacts → workstreams from signals

**Recommended approach:**
- Replace JS Onboard mode entirely with V1 onboarding wizard (`/onboarding` page from `backend/src/optic/v1/static/onboarding.html`)
- Or: update JS Onboard mode to call V1 onboarding + sources/import routes

---

### 2.9 Auth (Settings Overlay)

**What the JS expects:**
- `GET /api/account` → user profile
- `POST /api/signup` → create account (email-based)
- `POST /api/signout` → end session

**V1 source of truth:**
```
POST /api/v1/auth/signup   → Create user or return existing token (token-based, no passwords)
POST /api/v1/auth/login    → Return token for existing user
```
Missing: account profile route, session-based signout.

**Protocol mismatch:** V1 uses token-based auth (`?token=...` query param on every request). The JS SPA has no token management — it assumes session-based auth from the ctxorg server.

**Recommended approach:**
1. Add `GET /api/v1/account?token=...` → return user profile (email, created_at, onboarding_state)
2. Replace JS signup/login to use V1 token-based flow
3. Store token in `localStorage` and attach to all V1 API calls
4. For signout: client-side only (delete token from localStorage)

**JS changes needed (app.js):**
- Add token storage: `state.token = localStorage.getItem('optic_token')`
- Add auth header/param to all `getJson()` and `postJson()` calls
- Update Settings overlay to use V1 auth routes

---

## 3. Gap Summary

### Direct Matches (no new V1 code needed)
| Legacy Route | V1 Route | Action |
|---|---|---|
| `GET /api/graph` | `GET /api/v1/graph/evidence` | Update JS to call V1 route |
| `POST /api/exports` | `GET /api/v1/export/{format}` | Update JS (verb change) |
| `GET /api/settings` | `GET /api/v1/settings` | Update JS to call V1 route |
| `GET /api/health` | `GET /api/v1/health` | Update JS to call V1 route |
| `POST /api/signup` | `POST /api/v1/auth/signup` | Update JS (token-based, different body) |

### Needs V1 Adapter Route (thin wrapper over existing V1 logic)
| Legacy Route | Proposed V1 Adapter | What It Wraps |
|---|---|---|
| `GET /api/workstreams` | `GET /api/v1/home/workstreams` | `_load_ctxorg_workstreams()` standalone |
| `GET /api/home` | `GET /api/v1/home/stats` | Aggregated counts from DB + workstreams |
| `GET /api/audiences` | `GET /api/v1/audiences` | Lightweight audit → lens-scored claims |
| `POST /api/iris` | `POST /api/v1/iris/ask` (or new `/stream`) | `IrisAuditChat` with optional SSE wrapper |

### Needs New V1 Route (feature doesn't exist in V1 yet)
| Legacy Route | Proposed New V1 Route | Effort |
|---|---|---|
| `GET /api/simulate/{audId}` | `GET /api/v1/audiences/{lens_id}` | Medium — filter claims by lens |
| `POST /api/simulations/evaluate` | `POST /api/v1/simulations/evaluate` | High — new simulation engine |
| `POST /api/simulations/save` | `POST /api/v1/simulations/save` | Medium — DB table + storage |
| `POST /api/simulations/compare` | `POST /api/v1/simulations/compare` | High — diff engine |
| `GET /api/exports/history` | `GET /api/v1/exports/history` | Low — DB table + query |
| `GET /api/account` | `GET /api/v1/account` | Low — user profile endpoint |

### Needs ctxorg or New V1 Module (outside V1 intelligence scope)
| Legacy Route | Solution | Effort |
|---|---|---|
| `GET /api/analyze?kind=duplicates` | Query ctxorg scan DB → `/api/v1/vault/duplicates` | Medium |
| `GET /api/analyze?kind=old_downloads` | Query ctxorg scan DB → `/api/v1/vault/stale` | Medium |
| `GET /api/analyze?kind=largest` | Query ctxorg scan DB → `/api/v1/vault/largest` | Medium |

---

## 4. Migration Priority

### Wave 2A — Critical Path (unblock the SPA)
1. **Graph endpoints** (`/api/v1/graph/evidence`) — Powers Map, Timeline, Universe (3 modes)
2. **Home adapter** (`/api/v1/home/*`) — Powers Home mode (the landing page)
3. **Auth migration** — Token management in JS SPA (required for ALL V1 calls)
4. **Iris adapter** — Streaming or JSON fallback

### Wave 2B — Complete Coverage
5. **Audiences adapter** + `/api/v1/audiences/{lens_id}`
6. **Export history** tracking
7. **Vault routes** (query ctxorg scan DB)

### Wave 2C — New Features
8. **Simulations engine** (evaluate, save, compare)
9. **Account profile** endpoint
10. **Onboarding** integration with V1 wizard

---

## 5. JS SPA Changes Required (Summary)

| File | Change | Lines Affected |
|---|---|---|
| `app.js` | Add `state.token` from localStorage | ~line 56 |
| `app.js` | Update `getJson()` to append `?token=` | ~line 7643 |
| `app.js` | Update `postJson()` to include token in body | ~line 7650 |
| `app.js` | Change Home mode API calls to V1 routes | Mode class mount() |
| `app.js` | Change Map/Timeline/Universe to call `/api/v1/graph/evidence` | Mode class mount() |
| `app.js` | Change Iris mode to `/api/v1/iris/ask` (or new stream endpoint) | IrisMode class |
| `app.js` | Change Audiences mode to `/api/v1/audiences` | AudiencesMode class |
| `app.js` | Change Exports mode to `/api/v1/export/{format}` | ExportsMode class |
| `app.js` | Change Settings overlay auth to V1 token flow | Settings overlay |
| `app.js` | Update `defaultAudiences()` from 4 to 8 lenses | ~line 6417 |
| `app.js` | Change Vault mode to `/api/v1/vault/*` (once built) | VaultMode class |
| `app.js` | Change Onboard mode to V1 onboarding flow | OnboardMode class |

---

## 6. Quick Reference: V1 Endpoint Directory

```
/api/v1/auth/signup          POST   → Create user, return token
/api/v1/auth/login           POST   → Return token for existing user
/api/v1/onboarding           GET    → Onboarding state
/api/v1/onboarding/step      POST   → Advance onboarding step
/api/v1/sources              GET    → List sources
/api/v1/sources              POST   → Add source
/api/v1/sources/{id}/consent POST   → Create consent receipt
/api/v1/sources/import       POST   → Upload files/URLs, parse, save
/api/v1/audit/{mode}         GET    → Full 14-stage audit pipeline
/api/v1/claims               GET    → Top 50 claims by severity
/api/v1/contradictions       GET    → All detected contradictions
/api/v1/risks                GET    → Risk flags
/api/v1/repairs              GET    → Repairs sorted by priority
/api/v1/repairs/{id}/complete POST  → Mark repair done
/api/v1/graph/evidence       GET    → SQLite evidence graph ← MAP/TIMELINE/UNIVERSE
/api/v1/entities             GET    → Extracted entities
/api/v1/scrapers/status      GET    → Scraper provider states
/api/v1/iris/ask             POST   → Audit Q&A ← IRIS
/api/v1/settings             GET    → User settings ← SETTINGS
/api/v1/settings             POST   → Update settings
/api/v1/report               GET    → Audit report summary
/api/v1/export/{format}      GET    → Export (json/md/pdf) ← EXPORTS
/api/v1/health               GET    → DB health stats
/api/v1/status               GET    → Backend status (claims, risks, repairs)
```

**Legacy routes to keep (or replace with adapters):**
```
/api/workstreams   → adapter → /api/v1/home/workstreams (new)
/api/home          → adapter → /api/v1/home/stats (new)
/api/graph         → adapter → /api/v1/graph/evidence (exists)
/api/audiences     → adapter → /api/v1/audiences (new)
/api/analyze       → adapter → /api/v1/vault/* (new)
/api/simulations   → adapter → /api/v1/simulations/* (new)
/api/exports       → adapter → /api/v1/export/{format} (exists)
/api/account       → adapter → /api/v1/account (new)
/api/signup        → adapter → /api/v1/auth/signup (exists)
/api/iris          → adapter → /api/v1/iris/ask (exists)
/api/settings      → adapter → /api/v1/settings (exists)
/api/health        → adapter → /api/v1/health (exists)
```

---

*End of Wave 2 Frontend Map. Next: WAVE3-INTEGRATION-PLAN.md — implementation order, file-by-file changes, and test strategy.*
