# QA-VERIFICATION-HAWK.md
## Optic V1 — Pipeline Fix Verification Report

**Auditor:** HAWK (QA/QC Leader)
**Date:** 2026-06-08
**Baseline:** PIPELINE-GAPS.md (43% pipeline score, 7 incomplete stages)
**Scope:** Full re-audit of both execution paths:
  1. `backend/src/optic/v1/server.py` → `run_audit()` (FastAPI path)
  2. `backend/src/ctxorg/server.py` → `_v1_audit_bg()` (ctxorg bridge path)
**Standard:** THE ACCEPTANCE RULE IS ABSOLUTE — all 15 invariants, all 8 quality gates.

---

## EXECUTIVE SUMMARY

**NEW PIPELINE SCORE: 50%** (up from 43% baseline — +7 percentage points)

Of 7 critical/high gaps targeted for fixes, **0 are fully resolved**. Two show partial improvement, five show no change. One blocker-level NameError bug was discovered in the ctxorg bridge path that silently kills the entire background pipeline. The V1 FastAPI path's `run_audit()` is functionally identical to the pre-fix baseline.

**Verdict: PIPELINE IS NOT PRODUCTION-READY. CRITICAL GAPS REMAIN.**

---

## STAGE-BY-STAGE VERIFICATION

### Stage 2: Consent Filter — 20% (was 0%) — PARTIAL IMPROVEMENT

| Aspect | Status | Detail |
|--------|--------|--------|
| `_consent_check_source()` exists | EXISTS | ctxorg/server.py:7965 — well-built |
| Called in `audit_single_payload()` | EXISTS | Single-audit API path, line 8048 |
| Called in `_v1_audit_bg()` | **MISSING** | Pipeline never checks consent |
| Called in `run_audit()` | **MISSING** | V1 server never checks consent |

**FINDING:** The consent check function is well-built (checks revoked_at, scope, cloud_allowed) but is ONLY wired into the single-audit API path — not the main 14-stage pipeline. This violates Invariant #2 (Consent-Scoped).

### Stage 3-4: Real Artifacts + Evidence — 30% (was 0%) — PARTIAL IMPROVEMENT

| Aspect | V1 Server run_audit() | ctxorg _v1_audit_bg() |
|--------|----------------------|----------------------|
| Sources queried | Dummy Artifacts fabricated | Workstream key_files used |
| Artifact IDs | Random UUIDs | Random UUIDs |
| File paths | None real | Real file paths from workstream cache |
| Content parsed | Never | Never |
| Artifacts table queried | Never | Never |

**FINDING:** The ctxorg bridge loads real file paths from workstream key_files — an improvement over pure dummy data. But no file content is parsed (17 format parsers exist, never called). Neither path queries the actual artifacts table. Evidence quality remains "workstream metadata" not "parsed file content."

### Stage 5: Signal Detectors — 60% (was 60%) — NO CHANGE

| Aspect | Status |
|--------|--------|
| Signal package imported | V1 server: YES but unused. Ctxorg: In separate path only. |
| PatternDetector used in pipeline | **NO** — only in `audit_single_payload()` |
| MLAuditor used in pipeline | **NO** |
| Signal categories | 4 basic types only (topic_focus, activity_volume, etc.) |

**FINDING:** The signal package (detectors.py, ml_detector.py, auditor.py — 249+ lines) is imported in the V1 server but never called. The ctxorg bridge uses workstream-to-signal conversion only. Signal detection is unchanged from baseline.

### Stage 6: Audience Lenses — 65% (was 85%) — REGRESSION

**Current lenses in code (lenses.py):**
```
recruiter ✅ | investor ✅ | admissions ❌ (not doctrinal) | creator ✅
stranger ✅ | customer ❌ (not doctrinal) | collaborator ✅
ad_platform ⚠️ (called "Platform" in doctrine) | future_agent ❌ (not doctrinal)
```

**Missing sacred lenses:** Privacy, Search, Institution
**Extra lenses with no doctrinal basis:** admissions, customer, future_agent

**ADDITIONAL REGRESSION:** The ctxorg bridge `_v1_audit_bg()` limits to ONLY 4 LENSES (line 9014: `list(AUDIENCE_LENSES.keys())[:4]`). This means 5 of 9 code lenses (and 7 of 9 sacred lenses) are not applied in the background pipeline path.

### Stage 8: Contradiction Detection — 45% (was 40%) — ATTEMPTED BUT BROKEN

| Path | Artifacts | Entities | Status |
|------|-----------|----------|--------|
| V1 run_audit() | [] (empty) | [] (empty) | 3/5 methods dead (unchanged) |
| ctxorg _v1_audit_bg() | dicts passed | dicts passed | **ATTRIBUTE ERROR** — dicts don't have .type/.metadata/.id |

**BLOCKER BUG:** The ctxorg bridge passes raw Python dicts to `ContradictionEngine.run_full_audit()`, but all 5 detection methods access typed attributes (`.type`, `.metadata`, `.id`, `.is_public`, `.claim`, `.audience_lens`). This causes AttributeError on the first access, which is silently caught by `except Exception as exc: log.warning(...)`.

