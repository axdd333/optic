# TASK-T4: Fix Audience Lenses to Match Sacred Doctrine
**Priority:** CRITICAL (doctrinal mismatch)
**Agent:** @optic-aria
**Files:** backend/src/optic/v1/lenses.py + backend/src/ctxorg/server.py
**Estimated:** 45 minutes

## Problem
The sacred texts mandate 9 lenses: Recruiter, Investor, Collaborator, Creator, **Privacy**, **Platform**, **Search**, **Institution**, Stranger.

Current code has: recruiter, investor, **admissions**, creator, stranger, **customer**, collaborator, **ad_platform**, **future_agent**

3 missing, 3 extra. Also: ctxorg bridge limits to 4 lenses (`[:4]`) killing 5 lenses.

## Fix

### 1. Add missing lenses to lenses.py
```python
"privacy": AudienceLens(
    id="privacy", name="Privacy lens", icon="🔒",
    priorities=["exposure_surface", "location_leakage", "sensitive_traces",
                "hidden_metadata", "account_linkage", "removability"],
    evidence_preferences=["metadata_scan", "permission_audit", "sharing_settings",
                          "location_history", "account_connections"],
    common_false_positives=["metadata_is_benign", "public_info_is_safe",
                            "anonymized_means_private"],
    risk_sensitivity=0.9,
    repair_preferences=["strip_metadata", "review_permissions",
                        "unlink_accounts", "enable_2fa", "audit_sharing"],
    forbidden_outputs=["privacy_score", "security_rating", "identity_exposure_estimate"],
    confidence_rules={"min_evidence_count": 1, "max_recency_days": 90,
                      "downgrade_for_contradictions": True}
),

"search": AudienceLens(
    id="search", name="Search engine read", icon="🔍",
    priorities=["search_snippet_accuracy", "first_page_impression",
                "name_disambiguation", "stale_result_risk"],
    evidence_preferences=["google_results", "search_snippets",
                          "knowledge_panel", "image_search"],
    common_false_positives=["same_name_different_person", "outdated_results",
                            "automated_snippet_garbage"],
    risk_sensitivity=0.8,
    repair_preferences=["claim_knowledge_panel", "update_indexed_pages",
                        "add_personal_site", "disambiguate_from_namesakes"],
    forbidden_outputs=["search_ranking", "visibility_score", "reputation_estimate"],
    confidence_rules={"min_evidence_count": 1, "require_public_evidence": True,
                      "max_recency_days": 90, "downgrade_for_stale_context": True}
),

"institution": AudienceLens(
    id="institution", name="Institution read", icon="🏛",
    priorities=["credential_verification", "background_consistency",
                "professional_trajectory", "public_record_alignment"],
    evidence_preferences=["academic_record", "professional_history",
                          "credentials", "references", "public_records"],
    common_false_positives=["gap_reads_as_risk", "creative_work_reads_as_soft",
                            "online_presence_reads_as_character"],
    risk_sensitivity=0.6,
    repair_preferences=["align_application_materials", "verify_credentials",
                        "add_context_for_gaps", "clean_public_presence"],
    forbidden_outputs=["admission_prediction", "eligibility_judgment",
                       "candidate_ranking", "fit_score"],
    confidence_rules={"min_evidence_count": 2, "max_recency_days": 730,
                      "downgrade_for_contradictions": True}
),
```

### 2. Rename/remove non-doctrinal lenses
- `admissions` → Replace with `institution` above (admissions was narrower)
- `customer` → Remove (not in doctrine) or keep as optional extra beyond canonical 9
- `ad_platform` → Rename to `platform` per sacred texts
- `future_agent` → Remove (not in doctrine) or keep as extra

### 3. Remove lens limit in ctxorg bridge
```
# Line 9014 in ctxorg/server.py
# CHANGE: for lens_id in list(AUDIENCE_LENSES.keys())[:4]:
# TO:
for lens_id in list(AUDIENCE_LENSES.keys()):
```

## Verification
Confirm `len(AUDIENCE_LENSES) == 9` and all sacred lens IDs present exactly.
```
assert set(AUDIENCE_LENSES.keys()) == {"recruiter", "investor", "collaborator", "creator", "privacy", "platform", "search", "institution", "stranger"}
```

## References
- QA report: QA-VERIFICATION-HAWK.md, Sections Stage 6, T4
- Sacred texts: 9 Audience Lenses (Recruiter, Investor, Collaborator, Creator, Privacy, Platform, Search, Institution, Stranger)
- Hyperdoc §13: Privacy lens values
