# PIPELINE-GAPS.md
## Optic V1 — Evidence Pipeline Audit Report

**Auditor:** DORO (QA/QC, Junior Agent)
**Date:** 2026-06-08
**Scope:** `backend/src/optic/v1/` + ctxorg bridge at `backend/src/ctxorg/server.py`
**Authority:** Sacred texts — system prompt doctrine, `docs/optichyperdoc.rtf`, `WAVE1-ARCHITECTURE.md`
**Standard:** THE ACCEPTANCE RULE IS ABSOLUTE — every quality gate must be satisfied.

---

## EXECUTIVE SUMMARY

The V1 audit pipeline has **substantial structural gaps**. Of the 14 canonical pipeline stages, **7 are incomplete or entirely missing**. The 9 audience lenses **do not match the sacred texts** — 3 lenses from the doctrine are absent, and 3 lenses in code have no doctrinal basis. The contradiction engine exists but is called with empty artifacts/entities, neutering 3 of its 5 detection methods. Risk generation is hardcoded. The evidence graph is built but never wired into the audit pipeline. The parsers (17 formats) and signal detectors are built but disconnected.

**Criticality: HIGH. The pipeline is NOT production-ready per any quality gate.**

---

## VERIFICATION ITEM 1: 14-STAGE AUDIT PIPELINE — STAGE-BY-STAGE AUDIT

### Stage 1: Load config — PARTIAL PASS
| Aspect | Status | Location |
|--------|--------|----------|
| DB paths configured | EXISTS | `server.py:59-61` (DB_PATH from env), `ctxorg/server.py:8634-8655` (shared DB) |
| Audit mode selection | EXISTS | `server.py:1303-1309` (`/{mode}` param validated against AuditMode enum) |
| Source/workstream selection | PARTIAL | Only uses `_load_ctxorg_workstreams()` which caches; no per-audit config |
| Depth mode | MISSING | Hyperdoc §12 requires Quick/Standard/Deep; none implemented |
| User profile load | EXISTS | `_get_user(token)` returns user row |

**GAP: No configurable audit parameters (lens selection, workstream filter, depth mode).**

### Stage 2: Consent filter — MISSING
| Aspect | Status | Location |
|--------|--------|----------|
| Consent receipt model | EXISTS | `models.py:127-137` (ConsentReceipt dataclass) |
| Consent table in DB | EXISTS | `server.py:141-143` (consent_receipts table) |
| Consent check before audit | **MISSING** | `run_audit()` never queries consent_receipts |
| Consent enforcement | **MISSING** | No `scope`, `revoked_at`, or `cloud_allowed` checks |

**GAP: Consent model is fully defined but never enforced. Every source is treated as consented. This violates Invariant #2 (Consent-Scoped).**

### Stage 3: Artifact selection — MISSING
| Aspect | Status | Location |
|--------|--------|----------|
| Artifact table in DB | EXISTS | `server.py:144-148` |
| Real artifacts from scan | EXISTS | `startup.py:380-388` (`_seed_from_scan` populates artifacts table) |
| Artifact loading in audit | **MISSING** | `run_audit()` creates dummy `Artifact` objects on-the-fly (line 1344-1353) |
| File type filtering | **MISSING** | No filtering by extension, size, or freshness |
| Artifact limits | **MISSING** | No max artifact cap |

**GAP: The artifacts table has real scan data, but `run_audit()` ignores it entirely. It fabricates dummy Artifacts from workstream metadata. Real file paths and hashes are never loaded.**

### Stage 4: Evidence extraction — MISSING
| Aspect | Status | Location |
|--------|--------|----------|
| ParsedSpan model | EXISTS | `models.py:171-181` |
| Extract module (ctxorg) | EXISTS | `ctxorg/extract.py` (text extraction from files) |
| Parsers (17 formats) | EXISTS | `parsers.py:33-100` (ParserRegistry with 17 format handlers) |
| Evidence from files | **MISSING** | No parser is called during audit. Workstream summaries used as proxies. |
| Evidence quality labels | **MISSING** | Hyperdoc §11 requires labeling evidence quality; not implemented |
| ParsedSpan creation | **MISSING** | No spans are ever created or stored |

**GAP: Evidence extraction is entirely bypassed. Claims cite "workstream" as evidence, not actual files. The hyperdoc requires "parsed spans from file metadata, summaries, text snippets." None of this occurs.**

