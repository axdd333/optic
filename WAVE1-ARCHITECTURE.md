# Optic V1 — Wave 1 System Architecture

> **Document purpose**: Define the complete file ownership map for 17 logical agents, the data flow from filesystem scan through to dashboard, the API contract between the JS SPA and backend, the integration order for wiring everything together, and known conflicts with resolution strategies.

---

## 1. Architecture Overview

Optic V1 has two runtimes that must work as one product:

| Runtime | Technology | Port | Key File |
|---------|-----------|------|----------|
| **Ctxorg Backend** | Python `ThreadingHTTPServer`, stdlib | `:3003` | `backend/src/ctxorg/server.py` (8112 lines) |
| **V1 Backend** | Python FastAPI | `:3003` (alternative) | `backend/src/optic/v1/server.py` (1531 lines) |
| **JS SPA** | Vanilla JS (~8200 lines) | served by backend | `backend/src/ctxorg/static/app.js` |

**The core challenge**: The V1 FastAPI server (`optic/v1/server.py`) and the ctxorg server (`ctxorg/server.py`) are currently two *separate* server implementations. The V1 server re-implements the ctxorg routes with mock data. The JS app is wired to the ctxorg server. These must converge into a single, coherent product where every UI element is driven by real data.

**Architecture principle**: Merge V1 intelligence into the ctxorg server (which has the real scan/graph/workstreams pipeline). The V1 `models`, `lenses`, `contradiction`, `inference`, `parsers`, `resolver`, `graph`, `scrapers`, and `iris_audit` modules are imported as a library by ctxorg. The V1 FastAPI server becomes a thin compatibility wrapper or is deprecated.

---

## 2. The 17 Agents — File Ownership Map

Each agent is a logical owner for a set of files. Agents are the *units of change* for Wave 1 integration work. When wiring the JS app to real data, the corresponding agent is responsible for the backend module(s) that produce that data.

### Agent 1: Scan — Filesystem Walker

**Responsibility**: Walk the user's filesystem, record all files in SQLite, emit `items` rows with paths, sizes, mtimes, extensions.

| File | Path | Role |
|------|------|------|
| `scan.py` | `backend/src/ctxorg/scan.py` | Primary: `run()` walks `fs.walk(cfg)`, upserts items |
| `fs.py` | `backend/src/ctxorg/fs.py` | Filesystem walker (iterates `sources` from config) |
| `state.py` | `backend/src/ctxorg/state.py` | Run state constants (`SCANNED`, `INDEXED`, etc.) |

**Output**: `items` table in `ctx.db` (ctxorg SQLite).

### Agent 2: Ingest — File Ingestion & Artifact Creation

**Responsibility**: Take scanned files, parse them, create V1 `Artifact` objects, handle uploads and URL imports.

| File | Path | Role |
|------|------|------|
| `ingest.py` | `backend/src/ctxorg/ingest.py` | Ingestion pipeline for scanned files |
| `extract.py` | `backend/src/ctxorg/extract.py` | Text extraction from files |
| `parsers.py` | `backend/src/optic/v1/parsers.py` | 17 format parsers (V1 library) |
| `scrapers.py` | `backend/src/optic/v1/scrapers.py` | Source provider scrapers (LinkedIn, GitHub, etc.) |

**Output**: `Artifact` objects → `artifacts` table in `v1.db`.

### Agent 3: Cluster — Workstream Clustering

**Responsibility**: Group scanned files into topic clusters ("workstreams"), filter noise, assign confidence scores.

| File | Path | Role |
|------|------|------|
| `workstreams.py` | `backend/src/ctxorg/workstreams.py` | Primary: `compute()` clusters items by path/topics, noise filtering |
| `terms.py` | `backend/src/ctxorg/terms.py` | Term extraction, doc/code extension lists |
| `labels.py` | `backend/src/ctxorg/labels.py` | File labeling helpers |
| `naming.py` | `backend/src/ctxorg/naming.py` | Naming conventions for clusters |
| `latent.py` | `backend/src/ctxorg/latent.py` | Latent feature extraction from files |
| `deep.py` | `backend/src/ctxorg/deep.py` | Deep path analysis for metadata |

**Output**: Workstream card objects → `/api/workstreams` → `state.workstreams` in JS.

### Agent 4: Graph — Graph Construction & Evidence Graph

**Responsibility**: Build topology graph from items, maintain the V1 evidence graph (typed nodes + edges).

| File | Path | Role |
|------|------|------|
| `graph.py` | `backend/src/ctxorg/graph.py` | Topology graph builder for `/api/graph` |
| `graph.py` | `backend/src/optic/v1/graph.py` | V1 `EvidenceGraph` — typed SQLite graph for audit evidence |
| `atlas.py` | `backend/src/ctxorg/atlas.py` | Atlas/spatial layout helpers |
| `refs.py` | `backend/src/ctxorg/refs.py` | Cross-reference tracking |

**Output**: `/api/graph` payload (nodes + edges), V1 evidence graph for audit pipeline.

### Agent 5: Signal — Signal Detection

**Responsibility**: Detect low-level interpreted features from artifacts — frequent topics, timeline gaps, stale bios, project velocity, workstream fragmentation.

| File | Path | Role |
|------|------|------|
| `models.py` | `backend/src/optic/v1/models.py` | `Signal` dataclass definition |
| `server.py` (V1) | `backend/src/optic/v1/server.py` | `_workstream_to_signals()` — converts workstreams to `Signal` objects |
| `identity.py` | `backend/src/ctxorg/identity.py` | Identity-specific signal detection |
| `screens.py` | `backend/src/ctxorg/screens.py` | Screenshot/visual signal extraction |

