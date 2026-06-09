# PIPELINE-PROGRESS.md
## Optic V1 — Pipeline Remediation Progress Tracker

**Created:** 2026-06-08
**Baseline:** 43% pipeline completion (PIPELINE-GAPS.md audit by DORO)
**Target:** 100% pipeline completion
**Last Git Check:** 2026-06-08 — HEAD at `9fccad7` (Optic V1.0 full platform)

---

## THE ACCEPTANCE RULE IS ABSOLUTE

> A feature is NOT complete until every applicable quality gate is satisfied.
> "It works on my machine" is not passing. "The demo looks good" is not passing.
> Complete means: **wired, traceable, recoverable, honest, and survivable under real conditions.**

Every stage below must pass all 8 Quality Gates before marked COMPLETE:
1. Architecture Integrity — access control, field allowlists
2. Mutation Safety — idempotency, concurrency, id validation  
3. AI-Native Safety — model output is untrusted, prompt injection hardened
4. UI Honesty — every state handled, no fake data, keyboard accessible
5. Operational Readiness — bootstrappable, deps correct, no hallucinated imports
6. Cost & Abuse Surface — rate limits, quotas, cleanup
7. Testing — real boundaries, bad input, races, timeouts
8. Self-Audit — document what you didn't build, no shiny distractions

---

## CURRENT PIPELINE COMPLETION MATRIX

```
Stage  1: Load config        ████████░░  80%  (config loaded, depth modes missing)
Stage  2: Consent filter      ░░░░░░░░░░   0%  (model exists, never enforced)       ← IN PROGRESS
Stage  3: Artifact selection  ░░░░░░░░░░   0%  (dummy artifacts fabricated)          ← IN PROGRESS
Stage  4: Evidence extraction ░░░░░░░░░░   0%  (parsers exist, never called)         ← IN PROGRESS
Stage  5: Signal extraction   ██████░░░░  60%  (basic signals, detector package unused) ← IN PROGRESS
Stage  6: Audience application████████░░  85%  (all lenses applied, but lens set wrong) ← IN PROGRESS
Stage  7: Inference cards     ████████░░  80%  (cards generated, evidence quality low)
Stage  8: Contradiction detect████░░░░░░  40%  (engine solid, 3/5 methods dead)
Stage  9: Risk mapping        ██░░░░░░░░  20%  (3 hardcoded risks)                  ← IN PROGRESS
Stage 10: Repair generation   ██████░░░░  65%  (generates, but shallow)
Stage 11: Report assembly     ██████░░░░  60%  (snapshot created, sections incomplete)
Stage 12: Graph projection    ░░░░░░░░░░   0%  (graph class exists, never wired)    ← IN PROGRESS
Stage 13: Iris context index  ████░░░░░░  40%  (queryable, not indexed during audit)
Stage 14: Completion          ████████░░  75%  (summary returned, no error tracking)

OVERALL PIPELINE SCORE:  43%  (weighted average) → TARGET: 100%
```

---

## REMEDIATION TRACKER

### C1 — Stage 2: Consent Filter
| Field | Value |
|-------|-------|
| **Assigned Agent** | optic-bolt |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | CRITICAL — violates Invariant #2 (Consent-Scoped) |
| **Files** | `backend/src/ctxorg/server.py` (`run_audit()`), `backend/src/optic/v1/models.py` (ConsentReceipt) |
| **Gap** | ConsentReceipt model fully defined but `run_audit()` never queries `consent_receipts`. Every source treated as consented. |
| **Required** | Query `consent_receipts` before audit. Exclude sources with `revoked_at` set or scope missing `infer`. Enforce `cloud_allowed`. |
| **Verification** | Run audit with mixed consent states → only consented sources appear in evidence. Audit with all-revoked sources → zero artifacts. |
| **Quality Gates** | Gates 1 (access control for consent data), 2 (idempotent consent checks), 7 (test revoked/missing/partial consent) |

