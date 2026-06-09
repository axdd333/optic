# TASK-T2: Fix Dict/Object Type Mismatch in Contradiction Engine
**Priority:** BLOCKER (contradiction engine fails silently)
**Agent:** @optic-pipe
**File:** backend/src/ctxorg/server.py + backend/src/optic/v1/contradiction.py
**Estimated:** 30 minutes

## Problem
`_v1_audit_bg()` passes raw Python dicts to `ContradictionEngine.run_full_audit()`:
```python
claim_dicts = [_v1_row_to_dict(r) for r in all_claim_rows]
contradictions = engine.run_full_audit(claim_dicts, artifact_dicts, entity_dicts)
```

All 5 detection methods access typed attributes on objects:
- `e.type`, `claim.title`, `claim.audience_lens` (find_job_title_mismatches)
- `a.metadata`, `a.id` (find_timeline_conflicts, find_stale_context)
- Entity attributes (find_profile_mismatches)

Dicts don't have these as attributes — they'd need `["type"]` access. This causes AttributeError.

## Fix Options

### Option A (recommended): Build proper typed objects
```python
# Build proper Artifact objects
from optic.v1.models import Artifact, Entity
artifact_objects = []
for ad in artifact_dicts:
    artifact_objects.append(Artifact(
        id=UUID(ad["id"]),
        source_id=UUID(ad["source_id"]),
        type=ad["type"],
        raw_hash=ad["raw_hash"],
        metadata=ad.get("metadata", {}),
        is_public=ad.get("is_public", False),
        content_preview=ad.get("content_preview", ""),
    ))
# Build proper Entity objects similarly from entity_dicts
```

### Option B: Make contradiction engine handle dicts
Add `isinstance` checks or `getattr` fallbacks in all 5 methods. More invasive.

## Verification
After fix, trigger audit, verify contradictions appear at `/api/v1/status` with count > 0.

## References
- QA report: QA-VERIFICATION-HAWK.md, Section B2
- Code: contradiction.py, all 5 `find_*` methods
- Code: ctxorg/server.py, line ~9114
