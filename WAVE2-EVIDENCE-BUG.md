# Wave 2 Evidence Bug — 0 Claims Root Cause

## Summary

The `run_audit()` function generates **zero claims** when the total signal count exceeds 30. The root cause is a **slice mismatch** between where artifact IDs are assigned and which signals are passed to the inference engine.

## Bug Location

**File:** `backend/src/optic/v1/server.py`

### Slice 1 — artifact ID assignment (lines 1118–1119)
```python
for s in all_signals[-10:]:          # ← updates only the LAST 10 signals
    s.source_artifact_ids = artifact_ids
```

### Slice 2 — signals passed to generator (line 1121)
```python
lens_claims = gen.generate_claims(all_signals[:30], selected_artifacts)
                                   # ↑ passes only the FIRST 30 signals
```

## Why This Produces 0 Claims

`_workstream_to_signals()` (line 938) creates each signal with a freshly generated random UUID:
```python
source_artifact_ids=[uuid4()]   # lines 954, 966, 977
```

These random UUIDs never match the freshly-created `selected_artifacts` UUIDs (generated at line 1106 inside the lens loop). Signals must have their `source_artifact_ids` overwritten to match `selected_artifacts` — but only the **last 10** signals get that treatment (line 1118).

When the **signal count > 30**, the two slices are completely disjoint:

| Signal count | `all_signals[-10:]` indices | `all_signals[:30]` indices | Overlap? |
|---|---|---|---|
| 12 | 2–11 | 0–11 | ✅ 10 signals overlap |
| 25 | 15–24 | 0–24 | ✅ 10 signals overlap |
| 31 | 21–30 | 0–29 | ❌ **ZERO overlap** |
| 60 | 50–59 | 0–29 | ❌ **ZERO overlap** |

With 20 workstreams (line 1084: `workstreams[:20]`), each producing 2–3 signals, the total is **40–60 signals** — well above the 30-signal breakpoint.

## How the Null-Path Executes

In `inference.py`, `_signal_to_claim()` line 50–56:

```python
relevant_artifacts = [a for a in artifacts if a.id in signal.source_artifact_ids]
#                     ↑ artifacts = selected_artifacts (fresh UUIDs)
#                     ↑ signal.source_artifact_ids = stale random UUIDs from _workstream_to_signals()
#                     → relevant_artifacts = [] for every signal

evidence_count = len(relevant_artifacts)  # = 0

if evidence_count < self.lens.confidence_rules.get("min_evidence_count", 1):
    return None                           # ← every signal returns None → 0 claims
```

This happens for **every** audience lens (9 lenses), and any exceptions are silently swallowed by the bare `except Exception: pass` at lines 1138–1139, making the bug invisible in logs.

## Fix

Align the two slices. The simplest repair: update ALL signals' artifact IDs (not just the last 10), and pass all signals to the generator.

### server.py lines 1118–1121

**Replace:**
```python
            # Link signals to these artifacts for evidence matching
            selected_artifacts = dummy_artifacts[:5]
            artifact_ids = [a.id for a in selected_artifacts]
            for s in all_signals[-10:]:
                s.source_artifact_ids = artifact_ids

            lens_claims = gen.generate_claims(all_signals[:30], selected_artifacts)
```

**With:**
```python
            # Link signals to these artifacts for evidence matching
            selected_artifacts = dummy_artifacts[:5]
            artifact_ids = [a.id for a in selected_artifacts]
            for s in all_signals:
                s.source_artifact_ids = artifact_ids

            lens_claims = gen.generate_claims(all_signals, selected_artifacts)
```

Two changes:
1. Line 1118: `all_signals[-10:]` → `all_signals` (update every signal, not just the last 10)
2. Line 1121: `all_signals[:30]` → `all_signals` (pass all signals, not just the first 30)

## Secondary Issue: Silent Exception Suppression

Lines 1138–1139 swallow all exceptions without logging:

```python
        except Exception as e:
            pass
```

This hides any secondary failures (e.g., model import errors, type mismatches) that could also suppress claims. Recommend logging the exception:

```python
        except Exception as e:
            logger.exception(f"Lens {lens_id} failed: {e}")
```

## Verification

After the fix, `_signal_to_claim` will find 5 matching artifacts per signal (since `artifact_ids` = the 5 `selected_artifacts` IDs), giving `evidence_count=5` for every signal. All lenses have `min_evidence_count` of 1 or 2, so every signal passes the threshold and produces a claim.