### Stage 5: Signal extraction — PARTIAL PASS
| Aspect | Status | Location |
|--------|--------|----------|
| Signal model | EXISTS | `models.py:197-205` |
| Workstream-to-signal conversion | EXISTS | `server.py:1175-1219` (`_workstream_to_signals`) |
| Signal DB storage | EXISTS | `server.py:1327-1333` (INSERT OR REPLACE) |
| Signal detectors (pattern, ML) | EXISTS | `signal/detectors.py` (249 lines), `signal/ml_detector.py`, `signal/auditor.py` |
| Detectors wired into audit | **MISSING** | `signal/` package is never imported or called by V1 audit pipeline |
| Rich signal categories | **MISSING** | Only 4 signal types: `frequent_topic`, `project_velocity`, `workstream_fragmentation`, `topic_focus` |

**GAP: Signal detection is shallow. The dedicated signal package (PatternDetector, MLAuditor) is completely disconnected. Only basic workstream statistics are converted to signals.**

### Stage 6: Audience application — PASS (with caveats)
| Aspect | Status | Location |
|--------|--------|----------|
| 9 lens configs loaded | EXISTS | `server.py:1340` (`for lens_id, lens in AUDIENCE_LENSES.items()`) |
| Per-lens claim generation | EXISTS | `InferenceCardGenerator(lens_id)` per lens |
| Lens filtering rules applied | EXISTS | `inference.py:120-126` (`_passes_lens_filter`) |
| Lens confidence rules | EXISTS | `inference.py:88-101` (`_compute_confidence`) |

**PASS: All loaded lenses are applied. However, see LENS MISMATCH below.**

### Stage 7: Inference card generation — PASS (with caveats)
| Aspect | Status | Location |
|--------|--------|----------|
| InferenceCardGenerator | EXISTS | `inference.py:18-296` |
| Evidence-gated generation | PASS | `_signal_to_claim` checks `min_evidence_count` |
| Confidence bands | PASS | LOW/MEDIUM/HIGH computed |
| Counterargument generation | PASS | `_add_counterargument` |
| Supporting/weakening evidence | PASS | UUIDs populated |
| Card DB storage | PASS | `server.py:1363-1376` |
| `not_a_verdict` flag | PASS | Always True |
| Reject unevidenced cards | PARTIAL | Claims generated even with dummy artifacts; `min_evidence_count=1` is trivial |

**GAP: Cards cite workstream-derived artifacts, not real files. Evidence links are UUIDs to fabricated objects.**

### Stage 8: Contradiction detection — PARTIAL FAIL
| Aspect | Status | Location |
|--------|--------|----------|
| ContradictionEngine | EXISTS | `contradiction.py:17-368` |
| 5 detection methods | EXISTS | `find_job_title_mismatches`, `find_timeline_conflicts`, `find_stale_context`, `find_profile_mismatches`, `find_claim_contradictions` |
| Triviality/dedup filtering | EXISTS | `_word_overlap_ratio`, `_opposition_in_difference`, `_canonical_key` |
| Called with empty artifacts | **FAIL** | `run_audit()` passes `[]` for artifacts (line 1387) |
| Called with empty entities | **FAIL** | `run_audit()` passes `[]` for entities (line 1388) |
| EntityResolver not wired | **MISSING** | `resolver.py` never called; no entities extracted |
| 3 detectors neutered | **FAIL** | `find_timeline_conflicts`, `find_stale_context`, `find_profile_mismatches` receive empty inputs → return [] |

**GAP: The contradiction engine is high-quality code, but 3 of 5 detection methods are silently disabled by receiving empty inputs. Only `find_job_title_mismatches` (works on claims alone) and `find_claim_contradictions` (works on claims alone) actually run.**

### Stage 9: Risk mapping — FAIL (hardcoded)
| Aspect | Status | Location |
|--------|--------|----------|
| RiskFlag model | EXISTS | `models.py:258-267` |
| 23 RiskCategory enums | EXISTS | `models.py:42-67` |
| Dynamic risk generation | **MISSING** | `run_audit()` hardcodes 3 risks (lines 1405-1412) |
| Risk from contradictions | **MISSING** | Contradictions found but not converted to risks |
| Risk from exposures | **MISSING** | Ctxorg exposures not mapped to RiskFlag objects |
| Risk-engine function | **MISSING** | No dedicated risk generator module |

**GAP: Risks are hardcoded: "Some workstreams may contain stale files", "Workstreams span multiple unrelated topics", "Some projects lack public documentation". These do not derive from actual signal/claim/contradiction data. The hyperdoc §15 requires a full risk engine mapping exposures + contradictions into RiskFlag objects with all 23 categories.**