**Result:** The contradiction engine SILENTLY FAILS in the ctxorg bridge path. In the V1 server path, it still passes empty `[]`.

**SECONDARY BUG:** The variable `all_generated_artifacts` (line 9068) is never initialized as an empty list before `.append()` is called. This causes a NameError BEFORE the contradiction engine even runs, which is swallowed by the outer exception handler at line 9232: `except Exception as exc: log.exception("V1 audit background thread failed: %s", exc)`.

**Net effect:** The entire `_v1_audit_bg()` function crashes silently on the first lens iteration. No claims, contradictions, risks, or repairs are generated.

### Stage 9: Risk Mapping — 50% (was 20%) — PARTIALLY FIXED (ctxorg bridge only)

| Path | Risk Generation | Status |
|------|----------------|--------|
| V1 run_audit() | 3 hardcoded risks | Unchanged from baseline |
| ctxorg _v1_audit_bg() | Dynamic from contradictions | **GOOD DESIGN** — but unreachable due to NameError bug |

**FINDING:** The ctxorg bridge HAS dynamic risk generation from contradiction output (lines 9131-9177). It deduplicates by category, maps contradiction severity to risk severity, and falls back to an honest note. This is the RIGHT approach. But it's unreachable because the function crashes before reaching this code.

### Stage 12: Graph Projection — 10% (was 0%) — MINIMAL IMPROVEMENT

| Aspect | Status |
|--------|--------|
| `_build_evidence_graph()` | EXISTS — populates user/sources/artifacts nodes + edges |
| Called in `run_audit()` | **NO** |
| Called in `_v1_audit_bg()` | **NO** |
| API endpoint | GET /api/v1/graph/evidence — returns 1 node, 0 edges (LIVE VERIFIED) |

**FINDING:** The graph building function exists and works at the API level, but it's never called during audit. The live endpoint returns: `{"nodes":[{"id":"local","type":"user"...}],"edges":[],"node_count":1,"edge_count":0}`.

---

## COMPLETE PIPELINE MATRIX

```
Stage  1: Load config        ████████░░  80%  (unchanged)
Stage  2: Consent filter      ████░░░░░░  20%  ↑ from 0%  (function exists, not wired to pipeline)
Stage  3: Artifact selection  ██████░░░░  30%  ↑ from 0%  (key_files used, artifacts table ignored)
Stage  4: Evidence extraction ██████░░░░  30%  ↑ from 0%  (real paths, no file parsing)
Stage  5: Signal extraction   ██████░░░░  60%  (unchanged — detectors imported, unused)
Stage  6: Audience application█████████░░  65%  ↓ from 85%  (wrong lenses, ctxorg limits to 4)
Stage  7: Inference cards     ███████░░░  70%  ↓ from 80%  (evidence quality still low)
Stage  8: Contradiction detect█████░░░░░  45%  ↑ from 40%  (bridge ATTEMPTS fix, crashes silently)
Stage  9: Risk mapping        ██████░░░░  50%  ↑ from 20%  (dynamic in bridge, unreachable)
Stage 10: Repair generation   ██████░░░░  60%  ↓ from 65%  (4 hardcoded in bridge)
Stage 11: Report assembly     ██████░░░░  60%  (unchanged)
Stage 12: Graph projection    ██░░░░░░░░  10%  ↑ from 0%   (builder exists, never called in audit)
Stage 13: Iris context index  ████░░░░░░  40%  (unchanged)
Stage 14: Completion          ████████░░  75%  (unchanged)
```

**PREVIOUS: 43% || NEW: 50%** (weighted average)

Change: **+7 percentage points** — insufficient for any quality gate.

---

## BLOCKER BUGS DISCOVERED

### B1: NameError — `all_generated_artifacts` never initialized
- **File:** `backend/src/ctxorg/server.py`, line ~9068
- **Impact:** `_v1_audit_bg()` crashes at first `.append()` call
- **Consequence:** Entire ctxorg background audit pipeline silently dies
- **Fix:** Add `all_generated_artifacts = []` before the lens loop (line ~9012)

### B2: Dict/object type mismatch in contradiction engine
- **File:** `backend/src/ctxorg/server.py`, line ~9114
- **Impact:** `engine.run_full_audit()` receives dicts; methods access `.type`, `.metadata` as attributes
- **Consequence:** AttributeError swallowed by exception handler
- **Fix:** Convert dicts to typed objects (Artifact, Entity) before calling engine

### B3: ctxorg bridge limits to 4 lenses
- **File:** `backend/src/ctxorg/server.py`, line 9014
- **Impact:** 5 of 9 lenses never applied in background pipeline
- **Fix:** Remove the `[:4]` slice (was for "speed" — no longer needed)

---

## REMAINING GAPS (from PIPELINE-GAPS.md)