**Output**: `Signal` objects → `signals` table in `v1.db`.

### Agent 6: Claim — Inference Claim Generation

**Responsibility**: Generate structured inference claims from signals for specific audience lenses. Every claim cites evidence, exposes uncertainty, shows counterarguments.

| File | Path | Role |
|------|------|------|
| `inference.py` | `backend/src/optic/v1/inference.py` | `InferenceCardGenerator` — generates `InferenceClaim` objects per lens |
| `models.py` | `backend/src/optic/v1/models.py` | `InferenceClaim`, `ConfidenceBand`, `EvidenceLink` dataclasses |

**Output**: `InferenceClaim` objects → `claims` table in `v1.db` → `/api/v1/claims`.

### Agent 7: Contradiction — Contradiction Detection

**Responsibility**: Find gaps, conflicts, stale context, and audience-dependent ambiguity across the evidence graph.

| File | Path | Role |
|------|------|------|
| `contradiction.py` | `backend/src/optic/v1/contradiction.py` | `ContradictionEngine` — finds job title mismatches, timeline conflicts, stale context, profile mismatches, claim contradictions |
| `models.py` | `backend/src/optic/v1/models.py` | `Contradiction` dataclass |

**Output**: `Contradiction` objects → `contradictions` table → `/api/v1/contradictions`.

### Agent 8: Risk — Risk Flag Generation

**Responsibility**: Generate risk flags from claims, contradictions, and patterns.

| File | Path | Role |
|------|------|------|
| `server.py` (V1) | `backend/src/optic/v1/server.py` | Risk generation in `run_audit()` (lines 1165-1181) |
| `models.py` | `backend/src/optic/v1/models.py` | `RiskFlag`, `RiskCategory` dataclasses |

**Output**: `RiskFlag` objects → `risks` table → `/api/v1/risks`.

### Agent 9: Repair — Repair Action Generation

**Responsibility**: Generate concrete actions users can take to improve their signal for specific audiences.

| File | Path | Role |
|------|------|------|
| `server.py` (V1) | `backend/src/optic/v1/server.py` | `_generate_repairs()` — generates `RepairAction` objects |
| `models.py` | `backend/src/optic/v1/models.py` | `RepairAction`, `RepairStatus` dataclasses |

**Output**: `RepairAction` objects → `repairs` table → `/api/v1/repairs`.

### Agent 10: Lens — Audience Lens Configuration

**Responsibility**: Define and manage audience viewpoints (recruiter, investor, admissions, etc.) with their priorities, evidence preferences, risk sensitivities, and forbidden outputs.

| File | Path | Role |
|------|------|------|
| `lenses.py` | `backend/src/optic/v1/lenses.py` | 9 `AudienceLens` configurations |
| `models.py` | `backend/src/optic/v1/models.py` | `AudienceLens` dataclass |

**Output**: `AUDIENCE_LENSES` dict used by Claims, Audiences, Simulate endpoints.

### Agent 11: Parser — Format Parsing

**Responsibility**: Parse 17+ file formats into structured `Artifact` objects.

| File | Path | Role |
|------|------|------|
| `parsers.py` | `backend/src/optic/v1/parsers.py` | `ParserRegistry` + 17 format parsers (zip, json, csv, html, pdf, docx, txt/md, mbox, email, ics, vcard, image, xml/plist, sqlite, twitter, linkedin, reddit) |

**Output**: `ParseResult` → `Artifact` objects.

### Agent 12: Resolver — Entity Extraction & Linking

**Responsibility**: Extract entities (people, orgs, schools, employers, projects) from artifacts and link them.

| File | Path | Role |
|------|------|------|
| `resolver.py` | `backend/src/optic/v1/resolver.py` | `EntityResolver` — extracts emails, URLs, handles, orgs, people from artifact text/metadata |

**Output**: `Entity` objects → `/api/v1/entities`.

### Agent 13: Iris — Conversational Audit Chat

**Responsibility**: Answer user questions about their signal profile using V1 database context and optionally Ollama LLM.

| File | Path | Role |
|------|------|------|
| `iris_audit.py` | `backend/src/optic/v1/iris_audit.py` | `IrisAuditChat` — gathers context from v1.db, tries LLM, falls back to deterministic summary |
| `iris.py` | `backend/src/ctxorg/iris.py` | Legacy Iris streaming endpoint |
| `ollama.py` | `backend/src/ctxorg/ollama.py` | Ollama client for LLM calls |
| `chat.py` | `backend/src/ctxorg/chat.py` | Chat reply helpers |
| `infer.py` | `backend/src/ctxorg/infer.py` | LLM-powered inference for nodes |

**Output**: `/api/iris` (streaming), `/api/v1/iris/ask` (direct answer), `/api/infer` (node inference).

### Agent 14: Export — Report Generation & Export

**Responsibility**: Generate structured audit reports and export in multiple formats (JSON, Markdown, PDF).

| File | Path | Role |
|------|------|------|
| `server.py` (V1) | `backend/src/optic/v1/server.py` | `get_report()`, `export_report()` endpoints |
| `models.py` | `backend/src/optic/v1/models.py` | `Report` dataclass |
| `planner.py` | `backend/src/ctxorg/planner.py` | Planning/action plan generation |
| `bulkplan.py` | `backend/src/ctxorg/bulkplan.py` | Bulk planning |
| `docedit.py` | `backend/src/ctxorg/docedit.py` | Document editing for exports |

**Output**: `/api/v1/report`, `/api/v1/export/{format}`, `/api/report`.