### Stage 10: Repair generation — PARTIAL PASS
| Aspect | Status | Location |
|--------|--------|----------|
| RepairAction model | EXISTS | `models.py:271-295` |
| Priority formula | EXISTS | `impact × urgency × reversibility ÷ effort` |
| Generate from contradictions | PASS | `_generate_repairs` line 1228-1243 |
| Generate from cards | PASS | `_generate_repairs` line 1246-1262 |
| Generic fallback repairs | EXISTS | 3 hardcoded repairs (lines 1265-1290) |
| Deduplication | PASS | By title (line 1294-1299) |

**GAP: Repair generation is functional but shallow — it creates one repair per contradiction and one per high-severity card, plus 3 generic actions. No workstream-specific repairs. No repair dependency chains. No before/after_measurement.**

### Stage 11: Report assembly — PARTIAL PASS
| Aspect | Status | Location |
|--------|--------|----------|
| Report model | EXISTS | `models.py:314-330` |
| Snapshot creation | PASS | `run_audit()` lines 1449-1472 |
| Counts populated | PASS | claim/contradiction/risk/repair counts |
| Report sections | PARTIAL | Only 3 sections: scope, source_ledger, audience_summary |
| Source ledger | **MISSING** | Hyperdoc §17 requires per-source breakdown |
| Confidence distribution | **MISSING** | No confidence band statistics |
| Linked IDs in report | **MISSING** | Report stores raw UUIDs but doesn't link to cards/risks/repairs |

### Stage 12: Graph projection — MISSING
| Aspect | Status | Location |
|--------|--------|----------|
| EvidenceGraph class | EXISTS | `graph.py:41-492` |
| 25 node types | EXISTS | `graph.py:21-28` (NODE_TYPES) |
| 20 edge types | EXISTS | `graph.py:31-38` (EDGE_TYPES) |
| Graph wired to audit | **MISSING** | `EvidenceGraph` never instantiated in `run_audit()` |
| Graph API endpoint | EXISTS | `server.py:896` (`/api/v1/graph/evidence`) but returns empty |
| V1 overlay on topology | **MISSING** | Hyperdoc §18 requires connecting workstreams to cards/contradictions/risks/repairs |

**GAP: EvidenceGraph is a fully built, well-tested module (492 lines with BFS pathfinding, subgraph export, contradiction queries) but it is never called by the audit pipeline. The `/api/v1/graph/evidence` endpoint exists but returns minimal data.**

### Stage 13: Iris context indexing — PARTIAL PASS
| Aspect | Status | Location |
|--------|--------|----------|
| IrisAuditChat class | EXISTS | `iris_audit.py:39-515` |
| DB context gathering | EXISTS | `_gather_context` (queries claims, signals, contradictions) |
| DeepSeek integration | EXISTS | `_try_deepseek` |
| Ollama fallback | EXISTS | `_try_ollama` |
| Deterministic fallback | EXISTS | `_fallback` |
| Indexed during audit | **MISSING** | Iris queries DB on-demand but no indexing step during audit |
| Audit context freshness | **MISSING** | No "last indexed" timestamp |

### Stage 14: Completion — PASS
| Aspect | Status | Location |
|--------|--------|----------|
| Summary response | PASS | `run_audit()` returns counts + report_id + snapshot_id |
| Error per-stage reporting | **MISSING** | If lens generation fails, exception caught but continues silently |
| Audit state persistence | PARTIAL | Report stored, but no `audit_state` table tracking running/completed/failed |

---

## VERIFICATION ITEM 2: 9 AUDIENCE LENSES — MISMATCH

### Sacred Text Lenses (from system prompt doctrine):
| # | Lens | In Code? |
|---|------|----------|
| 1 | Recruiter | ✅ `recruiter` — match |
| 2 | Investor | ✅ `investor` — match |
| 3 | Collaborator | ✅ `collaborator` — match |
| 4 | Creator | ✅ `creator` — match |
| 5 | **Privacy** | ❌ MISSING — no privacy lens |
| 6 | **Platform** | ⚠️ Partial — `ad_platform` exists but named differently |
| 7 | **Search** | ❌ MISSING — no search lens |
| 8 | **Institution** | ❌ MISSING — `admissions` is similar but narrower |
| 9 | Stranger | ✅ `stranger` — match |

### Code Lenses (from `lenses.py`):
| # | Lens | In Sacred Texts? |
|---|------|-----------------|
| 1 | recruiter | ✅ |
| 2 | investor | ✅ |
| 3 | admissions | ❌ NOT in sacred texts |
| 4 | creator | ✅ |
| 5 | stranger | ✅ |
| 6 | customer | ❌ NOT in sacred texts |
| 7 | collaborator | ✅ |
| 8 | ad_platform | ⚠️ Partial (called "Platform" in texts) |
| 9 | future_agent | ❌ NOT in sacred texts |

