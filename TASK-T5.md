# TASK-T5: Wire Real Artifacts from DB into Audit Pipeline
**Priority:** HIGH (evidence quality)
**Agent:** @optic-nova
**Files:** backend/src/optic/v1/server.py + backend/src/ctxorg/server.py
**Estimated:** 30 minutes

## Problem
Both audit paths fabricate dummy Artifact objects instead of querying the artifacts table. The ctxorg bridge uses workstream key_files as a partial improvement, but neither actually loads scanned artifacts from the database.

## Fix

### In V1 server's run_audit() (lines 1487-1496)
Replace dummy artifact creation:
```python
# OLD: dummy_artifacts created from workstream metadata
# NEW: Load real artifacts from the DB
artifact_rows = conn.execute(
    "SELECT a.* FROM artifacts a "
    "JOIN sources s ON s.id = a.source_id "
    "WHERE s.user_id = ? ORDER BY a.id LIMIT 50",
    (user["id"],)
).fetchall()
real_artifacts = [_row_to_artifact(r) for r in artifact_rows]
if not real_artifacts:
    # Fallback: use workstream-derived artifacts
    real_artifacts = _build_artifacts_from_workstreams(workstreams)
```

### In ctxorg bridge _v1_audit_bg()
Query the artifacts table instead of building from workstream key_files:
```python
conn_ro = _v1_open_db()
artifact_rows = conn_ro.execute(
    "SELECT * FROM artifacts LIMIT 50"
).fetchall()
conn_ro.close()
real_artifact_dicts = [_v1_row_to_dict(r) for r in artifact_rows]
```

## Verification
After fix, audit claims should cite artifact IDs that match actual rows in the artifacts table.
```sql
SELECT c.id, c.evidence_count FROM claims c LIMIT 5;
SELECT a.id, a.type FROM artifacts a LIMIT 5;
```

## References
- QA report: QA-VERIFICATION-HAWK.md, Sections Stage 3-4, T5
- Hyperdoc §11: Evidence quality labels
- Code: optic/v1/server.py lines 1487-1496