### C2 — Stage 3-4: Artifact Selection + Evidence Extraction
| Field | Value |
|-------|-------|
| **Assigned Agents** | optic-nova, optic-vault |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | CRITICAL — real artifacts never loaded; evidence extraction entirely bypassed |
| **Files** | `backend/src/ctxorg/server.py` (lines 1344-1353 dummy Artifacts, line 1387-1388 empty arrays), `backend/src/optic/v1/parsers.py` (ParserRegistry), `backend/src/ctxorg/startup.py` (_seed_from_scan), `backend/src/ctxorg/extract.py` |
| **Gap (Stage 3)** | artifacts table has real scan data, but `run_audit()` fabricates dummy Artifacts from workstream metadata. Real file paths and hashes never loaded. |
| **Gap (Stage 4)** | 17 format parsers in ParserRegistry exist but never called. Workstream summaries used as proxies for evidence. No ParsedSpan objects ever created. |
| **Required** | Load artifacts from artifacts table in `run_audit()`. Call ParserRegistry against real files. Create ParsedSpan objects. Wire spans into claims as evidence. Apply evidence quality labels per hyperdoc §11. |
| **Verification** | Audit output shows claims citing real file:line evidence. ParsedSpan objects stored in DB. Evidence quality labels populated. |
| **Quality Gates** | Gates 1 (artifact access control), 3 (parser output is untrusted input), 5 (parser deps), 7 (empty artifacts, malformed files, large files) |

### C3 — Audience Lenses: Fix Mismatch
| Field | Value |
|-------|-------|
| **Assigned Agent** | optic-aria |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | CRITICAL — 3 doctrinally-required lenses missing, 3 code lenses have no doctrinal basis |
| **Files** | `backend/src/optic/v1/lenses.py`, `backend/src/optic/v1/server.py` (line 8986 limits to 4 lenses) |
| **Gap** | Sacred texts require: Privacy, Platform, Search, Institution. Code has: admissions (not in texts), customer (not in texts), future_agent (not in texts). Missing: Privacy, Search, Institution. Platform named ad_platform. |
| **Required** | Add Privacy, Search, Institution lenses. Rename ad_platform → Platform. Remove or re-theme admissions → Institution. Remove customer, future_agent (or mark as non-canonical extras). Fix the 4-lens cap in ctxorg bridge. |
| **Verification** | `AUDIENCE_LENSES` dict contains exactly: Recruiter, Investor, Collaborator, Creator, Privacy, Platform, Search, Institution, Stranger. All 9 applied during audit. |
| **Quality Gates** | Gates 1 (lens definitions validated), 4 (UI shows all 9 lenses), 8 (non-canonical lenses documented or removed) |

### H2 — Stage 5: Signal Extraction — Wire Detector Package
| Field | Value |
|-------|-------|
| **Assigned Agent** | optic-vault |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | HIGH — signal package (detectors.py, ml_detector.py, auditor.py) completely disconnected |
| **Files** | `backend/src/optic/v1/signal/detectors.py`, `backend/src/optic/v1/signal/ml_detector.py`, `backend/src/optic/v1/signal/auditor.py`, `backend/src/ctxorg/server.py` (`_workstream_to_signals`) |
| **Gap** | `optic/signal/` package never imported or called by V1 audit pipeline. Only 4 basic signal types from workstream stats. |
| **Required** | Import PatternDetector, MLAuditor. Run against parsed artifact content. Generate rich signal categories beyond the current 4. Wire detectors into `run_audit()`. |
| **Verification** | Signal output includes pattern-detected signals and ML-detected signals. Signal diversity > 10 categories. Detector results stored in signals table. |
| **Quality Gates** | Gates 3 (ML output is untrusted — validate before storage), 5 (ML deps correct), 7 (test with empty content, binary files, non-text) |

### C5 — Stage 8: Contradiction Detection — Wire EntityResolver
| Field | Value |
|-------|-------|
| **Assigned Agent** | *Depends on optic-vault (entities fed from parsed artifacts)* |
| **Status** | 🟡 BLOCKED — waiting on Stage 3-4 completion |
| **Started** | — |
| **Criticality** | CRITICAL — 3 of 5 contradiction detection methods receive empty inputs |
| **Files** | `backend/src/optic/v1/contradiction.py`, `backend/src/optic/v1/resolver.py`, `backend/src/ctxorg/server.py` (line 1387-1388) |
| **Gap** | EntityResolver (385 lines) never called. `run_audit()` passes `[]` for artifacts and entities to ContradictionEngine. 3 methods dead: timeline_conflicts, stale_context, profile_mismatches. |
| **Required** | Call EntityResolver.resolve() during audit. Pass real artifacts and resolved entities to ContradictionEngine.run_full_audit(). |
| **Verification** | All 5 contradiction methods return results. Contradiction count > 0 for real-world data. EntityResolver output logged. |
| **Quality Gates** | Gates 1 (entity resolution validation), 7 (test with conflicting data, identical data, empty data) |

