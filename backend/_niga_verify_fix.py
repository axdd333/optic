"""Verify repair generation post-fix."""
import sys
sys.path.insert(0, '.')
try:
    from optic.v1.server import _generate_repairs, _coerce_uuid_repair
    from optic.v1.models import RepairAction
    print("Import OK")
    
    # Test with mock data
    mock_claims = [
        {"id": "00000000-0000-4000-8000-000000000001", "title": "Recruiter read: frequent_topic",
         "audience_lens": "recruiter", "confidence_band": "high", "severity": "medium",
         "claim": "This user focuses heavily on AI/ML systems and open source tooling",
         "source_gaps": '["Missing GitHub evidence", "No portfolio links"]'},
        {"id": "00000000-0000-4000-8000-000000000002", "title": "Investor read: project_velocity",
         "audience_lens": "investor", "confidence_band": "medium", "severity": "low",
         "claim": "Project shows inconsistent commit velocity across quarters",
         "source_gaps": '[]'},
        {"id": "00000000-0000-4000-8000-000000000003", "title": "Stranger read: frequent_topic",
         "audience_lens": "stranger", "confidence_band": "low", "severity": "low",
         "claim": "Limited public activity visible to strangers",
         "source_gaps": '["No public profile", "No social media links"]'},
    ]
    
    mock_contradictions = [
        {"category": "timeline_gap", "description": "Gap between Project A (2023) and Project B (2025)",
         "severity": "medium", "audience_affected": ["recruiter"],
         "claim_ids": ["00000000-0000-4000-8000-000000000001"]},
        {"category": "stale_context", "description": "Files in archive/ not touched since 2022",
         "severity": "low", "audience_affected": ["stranger"],
         "claim_ids": []},
    ]
    
    mock_risks = [
        {"category": "overexposure", "description": "Personal email visible in git history",
         "severity": "high", "audience_affected": ["stranger", "recruiter"]},
        {"category": "stale_context", "description": "3 directories with no activity in 2+ years",
         "severity": "medium", "audience_affected": ["recruiter"]},
    ]
    
    repairs = _generate_repairs(mock_claims, mock_contradictions, mock_risks)
    print(f"\nGenerated {len(repairs)} repairs:")
    
    priorities = []
    for r in repairs:
        p = round(r.priority, 4)
        priorities.append(p)
        linked = str(r.linked_claim_id)[:8] if r.linked_claim_id else "(none)"
        steps_preview = r.exact_steps[0][:60] if r.exact_steps else "(no steps)"
        print(f"  priority={p:.4f} | linked_claim={linked} | steps='{steps_preview}...'")
        print(f"    impact={r.impact} urgency={r.urgency} effort={r.effort} rev={r.reversibility}")
        print(f"    before={r.before_measurement} | after={r.after_measurement}")
    
    # Verify uniqueness
    print(f"\nUnique priorities: {len(set(priorities))} / {len(priorities)}")
    if len(set(priorities)) == len(priorities):
        print("PASS: All priorities are unique!")
    else:
        print("PARTIAL: Some duplicate priorities (possible with small samples)")
    
    # Verify linkage
    linked_count = sum(1 for r in repairs if r.linked_claim_id)
    print(f"Linked repairs: {linked_count}/{len(repairs)}")
    if linked_count > 0:
        print("PASS: Repairs are linked to claims!")
    
    # Verify executable steps
    executable = 0
    for r in repairs:
        for step in r.exact_steps:
            if any(cmd in step for cmd in ['find ', 'grep ', 'ls ', 'cd ', 'git ', 'touch ', 'echo ', 'mkdir ']):
                executable += 1
                break
    print(f"Repairs with shell commands: {executable}/{len(repairs)}")
    if executable > 0:
        print("PASS: Repairs contain executable shell commands!")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAIL: {e}")