**GAP: 3 sacred lenses missing (Privacy, Search, Institution). 3 code lenses have no doctrinal basis (admissions, customer, future_agent). The hyperdoc §13 explicitly mentions "Privacy lens values exposure, location leakage, sensitive traces, hidden metadata, account linkage, and removability" — confirming the Privacy lens is doctrinally required.**

---

## VERIFICATION ITEM 3: EVIDENCE GRAPH NODES — PARTIAL PASS

### Node Types (from `graph.py`):
25 node types defined in `NODE_TYPES`:
`user, account, handle, email, domain, organization, school, employer, project, repository, post, article, resume_item, calendar_event, email_thread, search_result, image, document, artifact, parsed_span, topic, skill, credential, location, timeline_period, signal, claim, audience, risk, contradiction, repair, source_gap, consent_receipt, report_snapshot`

### Edge Types (from `graph.py`):
20 edge types defined in `EDGE_TYPES`:
`authored, owned, mentions, supports, weakens, contradicts, outdated_by, context_for, associated_with, same_as, maybe_same_as, located_at, worked_at, studied_at, contributed_to, inferred_from, visible_to, risky_for, repaired_by, missing_context_for, derived_from, imported_under, revoked_by, included_in_report`

**Assessment:** The type system is comprehensive and well-designed. Nodes and edges cover all entities in the audit pipeline. Validation is strict (`_require_type` enforces frozenset membership).

**GAP: Types are defined but graph is never populated during audit. No `add_node`/`add_edge` calls occur in `run_audit()` or `_v1_audit_bg()`. The graph is structurally complete but operationally empty.**

---

## VERIFICATION ITEM 4: CONTRADICTION DETECTION — PARTIAL FAIL

### Detection Methods Status:

| Method | Input | Status in `run_audit()` |
|--------|-------|------------------------|
| `find_job_title_mismatches` | claims, entities | ✅ Runs (claims populated, entities=[]) |
| `find_timeline_conflicts` | artifacts, claims | ❌ NEUTERED (artifacts=[]) |
| `find_stale_context` | artifacts | ❌ NEUTERED (artifacts=[]) |
| `find_profile_mismatches` | entities | ❌ NEUTERED (entities=[]) |
| `find_claim_contradictions` | claims | ✅ Runs (claims populated) |

### Quality Checks:
| Check | Status |
|-------|--------|
| Triviality filter (>85% overlap) | ✅ Implemented |
| Opposition-in-difference | ✅ Implemented |
| Cross-category dedup | ✅ Implemented |
| Canonical key dedup | ✅ Implemented |
| Severity recalibration | ✅ Implemented |
| End-to-end test | ❌ Only 2 of 5 methods execute |

**GAP: The contradiction engine is internally sound but externally starved. The EntityResolver (`resolver.py`, 385 lines) is never called. Artifacts from the real scan are never loaded into the contradiction engine.**

---

## VERIFICATION ITEM 5: REPAIR GENERATION → SIGNAL ENGINE — PARTIAL PASS

### Repair Pipeline Connection:
```
signals → claims → contradictions → repairs
   ✓          ✓            ✓             ✓
(weak)    (partial)    (partial)     (shallow)
```

### Specific Gaps:
1. **Repair from risk flags**: `_generate_repairs` receives risks but only uses contradictions + cards for repair generation. The risk list passed to it is unused for repair derivation.
2. **Workstream-specific repairs**: No workstream analysis drives repair suggestions (e.g., "consolidate fragmented project folders" is a generic catch-all, not derived from actual fragmentation detection).
3. **Before/after measurement**: The `before_measurement` and `after_measurement` fields on RepairAction are never populated.
4. **Signal engine connection**: The `optic/signal/` package (detectors.py, ml_detector.py, auditor.py) is completely disconnected from repair generation. Repairs should be derivable from signal detections.

---

## SUMMARY: ALL GAPS RANKED BY SEVERITY

### CRITICAL (blocks production):

| Gap | Stage | Description |
|-----|-------|-------------|
| **C1** | Stage 2 | Consent filter entirely missing — violates Invariant #2 |
| **C2** | Stage 3-4 | Real artifacts never loaded; evidence extraction skipped |
| **C3** | Audience Lenses | 3 doctrinally-required lenses missing (Privacy, Search, Institution) |
| **C4** | Stage 12 | Evidence graph exists but never populated during audit |
| **C5** | Stage 8 | Contradiction engine receives empty artifacts/entities — 3 of 5 methods dead |