### C4 — Stage 12: Graph Projection — Wire EvidenceGraph
| Field | Value |
|-------|-------|
| **Assigned Agent** | optic-pipe |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | CRITICAL — EvidenceGraph fully built (492 lines) but never instantiated in audit |
| **Files** | `backend/src/optic/v1/graph.py`, `backend/src/ctxorg/server.py` (`/api/v1/graph/evidence` endpoint), `backend/src/ctxorg/server.py` (`run_audit()`) |
| **Gap** | EvidenceGraph class with BFS pathfinding, subgraph export, contradiction queries. 25 node types, 20 edge types. Not instantiated during audit. Graph endpoint exists but returns empty. |
| **Required** | Instantiate EvidenceGraph in `run_audit()`. Add nodes for every artifact, claim, contradiction, risk, repair, signal, lens. Add typed edges connecting them. Wire graph data to `/api/v1/graph/evidence` endpoint. |
| **Verification** | `/api/v1/graph/evidence` returns populated graph. Node count > 0. Edge count > 0. BFS pathfinding returns paths between related nodes. |
| **Quality Gates** | Gates 1 (graph node validation), 2 (idempotent graph operations), 7 (test graph with empty audit, single-claim audit, full audit) |

### H1 — Stage 9: Risk Mapping — Dynamic Risk Engine
| Field | Value |
|-------|-------|
| **Assigned Agent** | optic-sage |
| **Status** | 🔴 IN PROGRESS |
| **Started** | 2026-06-08 |
| **Criticality** | HIGH — risks hardcoded, not derived from claims/contradictions |
| **Files** | `backend/src/ctxorg/server.py` (lines 1405-1412 hardcoded risks), `backend/src/optic/v1/models.py` (RiskFlag model, 23 RiskCategory enums) |
| **Gap** | 3 hardcoded generic risks. No risk derivation from contradictions, exposures, or signals. 23 RiskCategory enums defined but only ~3 used. |
| **Required** | Build risk engine that maps: contradictions → risks, stale context detections → risks, exposure records → risks. Use all applicable RiskCategory enums. Wire into `run_audit()` replacing hardcoded block. |
| **Verification** | Risk output varies with input data. Risk count > 3 for real audits. Each risk cites its source (contradiction ID, exposure record, signal ID). Risk categories drawn from full enum set. |
| **Quality Gates** | Gates 3 (risk derivations validated), 7 (test no-contradiction audit → zero risks, many-contradiction audit → proportional risks) |

### Stage 10: Repair Generation — Deepen
| Field | Value |
|-------|-------|
| **Assigned Agent** | *TBD — may be covered by optic-sage work* |
| **Status** | 🟡 PENDING — dependent on Stages 5, 8, 9 |
| **Started** | — |
| **Criticality** | MEDIUM — repairs functional but shallow |
| **Files** | `backend/src/ctxorg/server.py` (`_generate_repairs` lines 1228-1299), `backend/src/optic/v1/models.py` (RepairAction) |
| **Gap** | One repair per contradiction, one per high-severity card, 3 generic fallbacks. No workstream-specific repairs. No before/after_measurement populated. |
| **Required** | Derive repairs from risk flags. Generate workstream-specific repairs. Populate before_measurement and after_measurement. Add repair dependency chains. |
| **Verification** | Repair output includes risk-derived repairs, workstream-specific actions. Measurements populated. Repair count scales with audit complexity. |
| **Quality Gates** | Gates 1 (repair validation), 2 (idempotent repair generation), 7 (test empty audit, full audit) |

### Stage 1: Load Config — Depth Modes
| Field | Value |
|-------|-------|
| **Assigned Agent** | *TBD* |
| **Status** | 🟡 PENDING |
| **Started** | — |
| **Criticality** | MEDIUM — no Quick/Standard/Deep depth modes |
| **Files** | `backend/src/ctxorg/server.py` (AuditMode enum), `backend/src/optic/v1/models.py` |
| **Gap** | Hyperdoc §12 requires Quick/Standard/Deep depth modes. None implemented. |
| **Required** | Add Depth enum (Quick/Standard/Deep). Quick: basic signals only. Standard: full pipeline. Deep: extended ML + graph analysis. Wire into audit config. |
| **Verification** | Quick audit < 5s, Standard audit < 30s, Deep audit runs full pipeline with ML. |
| **Quality Gates** | Gates 4 (UI shows depth options), 6 (Deep mode rate-limited) |