### Agent 15: Dashboard — Home & Dashboard Data Aggregation

**Responsibility**: Aggregate data from all agents into the home/dashboard payload and audience simulation data.

| File | Path | Role |
|------|------|------|
| `server.py` (ctxorg) | `backend/src/ctxorg/server.py` | `home_payload()` (line 4780), `audiences_payload()` (line 4817), `simulate_payload()` (line 4829), `simulations_payload()` (line 4853) |
| `health.py` | `backend/src/ctxorg/health.py` | Health check helpers |
| `cfg.py` | `backend/src/ctxorg/cfg.py` | Config loading |
| `log.py` | `backend/src/ctxorg/log.py` | Structured logging |

**Output**: `/api/home`, `/api/audiences`, `/api/simulate/{id}`, `/api/simulations`.

### Agent 16: View — JS SPA Frontend

**Responsibility**: Render the entire UI from live data, manage 10 mode states, handle all client-side interactivity.

| File | Path | Role |
|------|------|------|
| `app.js` | `backend/src/ctxorg/static/app.js` | **8218-line vanilla JS SPA** — 11 mode classes, state management, D3/Three.js rendering, all API calls |
| `app.css` | `backend/src/ctxorg/static/app.css` | All CSS styling |
| `index.html` | `backend/src/ctxorg/static/index.html` | HTML shell, leftnav, topbar, overlays |

**Mode classes in app.js**:
| Mode | Class | Line | Data Sources |
|------|-------|------|-------------|
| Home | `WorkstreamsMode` | 789 | `/api/workstreams`, `/api/home` |
| Map | `TopologyMode` | 3917 | `/api/graph`, `/api/audiences` |
| Timeline | `TimelineMode` | 4778 | `/api/graph` (nodes with mtime) |
| Universe | `UniverseMode` | 5172 | `/api/graph` (nodes by category) |
| Iris | `IrisMode` | 1576 | `/api/iris` (streaming) |
| Vault | `VaultMode` | 1699 | `/api/analyze` (storage analysis) |
| Audiences | `AudiencesMode` | 1853 | `/api/audiences`, `/api/simulate/{id}` |
| Simulations | `SimulationsMode` | 1942 | `/api/simulations` |
| Exports | `ExportsMode` | 2098 | `/api/export/history` |
| Settings | `SettingsMode` | 2245 | `/api/settings`, `/api/account` |

### Agent 17: Server — HTTP Routing, Static Serving, Ops

**Responsibility**: Route dispatch, static file serving, auth, workspace management, billing, integrations, ops.

| File | Path | Role |
|------|------|------|
| `server.py` | `backend/src/ctxorg/server.py` | Primary HTTP server — `route()` (GET, line 731) and `post()` (POST, line 823) dispatch |
| `__main__.py` | `backend/src/ctxorg/__main__.py` | Entry point: `python -m ctxorg serve` |
| `__init__.py` | `backend/src/ctxorg/__init__.py` | Package init |
| `db.py` | `backend/src/ctxorg/db.py` | SQLite helpers (`open_db`, `rows`, `inc`) |
| `cmd.py` | `backend/src/ctxorg/cmd.py` | Command infrastructure |
| `cli.py` | `backend/src/ctxorg/cli.py` | CLI entry points |
| `retry.py` | `backend/src/ctxorg/retry.py` | Retry logic |
| `cleanup.py` | `backend/src/ctxorg/cleanup.py` | Cleanup helpers |
| `doctor.py` | `backend/src/ctxorg/doctor.py` | Diagnostics |
| `mover.py` | `backend/src/ctxorg/mover.py` | File moving/organization |
| `mirror.py` | `backend/src/ctxorg/mirror.py` | Mirror/sync logic |
| `mirofish.py` | `backend/src/ctxorg/mirofish.py` | Mirror utilities |

**Managed routes** (all `if path ==` checks in `route()`):
- Core: `/api/runs`, `/api/graph`, `/api/workstreams`, `/api/report`, `/api/status`, `/api/home`
- Auth: `/api/account`, `/api/signup`, `/api/signout`
- Workspace: `/api/workspace`, `/api/workspace/members`, `/api/workspace/invites`
- Billing: `/api/billing`, `/api/billing/usage`, `/api/billing/checkout`, etc.
- Integrations: `/api/integrations/*` (9 routes)
- New Wave 1: `/api/audiences`, `/api/simulations`, `/api/simulate/{id}`
- AI: `/api/infer`, `/api/iris`, `/api/chat`
- Ops: `/api/ops/health`, `/api/ops/backups`

---

## 3. Data Flow: Filesystem Scan → Dashboard