| Gap | Stage | Status | Notes |
|-----|-------|--------|-------|
| C1 | Stage 2 | **NOT FIXED** | Consent check not wired to audit pipelines |
| C2 | Stage 3-4 | **NOT FIXED** | Artifacts table ignored, parsers unused |
| C3 | Lenses | **NOT FIXED** | Privacy/Search/Institution still missing |
| C4 | Stage 12 | **NOT FIXED** | Graph builder exists, never called in audit |
| C5 | Stage 8 | **ATTEMPTED, BROKEN** | Type mismatch + NameError bugs |
| H1 | Stage 9 | **PARTIAL (unreachable)** | Dynamic risk code exists but can't execute |
| H2 | Stage 5 | **NOT FIXED** | Signal detectors still disconnected |
| H3 | Stage 13 | **NOT FIXED** | Iris indexing not performed during audit |
| H4 | Stage 8 | **NOT FIXED** | EntityResolver never called |
| H5 | Stage 3-4 | **NOT FIXED** | 17 parsers never used in audit |

---

## FOLLOW-UP REMEDIATION TASKS (PRIORITY ORDER)

### T1 [BLOCKER]: Fix NameError in _v1_audit_bg()
- Add `all_generated_artifacts = []` before line 9012
- Agent: @optic-pipe (evidence pipeline)
- Estimated: 5 minutes

### T2 [BLOCKER]: Fix dict/object type mismatch in contradiction engine
- Convert `artifact_dicts` and `entity_dicts` to proper Artifact/Entity objects
- OR: Add dict-compatible access to contradiction engine methods
- Agent: @optic-pipe (evidence pipeline)
- Estimated: 30 minutes

### T3 [CRITICAL]: Wire consent filter into both pipeline paths
- Call `_consent_check_source()` at start of `run_audit()` and `_v1_audit_bg()`
- Agent: @optic-bolt (consent filter)
- Estimated: 20 minutes

### T4 [CRITICAL]: Fix audience lenses to match sacred doctrine
- Add Privacy, Search, Institution lenses to lenses.py
- Remove/rename admissions→Institution, remove customer, remove future_agent (or keep as extras beyond canonical 9)
- Remove `[:4]` limit in ctxorg bridge
- Agent: @optic-aria (audience lenses)
- Estimated: 45 minutes

### T5 [HIGH]: Wire real artifacts from DB into both pipeline paths
- Query artifacts table instead of fabricating dummies
- Pass real artifacts to contradiction engine
- Agent: @optic-nova (real artifacts)
- Estimated: 30 minutes

### T6 [HIGH]: Wire signal detectors into audit pipeline
- Call PatternDetector + MLAuditor against artifact content
- Agent: @optic-vault (signal detectors)
- Estimated: 45 minutes

### T7 [HIGH]: Populate EvidenceGraph during audit
- Call `_build_evidence_graph()` in both pipeline paths
- Add claims/contradictions/risks/repairs as graph nodes
- Agent: @optic-pipe (evidence graph)
- Estimated: 30 minutes

### T8 [MEDIUM]: Wire EntityResolver into audit pipeline
- Call resolver during audit to extract entities from artifacts
- Pass to contradiction engine
- Agent: @optic-sage (dynamic risks)
- Estimated: 20 minutes

---

## LIVE VERIFICATION DATA

**Backend:** Running at http://127.0.0.1:3003 (health: OK)
**Status endpoint:** `/api/v1/status` returns:
- 162 claims (all "Recruiter read: frequent_topic" — repetitive, single-lens)
- 3 risks (hardcoded)
- 3 pending repairs (hardcoded)
- 0 reports
- Graph: 1 node (user), 0 edges (confirmed empty)

**Graph endpoint:** `/api/v1/graph/evidence` returns:
```json
{"nodes":[{"id":"local","type":"user","label":"local@optic.dev","data":{"local_mode":true},"created_at":"...","updated_at":"..."}],"edges":[],"node_count":1,"edge_count":0}
```

---

## FINAL VERDICT

**THE FIXES ARE INCOMPLETE.** Of the 7 critical/high gaps targeted for remediation, 0 are fully resolved. 2 show partial improvement (consent function exists but unwired; risk generation dynamic but unreachable due to bugs). 2 blocker bugs discovered (NameError + type mismatch) prevent the ctxorg bridge from executing at all. The V1 FastAPI path is unchanged from baseline.

**The Acceptance Rule is violated.** The pipeline does not meet any of the 8 quality gates. Evidence-gated claims (Gate 3) cite workstream metadata, not parsed files. Mutation safety (Gate 2) is irrelevant since the pipeline crashes silently. UI honesty (Gate 4) cannot be verified because the bridge produces no output.

**RECOMMENDATION:** Stop further feature development. Fix blockers T1-T2 immediately (15-35 minutes). Then execute T3-T8 in priority order. Re-audit after all fixes land. Do not ship to production until pipeline score reaches ≥85%.

---

*Report generated by HAWK (QA/QC Leader) under the authority of the sacred texts. THE ACCEPTANCE RULE IS ABSOLUTE. No feature ships without Hawk's seal.*