### Stage 11: Report Assembly — Complete Sections
| Field | Value |
|-------|-------|
| **Assigned Agent** | *TBD* |
| **Status** | 🟡 PENDING — dependent on Stages 5-9, 12 |
| **Started** | — |
| **Criticality** | MEDIUM — report sections incomplete |
| **Files** | `backend/src/ctxorg/server.py` (`run_audit()` lines 1449-1472), `backend/src/optic/v1/models.py` (Report model) |
| **Gap** | Only 3 report sections. Missing: source ledger, confidence distribution, linked IDs. |
| **Required** | Add per-source breakdown. Add confidence band statistics. Link report sections to cards/risks/repairs by ID. |
| **Verification** | Report JSON includes `source_ledger`, `confidence_distribution`, linked entity IDs. |
| **Quality Gates** | Gates 4 (UI renders full report), 7 (test report with 0 items, 1000 items) |

### Stage 13: Iris Context Indexing — Index During Audit
| Field | Value |
|-------|-------|
| **Assigned Agent** | *TBD* |
| **Status** | 🟡 PENDING — dependent on Stages 3-9 |
| **Started** | — |
| **Criticality** | HIGH — Iris queries DB on-demand but no indexing step during audit |
| **Files** | `backend/src/optic/v1/iris_audit.py`, `backend/src/ctxorg/server.py` |
| **Gap** | IrisAuditChat class exists with DeepSeek integration but no indexing occurs during audit. No "last indexed" timestamp. |
| **Required** | Add indexing step to audit pipeline that pre-computes context for Iris. Store "last indexed" timestamp. |
| **Verification** | Iris responses include freshly indexed audit context. `last_indexed_at` timestamp updated after each audit. |
| **Quality Gates** | Gates 3 (DeepSeek output is untrusted), 6 (rate limits on LLM calls), 7 (test with empty DB) |

### Stage 14: Completion — Error Tracking
| Field | Value |
|-------|-------|
| **Assigned Agent** | *TBD* |
| **Status** | 🟡 PENDING |
| **Started** | — |
| **Criticality** | LOW — no per-stage error tracking |
| **Files** | `backend/src/ctxorg/server.py` (`run_audit()`), `backend/src/optic/v1/models.py` |
| **Gap** | If stage fails, exception caught but continues silently. No `audit_state` table. |
| **Required** | Add per-stage error collection. Add `audit_state` table (running/completed/failed with stage detail). Report failures in summary. |
| **Verification** | Failed stage produces error entry in audit output. `audit_state` reflects actual pipeline state. |
| **Quality Gates** | Gates 2 (state transitions atomic), 7 (test stage failure at every stage) |

---

## CROSS-CUTTING TASKS

| Task | Agent | Status | Description |
|------|-------|--------|-------------|
| QA Verify | optic-hawk | 🔴 IN PROGRESS | Run full Quality Gate verification on all fixed stages |
| Design Polish | optic-pixel | 🔴 IN PROGRESS | Ensure white frost-glass aesthetic consistency across all modes |
| Dead Code Prune | optic-lint | 🔴 IN PROGRESS | Remove unused code (detectors, parsers, graph made reachable or removed) |

---

## REMEDIATION DEPENDENCY GRAPH

```
Stage 3-4 (Artifacts+Evidence) ──┬── Stage 5 (Signals) ──┬── Stage 8 (Contradictions)
                                 │                       │
Stage 6 (Lenses)                 │                       ├── Stage 9 (Risks)
                                 │                       │
Stage 2 (Consent)                │                       └── Stage 10 (Repairs)
                                 │                                │
                                 ├── Stage 12 (Graph) ────────────┤
                                 │                                │
                                 └── Stage 11 (Report) ───────────┘
                                          │
Stage 1 (Depth Modes) ────────────────────┤
                                          │
Stage 13 (Iris Index) ────────────────────┤
                                          │
Stage 14 (Error Tracking) ────────────────┘
```

**Critical path:** Stage 3-4 → Stage 5 → Stage 8 → Stage 9 → Stage 10/11 → Complete

---

## GIT CHANGE LOG

| Timestamp | Agent | Stage | Files Changed | Commit |
|-----------|-------|-------|---------------|--------|
| 2026-06-08 | — | — | Baseline at `9fccad7` | — |

---

## HOW TO UPDATE

1. Run: `cd /Users/ahmedm/Developer/Projects/optic && git log --oneline --since="2 minutes ago"`
2. For each new commit, identify which stage it addresses
3. Update the Git Change Log above
4. If a stage's verification criteria are met, update its status to ✅ COMPLETE
5. Update the completion matrix bar

---

*Tracker maintained by Clio (Manifold Evaluation Metric Lead). THE ACCEPTANCE RULE IS ABSOLUTE.*
