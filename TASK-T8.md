# TASK-T8: Wire EntityResolver into Audit Pipeline
**Priority:** MEDIUM (enables 2 more contradiction methods)
**Agent:** @optic-sage
**Files:** backend/src/optic/v1/server.py + backend/src/ctxorg/server.py
**Estimated:** 20 minutes

## Problem
`EntityResolver` (resolver.py, 385 lines) is never called during audit. The contradiction engine's `find_profile_mismatches` and `find_job_title_mismatches` need entity data but receive empty lists.

## Fix

### In V1 server's run_audit()
After artifacts are loaded (T5), resolve entities:
```python
# Resolve entities from artifacts
entity_resolver = resolver.EntityResolver()
entities = entity_resolver.resolve(real_artifacts)
```

Then pass to contradiction engine (replacing the empty `[]`):
```python
contradictions = engine.run_full_audit(
    [_row_to_claim(r) for r in existing_claims],
    real_artifacts,   # Was: []
    entities,          # Was: []
)
```

### In ctxorg bridge _v1_audit_bg()
Similarly, after building artifact_objects, call entity resolver and pass results.

## Verification
After fix, contradiction count should increase because 2 additional detection methods (profile_mismatches, job_title_mismatches) now receive non-empty entity data.

## References
- QA report: QA-VERIFICATION-HAWK.md, Section T8
- Code: optic/v1/resolver.py (EntityResolver)
- Code: optic/v1/contradiction.py (find_profile_mismatches, find_job_title_mismatches)
