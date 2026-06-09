# TASK-T3: Wire Consent Filter into Main Audit Pipelines
**Priority:** CRITICAL (violates Invariant #2)
**Agent:** @optic-bolt
**Files:** backend/src/optic/v1/server.py + backend/src/ctxorg/server.py
**Estimated:** 20 minutes

## Problem
The `_consent_check_source()` function (ctxorg/server.py:7965) is well-built but ONLY called in `audit_single_payload()`. It's never called in:
- V1 server's `run_audit()` (optic/v1/server.py:1447)
- Ctxorg bridge `_v1_audit_bg()` (ctxorg/server.py:8910)

This means every source passes consent checks unconditionally, violating Invariant #2.

## Fix
### In V1 server's run_audit()
Before processing workstreams, query consent_receipts and filter:
```python
# Stage 2: Consent filter
consented_sources = []
for ws in workstreams:
    sid = ws.get("source_id", ws.get("id", ""))
    # Check consent — if no receipt, conservative default is allow
    receipt = conn.execute(
        "SELECT * FROM consent_receipts WHERE source_id=? AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1",
        (sid,)
    ).fetchone()
    if receipt:
        scope = json.loads(receipt.get("scope", "[]") or "[]")
        if "infer" not in scope:
            continue  # Skip non-consented source
    consented_sources.append(ws)
workstreams = consented_sources
```

### In ctxorg bridge _v1_audit_bg()
Import and call `_consent_check_source()`:
```python
for card in _workstream_cards[:]:
    ws_id = card.get("source_id", card.get("id", ""))
    consent = _consent_check_source(ws_id)
    if not consent["consented"]:
        _workstream_cards.remove(card)
```

## Verification
After fix, add a revoked consent receipt and verify the source is excluded from audit output.

## References
- QA report: QA-VERIFICATION-HAWK.md, Section T3
- Invariant #2: Consent-Scoped — no data analyzed without approval
- Code: ctxorg/server.py line 7965 (_consent_check_source)