### End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: SCAN                                                           │
│ Agent 1 (Scan): fs.walk(cfg) → items table in ctx.db                    │
│ Output: ~100K-500K file records with path, size, mtime, ext             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: CLUSTER                                                        │
│ Agent 3 (Cluster): workstreams.compute() → cluster rows                 │
│ Groups files by parent folder/topic patterns, filters noise             │
│ Output: ~20-50 workstreams each with id, name, confidence,              │
│         file_count, size, topics, key_files, category_breakdown         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: GRAPH                                                          │
│ Agent 4 (Graph): graph_payload() → { nodes[], edges[], run }            │
│ Builds topology: each file = node with x/y/z, cluster, category         │
│ Edges connect files within same cluster + cross-cluster                 │
│ Output: /api/graph JSON (consumed by Map, Timeline, Universe views)     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: SIGNAL DETECTION                                               │
│ Agent 5 (Signal): _workstream_to_signals(ws) → Signal objects           │
│ Categories: frequent_topic, project_velocity, workstream_fragmentation  │
│ Output: Signal rows in v1.db signals table                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: INFERENCE CLAIMS                                               │
│ Agent 6 (Claim): InferenceCardGenerator per lens → InferenceClaim[]     │
│ Each lens (9 total) generates claims from signals citing evidence       │
│ Output: /api/v1/claims — structured, audience-specific readings         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 6: CONTRADICTION & RISK                                           │
│ Agent 7+8: ContradictionEngine.run_full_audit() + risk generation       │
│ Finds: job title mismatches, timeline gaps, stale context, claim        │
│        oppositions, identity fragmentation                              │
│ Output: /api/v1/contradictions, /api/v1/risks                           │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 7: REPAIR ACTIONS                                                 │
│ Agent 9: _generate_repairs(cards, contradictions, risks)                │
│ Prioritized by: impact × urgency × reversibility ÷ effort               │
│ Output: /api/v1/repairs (sorted by priority)                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 8: DASHBOARD AGGREGATION                                          │
│ Agent 15 (Dashboard): home_payload() aggregates all layers              │
│ Combines: file_count, workstreams_count, signal_count, narratives,      │
│           coherence_avg, exposures, iris_summary                        │
│ Output: /api/home → JS state.homeData                                   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 9: JS SPA RENDERING                                               │
│ Agent 16 (View): 10 mode classes render from state.*                    │
│                                                                         │
│ Home:       state.workstreams → category tabs, sort, cards w/ actions   │
│ Map:        state.graph → Three.js/D3 canvas, cluster nebulae, labels   │
│ Timeline:   state.graph.nodes → time-sorted canvas with filters         │
│ Universe:   state.graph.nodes → 3D force layout globe                   │
│ Iris:       /api/iris streaming → chat UI with audience lenses           │
│ Vault:      /api/analyze → storage breakdown by kind                    │
│ Audiences:  state.audiences → audience read cards w/ simulate button    │
│ Simulations:/api/simulations → saved simulation scenarios               │
│ Exports:    /api/report, /api/v1/export/{fmt} → download/export UI      │
│ Settings:   /api/settings → account, workspace, billing tabs            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Data Dependencies (Upstream → Downstream)

```
fs.walk → items (scan.py)
items → clusters (workstreams.py)
items → nodes+edges (graph.py)
clusters → workstreams (workstreams.py → /api/workstreams)
clusters → signals (server.py → _workstream_to_signals)
signals → claims (inference.py → InferenceCardGenerator)
claims → contradictions (contradiction.py)
claims + contradictions + risks → repairs (server.py → _generate_repairs)
all of above → home (server.py → home_payload)
```

---

## 4. API Contract: JS App ↔ V1 Server

### 4a. API Route Inventory

#### Existing Routes (ctxorg server, already wired)

| Method | Route | JS Consumer | Returns |
|--------|-------|-------------|---------|
| GET | `/api/health` | boot health check | `{status, version}` |
| GET | `/api/home` | `loadHomeData()` | `{file_count, total_size, workstreams_count, signal_count, source_count, last_analyzed_ago, narratives[], exposures, iris_summary, home, account}` |
| GET | `/api/runs` | run selector | `{runs: [...]}` |
| GET | `/api/graph?run=X` | `loadGraph()` | `{run, nodes[], links[]/edges[]}` |
| GET | `/api/workstreams` | WorkstreamsMode | `{workstreams[], cached}` |
| GET | `/api/status` | `loadStatus()` | `{scanning, last_run, queue_depth, progress: {stage, indexed, total}}` |
| GET | `/api/report?run=X` | ExportsMode | `{corpus, workstreams, scan, infer}` |
| GET | `/api/analyze?kind=X&limit=N` | VaultMode | `{kind, items[]/groups[]}` |
| GET | `/api/audiences` | AudiencesMode, Map panel | `{run, audiences[], cached}` |
| GET | `/api/simulate/{id}` | Audience modal | `{audience_id, name, icon, score, highlights[], risks[], narrative}` |
| GET | `/api/simulations` | SimulationsMode | `{run, items[]}` |
| POST | `/api/scan` | Scan button | `{run_id, started, folder_count}` |
| POST | `/api/iris` | IrisMode | Streaming SSE chunks |
| POST | `/api/chat` | Chat form | `{reply}` |
| POST | `/api/rename` | Rename action | `{ok, from, to}` |
| GET | `/api/settings` | SettingsMode | `{settings: {...}}` |
| GET | `/api/account` | SettingsMode | `{signed_in, account}` |

#### V1-Specific Routes (FastAPI server, NOT yet wired to JS)

| Method | Route | Purpose | Status |
|--------|-------|---------|--------|
| POST | `/api/v1/auth/signup` | User signup | V1 only |
| POST | `/api/v1/auth/login` | User login | V1 only |
| GET | `/api/v1/onboarding` | Onboarding state | V1 only |
| POST | `/api/v1/onboarding/step` | Advance onboarding | V1 only |
| GET | `/api/v1/sources` | List sources | V1 only |
| POST | `/api/v1/sources` | Add source | V1 only |
| POST | `/api/v1/sources/import` | Import files/URLs | V1 only |
| POST | `/api/v1/sources/{id}/consent` | Add consent receipt | V1 only |
| GET | `/api/v1/entities` | List resolved entities | V1 only |
| GET | `/api/v1/graph/evidence` | Evidence graph | V1 only |
| GET | `/api/v1/audit/{mode}` | Run full audit pipeline | V1 only |
| GET | `/api/v1/claims` | List inference claims | V1 only |
| GET | `/api/v1/contradictions` | List contradictions | V1 only |
| GET | `/api/v1/risks` | List risks | V1 only |
| GET | `/api/v1/repairs` | List repair actions | V1 only |
| POST | `/api/v1/repairs/{id}/complete` | Mark repair done | V1 only |
| GET | `/api/v1/report` | Audit report | V1 only |
| GET | `/api/v1/export/{format}` | Export report (json/md/pdf) | V1 only |
| POST | `/api/v1/iris/ask` | Direct Iris question | V1 only |
| GET | `/api/v1/health` | V1 health check | V1 only |
| GET | `/api/v1/status` | V1 backend status | V1 only |
| GET | `/api/v1/settings` | Get V1 settings | V1 only |
| POST | `/api/v1/settings` | Update V1 settings | V1 only |

