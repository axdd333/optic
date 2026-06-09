# TASK-T6: Wire Signal Detectors into Audit Pipeline
**Priority:** HIGH (signal quality)
**Agent:** @optic-vault
**Files:** backend/src/optic/v1/server.py + backend/src/ctxorg/server.py
**Estimated:** 45 minutes

## Problem
The signal package (detectors.py, ml_detector.py, auditor.py — 249+ lines with PatternDetector, AnomalyDetector, ThresholdDetector, MLAuditor) is imported but NEVER called during audit. Only basic workstream-derived signals are created (4 categories: topic_focus, activity_volume, timeline_gap, project_velocity).

## Fix

### In V1 server's run_audit()
After loading real artifacts (T5), run signal detectors on artifact content:
```python
# Stage 5: Run signal detectors on artifact content
try:
    from ..signal import SignalAuditor, PatternDetector
    auditor = SignalAuditor()
    auditor.add_detector(PatternDetector.default_bias_patterns())
    
    for artifact in real_artifacts:
        if artifact.content_preview:
            content = artifact.content_preview
            metadata = artifact.metadata or {}
            summary = content[:200]
            source = SignalSource.FILE if artifact.type == "scanned_file" else SignalSource.TEXT
            result = auditor.audit(content, source, summary, metadata)
            for detection in result.detections:
                all_signals.append(Signal(
                    id=uuid4(),
                    category=detection.category,
                    description=detection.description,
                    severity=Severity(detection.severity.value),
                    source_artifact_ids=[artifact.id],
                    metadata=detection.metadata,
                    created_at=now,
                ))
except ImportError:
    pass  # Signal package not available — fall back to workstream signals
```

### In ctxorg bridge _v1_audit_bg()
Similarly add signal detector calls against artifact content.

## Verification
After fix, signal count should increase beyond basic 4 workstream-derived signals. Check:
```sql
SELECT DISTINCT category FROM signals;
```
Should show categories from PatternDetector (bias, stereotype, etc.).

## References
- QA report: QA-VERIFICATION-HAWK.md, Section Stage 5, T6
- Code: optic/signal/detectors.py (PatternDetector)
- Code: optic/signal/auditor.py (SignalAuditor)