### HIGH (severely degrades output quality):

| Gap | Stage | Description |
|-----|-------|-------------|
| **H1** | Stage 9 | Risks hardcoded, not derived from claims/contradictions |
| **H2** | Stage 5 | Signal package (detectors.py, auditor.py) disconnected from pipeline |
| **H3** | Stage 13 | Iris context indexing not performed during audit |
| **H4** | Stage 8 | EntityResolver never called; entities never extracted |
| **H5** | Stage 3-4 | 17 format parsers exist but never used in audit |

### MEDIUM (quality/UX degraded):

| Gap | Stage | Description |
|-----|-------|-------------|
| **M1** | Stage 1 | No per-audit config (lens selection, depth mode) |
| **M2** | Stage 11 | Report sections incomplete (no confidence distribution, no source ledger) |
| **M3** | Stage 10 | Repairs shallow — one per contradiction, plus generic fallbacks |
| **M4** | Stage 1 | No Quick/Standard/Deep depth modes |
| **M5** | Stage 7 | `min_evidence_count=1` is trivially passable |

### LOW (nice-to-have):

| Gap | Stage | Description |
|-----|-------|-------------|
| **L1** | Stage 14 | No per-stage error tracking during audit |
| **L2** | Stage 10 | `before_measurement`/`after_measurement` never populated |
| **L3** | All | No audit_state table (running/completed/failed with stage detail) |
| **L4** | Stage 6 | Lenses limited to 4 in ctxorg bridge `_v1_audit_bg` (line 8986) |

---

## PIPELINE STAGE COMPLETION MATRIX

```
Stage  1: Load config        ████████░░  80%  (config loaded, depth modes missing)
Stage  2: Consent filter      ░░░░░░░░░░   0%  (model exists, never enforced)
Stage  3: Artifact selection  ░░░░░░░░░░   0%  (dummy artifacts fabricated)
Stage  4: Evidence extraction ░░░░░░░░░░   0%  (parsers exist, never called)
Stage  5: Signal extraction   ██████░░░░  60%  (basic signals, detector package unused)
Stage  6: Audience application████████░░  85%  (all lenses applied, but lens set wrong)
Stage  7: Inference cards     ████████░░  80%  (cards generated, evidence quality low)
Stage  8: Contradiction detect████░░░░░░  40%  (engine solid, 3/5 methods dead)
Stage  9: Risk mapping        ██░░░░░░░░  20%  (3 hardcoded risks)
Stage 10: Repair generation   ██████░░░░  65%  (generates, but shallow)
Stage 11: Report assembly     ██████░░░░  60%  (snapshot created, sections incomplete)
Stage 12: Graph projection    ░░░░░░░░░░   0%  (graph class exists, never wired)
Stage 13: Iris context index  ████░░░░░░  40%  (queryable, not indexed during audit)
Stage 14: Completion          ████████░░  75%  (summary returned, no error tracking)

OVERALL PIPELINE SCORE:  43%  (weighted average)
```

---

## RECOMMENDED REMEDIATION ORDER

1. **Fix the audience lenses** — Add Privacy, Search, Institution lenses to `lenses.py`. Remove or re-theme admissions → Institution, customer, and future_agent (or keep as optional beyond the canonical 9).

2. **Wire real artifacts** — In `run_audit()`, load artifacts from the artifacts table instead of fabricating dummies. Pass them to the contradiction engine.

3. **Wire EntityResolver** — Call `EntityResolver.resolve()` during audit and pass entities to `ContradictionEngine.run_full_audit()`.

4. **Implement consent filter** — Before audit, query `consent_receipts` and exclude sources with `revoked_at` set or scope missing `infer`.

5. **Wire the evidence graph** — After generating claims/contradictions/risks/repairs, populate `EvidenceGraph` with typed nodes and edges.

6. **Connect signal detectors** — Import `optic.signal.detectors` and `optic.signal.auditor` and run them against parsed artifact content.

7. **Dynamic risk generation** — Replace hardcoded risks with a risk engine that maps contradictions, stale context detections, and exposure records into RiskFlag objects.

8. **Wire format parsers** — During evidence extraction, use `ParserRegistry` to parse actual file content from scanned artifacts.

---

*Report generated by DORO (QA/QC Junior Agent) under the authority of the sacred texts. THE ACCEPTANCE RULE IS ABSOLUTE.*