### 4b. Contract: What the JS App Expects

#### `/api/home` — Extended Response Contract

```json
{
  "file_count": 3574,
  "total_size": 3700000000,
  "workstreams_count": 30,
  "coherence_avg": 0.78,
  "signal_count": 128473,
  "source_count": 1236,
  "last_analyzed_ago": "2h ago",
  "narratives": ["AI builder", "Independent thinker", "Privacy conscious"],
  "exposures": 6,
  "iris_summary": "You are a technically sophisticated builder...",
  "home": "/Users/ahmedm",
  "account": { "signed_in": true, "account": {...} }
}
```

**JS consumer** (`loadHomeData()`, app.js line 224):
- Caches in `state.homeData`
- Populates `#statusbarIndex` via `updateStatusIndex()`
- Feeds "Your Digital Self" right panel on Home mode
- `state.homeSummary` drives Iris insight section (pulsing skeleton if null)

#### `/api/workstreams` — Card Shape Contract

```json
{
  "workstreams": [
    {
      "id": "cluster-42",
      "name": "Research & Learning",
      "confidence": 0.92,
      "file_count": 142,
      "size": 48234567,
      "mtime": 1717200000,
      "topics": ["research", "learning", "ai", "notes", "papers"],
      "summary": "Dense technical notes, papers, and study artifacts...",
      "key_files": [
        { "path": "/Users/.../Research.txt", "ext": ".txt", "size": 14200, "mtime": 1717200000 }
      ],
      "folders": ["Research", "Documents"],
      "category_breakdown": { "Documents": 0.72, "Code": 0.18, "Other": 0.10 }
    }
  ],
  "cached": true
}
```

**JS consumer** (`loadWorkstreams()`, WorkstreamsMode.render):
- Caches in `state.workstreams`
- Renders `ws-card2` cards with emoji, confidence dot, top evidence
- Client-side filtering by category tabs (Identity, Work & skills, Life, Relations, Behavior)
- Client-side sorting (Relevance, Recent, Size, A–Z)
- "→ View in map" calls `state.manager.switch("topology")` then highlights cluster
- "Simulate audience" opens audience modal with `/api/simulate/{id}`

#### `/api/graph` — Topology Contract

```json
{
  "run": "20260606-fast-mock",
  "nodes": [
    {
      "id": "mock-node-00",
      "path": "/Users/.../file.txt",
      "label": "file.txt",
      "ext": ".txt",
      "size": 14200,
      "mtime": 1717200000,
      "category": "Documents",
      "cluster": "cluster-research-learning",
      "x": 112.0, "y": 45.0, "z": 78.0, "w": 0
    }
  ],
  "links": [
    { "a": "mock-node-00", "b": "mock-node-01", "score": 0.72, "why": "same workstream" }
  ],
  "edges": []  // alias for links (JS code reads both)
}
```

**JS consumer** (`loadGraph()`, TopologyMode, TimelineMode, UniverseMode):
- `state.nodes` = normalized nodes (picks `edges` or `links`)
- `state.nodeById` = Map for O(1) lookups
- Canvas rendering uses x/y/z for 3D layout, category for colors
- Cluster field drives cluster nebulae and label overlays

#### `/api/audiences` — Audience Read Contract

```json
{
  "run": "20260606-fast-mock",
  "audiences": [
    {
      "id": "recruiter",
      "name": "Recruiter read",
      "icon": "👤",
      "score": 87,
      "summary": "Most likely a strong fit for technical leadership roles."
    }
  ],
  "cached": false
}
```

**JS consumer** (`loadAudiences()`, AudiencesMode, Map right panel):
- Renders audience cards with icon, score bar, summary
- Click opens simulation modal via `/api/simulate/{audience_id}`

### 4c. API Route Gaps — What Must Be Built

These routes are defined in both the ctxorg AGENTS.md spec AND the V1 FastAPI server, but the JS app doesn't call them yet:

| Priority | Route | Backend Status | JS Wiring Needed |
|----------|-------|---------------|-----------------|
| **P0** | `/api/audiences` | ✅ In ctxorg server (line 792) | ✅ Already wired |
| **P0** | `/api/simulate/{id}` | ✅ In ctxorg server (line 796) | ✅ Audience modal calls it |
| **P0** | `/api/home` (extended) | ✅ Returns full payload | ✅ Already wired |
| **P1** | `/api/v1/claims` | ✅ In V1 server | ❌ Needs route in ctxorg or V1-ctxorg bridge |
| **P1** | `/api/v1/contradictions` | ✅ In V1 server | ❌ Needs route in ctxorg |
| **P1** | `/api/v1/risks` | ✅ In V1 server | ❌ Needs route in ctxorg |
| **P1** | `/api/v1/repairs` | ✅ In V1 server | ❌ Needs route in ctxorg |
| **P2** | `/api/v1/audit/{mode}` | ✅ In V1 server | ❌ Needs trigger from JS |
| **P2** | `/api/v1/report` | ✅ In V1 server | ❌ Needs export wiring |
| **P3** | `/api/v1/entities` | ✅ In V1 server | ❌ Future use |
| **P3** | `/api/v1/iris/ask` | ✅ In V1 server | ❌ Needs Iris mode integration |

