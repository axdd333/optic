# TASK-T1: Fix NameError Blocker in _v1_audit_bg()
**Priority:** BLOCKER (pipeline crashes silently)
**Agent:** @optic-pipe
**File:** backend/src/ctxorg/server.py
**Estimated:** 5 minutes

## Problem
The variable `all_generated_artifacts` is appended to at line ~9068 but never initialized as an empty list. This causes NameError, which crashes the entire `_v1_audit_bg()` function. The exception handler at line 9232 swallows the error silently.

## Fix
Add this line BEFORE the lens loop (after line ~9011, before comment "─ Stages 4-7"):

```python
all_generated_artifacts: list[dict] = []
```

## Verification
After fix, trigger `POST /api/v1/audit/general` and verify `/api/v1/status` shows non-zero claim_count, risk_count, and repair_count.

## References
- QA report: QA-VERIFICATION-HAWK.md, Section B1
- Code: ctxorg/server.py, function `_v1_audit_bg()`, line ~8910