---

## 5. Integration Order — What Gets Wired First

### Phase 1: Foundation (Week 1)

```
1. ✅ Confirm ctxorg server starts and serves index.html (port :3003)
2. ✅ Confirm JS app loads without errors (all modes reachable)
3. ✅ Confirm /api/home returns full payload with signal_count, narratives, iris_summary
4. ✅ Confirm /api/audiences returns real computed scores (not hardcoded)
5. ✅ Confirm /api/simulate/{id} works for all 9 audience lenses
6. ✅ Status bar shows live "Indexed: Xh ago · N signals from M sources"
7. 🔲 Remove all mock data fallbacks in V1 server's legacy routes
```

### Phase 2: Home View Wiring (Week 1-2)

```
8.  🔲 Home cards render from real /api/workstreams data (not hardcoded mock)
9.  🔲 Category tabs filter workstreams client-side
10. 🔲 Sort dropdown works (Relevance, Recent, Size, A-Z)
11. 🔲 "→ View in map" switches mode and highlights cluster
12. 🔲 "Inspect evidence" expands card to show all key_files
13. 🔲 "Simulate audience" opens audience modal with real data
14. 🔲 Right panel "Your Digital Self" shows live globe + stats + narratives
15. 🔲 Iris summary shows real data (or pulsing skeleton if null)
```

### Phase 3: Map & Canvas Views (Week 2)

```
16. 🔲 Map shows cluster nebula blobs behind nodes
17. 🔲 Cluster label divs at centroids update on pan/zoom
18. 🔲 Map toolbar with zoom +/- and pan/select/focus tools
19. 🔲 Map right panel shows audience scores from /api/audiences
20. 🔲 Canvas hint text: "Drag to rotate · Scroll to zoom · Click to focus"
21. 🔲 Timeline HUD only visible in Timeline mode (existing fix — don't regress)
22. 🔲 Universe canvas only visible in Universe mode
```

### Phase 4: V1 Intelligence Pipeline (Week 2-3)

```
23. 🔲 Bridge V1 audit pipeline into ctxorg: import V1 modules in ctxorg server
24. 🔲 Add /api/v1/claims route proxying from ctxorg to V1 intelligence
25. 🔲 Add /api/v1/contradictions route
26. 🔲 Add /api/v1/risks route
27. 🔲 Add /api/v1/repairs route
28. 🔲 Wire Vault mode to show claims/contradictions/risks/repairs
29. 🔲 Wire Exports to /api/v1/report and /api/v1/export/{format}
```

### Phase 5: Leftnav & Polish (Week 3)

```
30. 🔲 Leftnav: Simulations / Exports / Settings items
31. 🔲 Settings nav item opens settings overlay
32. 🔲 Final CSS polish pass, version bumps
33. 🔲 Zero JS errors on any mode switch
34. 🔲 All [hidden] elements respect display pattern
```

---

## 6. Known Conflicts & Resolution Strategies

### Conflict 1: Two Servers Competing on Port :3003

**Problem**: The ctxorg server (`python -m ctxorg serve --port 3003`) and the V1 FastAPI server (`uvicorn optic.v1.server:app --port 3003`) are separate server processes. Both want port :3003. Currently only one can run at a time.

**Impact**: If the V1 server is running, the ctxorg scan/graph/workstream pipeline is unavailable. If the ctxorg server is running, the V1 routes (claims, contradictions, risks, repairs) are unreachable.

**Resolution**: **Merge V1 intelligence into the ctxorg server.** Import `optic.v1.*` modules directly inside `ctxorg/server.py`, use the ctxorg SQLite for persistence, and add the V1 routes to the ctxorg `route()` dispatch chain. The V1 FastAPI server becomes an optional development convenience but is not the production path.

**Implementation**:
```python
# In ctxorg/server.py, import V1 intelligence modules:
from optic.v1.models import Signal, InferenceClaim, Contradiction, ...
from optic.v1.lenses import AUDIENCE_LENSES
from optic.v1.contradiction import ContradictionEngine
from optic.v1.inference import InferenceCardGenerator

# Add V1 routes to ctxorg route():
if path == "/api/v1/claims":
    return send(req, v1_claims_payload(cfg))
if path == "/api/v1/contradictions":
    return send(req, v1_contradictions_payload(cfg))
```

### Conflict 2: Mock Data in Both Backends

**Problem**: Both the ctxorg server and V1 server have hardcoded mock data paths. The V1 server's `_fast_mock_ws()`, `_mock_graph_payload()`, and `_mock_home_payload()` return fake data. The ctxorg server falls back to empty results if no scan has run.

**Impact**: The JS app may show stale mock data even when a real scan exists.

**Resolution**: 
1. Remove `_fast_mock_ws()`, `_mock_graph_payload()`, `_mock_home_payload()` from the V1 server once ctxorg routes are proven
2. In ctxorg, always attempt real data first; only fall back to a minimal "no scan yet" placeholder
3. Add a `data_source` field to every API response: `"source": "ctxorg"` or `"source": "mock"` so the JS app can show a "live data" indicator

### Conflict 3: Duplicate Route Definitions

**Problem**: The V1 server defines legacy-compatible routes (`/api/home`, `/api/workstreams`, `/api/graph`, `/api/status`) that shadow the ctxorg implementations.

**Impact**: If both servers run on different ports, the JS app must know which port to call. If routes are merged, duplicate definitions cause confusion.

**Resolution**: After merging V1 into ctxorg, **delete the legacy route shims from V1 server** (`legacy_*` routes). The ctxorg server is the canonical source for these routes. The V1 server only serves the V1-specific routes (`/api/v1/*`).

### Conflict 4: Database Incompatibility — ctx.db vs v1.db

**Problem**: Ctxorg uses SQLite at `{state_dir}/ctx.db` with an `items` table. V1 uses SQLite at `backend/.optic/v1.db` with 10 tables (users, sources, artifacts, signals, claims, contradictions, risks, repairs, reports, onboarding).

**Impact**: The V1 audit pipeline cannot query real scan data from ctx.db because the schemas are different.

**Resolution**: **Add a bridge layer** that queries ctx.db for items/workstreams, converts them to V1 model objects (Signal, Artifact), and feeds them into the V1 intelligence pipeline. The V1 audit pipeline writes to v1.db. See the existing `_load_ctxorg_workstreams()` function in V1 server.py (line 872) as the prototype.

Alternative: **Add a `v1_*` prefix table group to ctx.db** so all data is in one database. This eliminates the dual-database problem entirely.

### Conflict 5: JS App Expects Hardcoded Data Shape

**Problem**: The JS app's mode classes were built against specific JSON shapes from the ctxorg server. If the V1 server returns differently shaped data (e.g., V1 uses `edges` vs `links`), rendering breaks.

**Impact**: Mode switch failures, blank canvases, missing cards.

**Resolution**: The JS app already normalizes data defensively:
- `state.graph.links = state.graph.links || state.graph.edges || []` (app.js line 372)
- Each mode's `mount()` should validate data shape and degrade gracefully
- **Add a data validation layer** in `boot()` that checks all API responses against expected schemas

### Conflict 6: Ollama Dependency for Iris Summary

**Problem**: The `iris_summary` in `/api/home` is generated by Ollama (`_home_summary_start` in ctxorg server.py). If Ollama is not running, the summary is null, and the JS shows a pulsing skeleton forever.

**Impact**: "Your Digital Self" panel never fully loads.

**Resolution**:
1. Generate the Iris summary on first `/api/home` call if null, cache in a sidecar file
2. If Ollama is unavailable after 3 retries, generate a deterministic fallback from workstream names/topics
3. The JS app already handles `null` → shows skeleton; add a timeout that falls back to "Generate insight" button

### Conflict 7: Auth/Token Mismatch

**Problem**: The V1 server uses token-based auth (query param `?token=X`). The ctxorg server uses cookie-based sessions (`optic_session`). The JS app currently uses neither — it calls APIs directly.

**Impact**: If auth is enforced, all JS API calls fail. If not enforced, there's no user context.

**Resolution**: For Wave 1, **keep all routes unauthenticated** (local-first product — auth is for future cloud features). The `/api/account` route already returns `{signed_in: false}` by default. V1 routes that require `token` should be made optional (default to a local user).

### Conflict 8: CSS/JS Version Bumps

**Problem**: The AGENTS.md requires CSS version bumps (`-v46` → `-v47`) and JS version bumps on every edit. This is easy to forget.

**Impact**: Browser caching serves stale CSS/JS.

**Resolution**: **Automate with a build stamp.** Add a `?v={git_hash}` query parameter generated at server startup. The ctxorg server already reads `static/index.html` — it can inject the version param.

### Conflict 9: Mode State Leakage

**Problem**: When switching modes, canvas contexts, animation frames, and event listeners from the previous mode may persist.

**Impact**: Memory leaks, performance degradation, duplicate event handlers, wrong canvas showing.

**Resolution**: The JS app already has `unmount()` methods on each mode class. Ensure every mode:
1. Cancels `requestAnimationFrame` in `unmount()`
2. Removes event listeners
3. Hides its DOM elements with `[hidden]` attribute
4. Clears canvas with `clearRect` before hiding

The AGENTS.md quality gates specifically call out Timeline HUD and Universe canvas regressions.

### Conflict 10: V1 Audit Pipeline is Not Incremental

**Problem**: The V1 audit pipeline (`/api/v1/audit/{mode}`) regenerates all claims, contradictions, and repairs from scratch on every call. For 100K+ files, this could take minutes.

**Impact**: Slow audit runs, blocking HTTP calls.

**Resolution**:
1. Run audit as a background task, return immediately with a run ID
2. Poll `/api/status` for completion (reuse existing scan status pattern)
3. Cache results in v1.db; only recompute for changed workstreams
4. Trigger recomputation on new scan completion, not on every page load

---

## 7. Integration Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        BROWSER (JS SPA)                              │
│                                                                      │
│  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐          │
│  │  Home  │ │  Map   │ │ Timeline │ │Universe│ │  Iris  │  ...     │
│  │  Mode  │ │  Mode  │ │   Mode   │ │  Mode  │ │  Mode  │          │
│  └───┬────┘ └───┬────┘ └────┬─────┘ └───┬────┘ └───┬────┘          │
│      │          │            │           │          │                │
│      └──────────┴────────────┴───────────┴──────────┘                │
│                         │                                            │
│              state.{homeData, workstreams, graph,                    │
│                      audiences, status, report}                      │
│                         │                                            │
│              fetch() → port :3003                                    │
└─────────────────────────┬────────────────────────────────────────────┘
                          │
┌─────────────────────────┴────────────────────────────────────────────┐
│                   CTXORG SERVER (port :3003)                          │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  route() / post() dispatch                                   │     │
│  │  GET: /api/home, /api/workstreams, /api/graph, /api/status, │     │
│  │       /api/audiences, /api/simulate/{id}, etc.              │     │
│  │  POST: /api/scan, /api/iris, /api/chat                     │     │
│  └──────────────────────────┬──────────────────────────────────┘     │
│                             │                                         │
│  ┌──────────────────────────┼──────────────────────────────────┐     │
│  │              CTXORG MODULES                                   │     │
│  │  scan.py ──► ingest.py ──► workstreams.py ──► graph.py       │     │
│  │  fs.py       extract.py    terms.py           atlas.py        │     │
│  │  state.py     parsers.py*   labels.py          refs.py        │     │
│  │                             naming.py                         │     │
│  │                             latent.py                         │     │
│  └──────────────────────────┬──────────────────────────────────┘     │
│                             │                                         │
│  ┌──────────────────────────┼──────────────────────────────────┐     │
│  │              V1 INTELLIGENCE (imported as library)            │     │
│  │  models.py ──► lenses.py                                      │     │
│  │     │                                                         │     │
│  │     ├──► parsers.py ──► 17 format parsers                     │     │
│  │     ├──► resolver.py ──► entity extraction                    │     │
│  │     ├──► scrapers.py ──► source providers                     │     │
│  │     ├──► graph.py ──► EvidenceGraph                           │     │
│  │     ├──► inference.py ──► claims from signals                 │     │
│  │     ├──► contradiction.py ──► contradiction detection         │     │
│  │     └──► iris_audit.py ──► conversational audit               │     │
│  └──────────────────────────┬──────────────────────────────────┘     │
│                             │                                         │
│  ┌──────────────────────────┼──────────────────────────────────┐     │
│  │              STORAGE                                          │     │
│  │  ctx.db (SQLite)           v1.db (SQLite)                     │     │
│  │  ├── items                 ├── users                          │     │
│  │  ├── runs                  ├── sources                        │     │
│  │  ├── settings              ├── artifacts                      │     │
│  │  └── embeddings            ├── signals                        │     │
│  │                            ├── claims                         │     │
│  │                            ├── contradictions                 │     │
│  │                            ├── risks                          │     │
│  │                            ├── repairs                        │     │
│  │                            ├── reports                        │     │
│  │                            └── onboarding                     │     │
│  └──────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 8. Agent Interaction Matrix

How agents call each other (upstream → downstream dependencies):

```
                       ┌──────────┐
                       │ 17.Server│  ← routes EVERYTHING
                       └────┬─────┘
                            │
      ┌─────────────────────┼─────────────────────────┐
      │                     │                         │
      ▼                     ▼                         ▼
┌──────────┐         ┌──────────┐             ┌──────────┐
│ 1.Scan   │────────►│ 2.Ingest │───────────►│3.Cluster │
└──────────┘         └────┬─────┘             └────┬─────┘
                          │                        │
                    ┌─────┤                  ┌─────┤
                    │     │                  │     │
                    ▼     ▼                  ▼     ▼
              ┌──────────┐            ┌──────────┐ ┌──────────┐
              │11.Parser │            │ 4.Graph  │ │15.Dashboard│
              └──────────┘            └────┬─────┘ └──────────┘
                                          │
                    ┌─────────────────────┤
                    │                     │
                    ▼                     ▼
              ┌──────────┐          ┌──────────┐
              │12.Resolver│          │ 5.Signal │
              └──────────┘          └────┬─────┘
                                         │
                                         ▼
                                   ┌──────────┐     ┌──────────┐
                                   │10.Lens   │────►│ 6.Claim  │
                                   └──────────┘     └────┬─────┘
                                                         │
                              ┌──────────────────────────┤
                              │                          │
                              ▼                          ▼
                        ┌──────────┐               ┌──────────┐
                        │7.Contradiction│           │ 8.Risk   │
                        └────┬─────┘               └────┬─────┘
                             │                          │
                             └──────────┬───────────────┘
                                        │
                                        ▼
                                  ┌──────────┐
                                  │ 9.Repair │
                                  └────┬─────┘
                                       │
                         ┌─────────────┼─────────────┐
                         │             │             │
                         ▼             ▼             ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │13.Iris   │ │14.Export │ │16.View   │
                   └──────────┘ └──────────┘ └──────────┘
```

---

## 9. File Count Summary

| Agent | Files Owned | Total Lines (approx) |
|-------|------------|---------------------|
| 1. Scan | 3 | ~500 |
| 2. Ingest | 4 | ~1,500 |
| 3. Cluster | 6 | ~2,200 |
| 4. Graph | 4 | ~2,500 |
| 5. Signal | 4 | ~500 (net new logic) |
| 6. Claim | 2 | ~600 |
| 7. Contradiction | 2 | ~350 |
| 8. Risk | 2 | ~150 |
| 9. Repair | 2 | ~250 |
| 10. Lens | 2 | ~350 |
| 11. Parser | 1 | ~420 |
| 12. Resolver | 1 | ~385 |
| 13. Iris | 5 | ~1,200 |
| 14. Export | 5 | ~1,800 |
| 15. Dashboard | 4 | ~1,200 |
| 16. View | 3 | ~9,500 (app.js 8200 + css + html) |
| 17. Server | 13 | ~12,000 (server.py alone is 8112) |
| **Total** | **65** | **~35,000** |

---

*Document version: 1.0 — Wave 1 Architecture*
*Generated: 2026-06-06*
