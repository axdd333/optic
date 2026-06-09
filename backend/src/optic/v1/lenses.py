"""
Optic V1 — Audience Lens Configurations
========================================
Each lens has priorities, evidence preferences, common false positives,
risk sensitivity, repair preferences, forbidden outputs, and confidence rules.

Canonical 9: Recruiter, Investor, Collaborator, Creator, Privacy,
              Platform, Search, Institution, Stranger
"""
from .models import AudienceLens

AUDIENCE_LENSES: dict[str, AudienceLens] = {
    "recruiter": AudienceLens(
        id="recruiter",
        name="Recruiter read",
        icon="👤",
        priorities=[
            "role_fit", "stability", "proof_of_work", "clarity",
            "professionalism", "recent_activity", "team_signals"
        ],
        evidence_preferences=[
            "linkedin_profile", "resume", "github", "portfolio",
            "work_history", "project_output", "public_posts"
        ],
        common_false_positives=[
            "employment_gap_reads_as_risk",
            "creative_work_reads_as_unfocused",
            "rapid_role_changes_reads_as_flaky",
            "personal_projects_ignored"
        ],
        risk_sensitivity=0.7,
        repair_preferences=[
            "linkedin_headline_rewrite", "resume_update",
            "project_pinning", "gap_context", "proof_screenshots"
        ],
        forbidden_outputs=[
            "eligibility_prediction",
            "interview_recommendation",
            "fit_score",
            "auto_ranking"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_recent_evidence": True,
            "max_recency_days": 365,
            "downgrade_for_contradictions": True,
        }
    ),
    "investor": AudienceLens(
        id="investor",
        name="Investor read",
        icon="💰",
        priorities=[
            "ambition_signal", "execution_velocity", "narrative_coherence",
            "trust_risk", "founder_market_fit", "domain_depth",
            "technical_capability"
        ],
        evidence_preferences=[
            "github_activity", "project_shipping", "public_writing",
            "linkedin_trajectory", "investment_history", "team_building"
        ],
        common_false_positives=[
            "academic_focus_reads_as_risk_averse",
            "diverse_interests_reads_as_unfocused",
            "stealth_mode_reads_as_no_progress",
            "young_founder_reads_as_inexperienced"
        ],
        risk_sensitivity=0.6,
        repair_preferences=[
            "publish_start_here_page", "pin_strongest_project",
            "add_founder_narrative", "clean_public_presence",
            "add_timeline_context"
        ],
        forbidden_outputs=[
            "fundability_score",
            "valuation_hint",
            "investment_recommendation",
            "founder_ranking"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_project_evidence": True,
            "max_recency_days": 180,
            "downgrade_for_contradictions": True,
        }
    ),
    "collaborator": AudienceLens(
        id="collaborator",
        name="Collaborator / cofounder read",
        icon="🔗",
        priorities=[
            "execution_style", "chaos_risk", "complementary_skill",
            "trust", "communication", "reliability_signal"
        ],
        evidence_preferences=[
            "github_collaboration", "project_history",
            "public_interactions", "team_context", "references"
        ],
        common_false_positives=[
            "solo_work_reads_as_poor_team_player",
            "many_projects_reads_as_unfocused",
            "no_public_team_work_reads_as_isolated"
        ],
        risk_sensitivity=0.6,
        repair_preferences=[
            "add_collaboration_context", "link_team_projects",
            "add_recommendations", "show_work_style"
        ],
        forbidden_outputs=[
            "personality_assessment",
            "team_fit_prediction",
            "culture_score"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_collaboration_evidence": True,
            "max_recency_days": 365,
            "downgrade_for_contradictions": True,
        }
    ),
    "creator": AudienceLens(
        id="creator",
        name="Creator / public figure read",
        icon="📢",
        priorities=[
            "controversy_surface", "brand_clarity", "audience_trust",
            "parasocial_risk", "content_consistency", "platform_presence"
        ],
        evidence_preferences=[
            "social_posts", "public_mentions", "content_history",
            "platform_profiles", "audience_engagement", "press_mentions"
        ],
        common_false_positives=[
            "edgy_content_reads_as_risk",
            "inactive_periods_reads_as_irrelevant",
            "diverse_content_reads_as_confused"
        ],
        risk_sensitivity=0.8,
        repair_preferences=[
            "archive_old_posts", "update_bio_links",
            "add_content_warnings", "pin_best_work",
            "separate_personal_account"
        ],
        forbidden_outputs=[
            "cancellation_prediction",
            "brand_safety_score",
            "audience_growth_prediction"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_public_evidence": True,
            "max_recency_days": 90,
            "downgrade_for_contradictions": True,
        }
    ),
    "privacy": AudienceLens(
        id="privacy",
        name="Privacy read",
        icon="🔒",
        priorities=[
            "exposure_surface", "credential_leakage", "location_tracking",
            "identity_anchors", "behavioral_fingerprints",
            "third_party_linkage", "metadata_retention"
        ],
        evidence_preferences=[
            "browser_history", "search_queries", "location_data",
            "public_profiles", "social_posts", "app_permissions",
            "metadata_trails", "cookie_footprint"
        ],
        common_false_positives=[
            "routine_activity_reads_as_location_pattern",
            "research_queries_reads_as_behavioral_signal",
            "metadata_noise_reads_as_fingerprint",
            "shared_device_signals_mixed"
        ],
        risk_sensitivity=0.9,
        repair_preferences=[
            "clear_cookies", "use_privacy_mode",
            "opt_out_ad_personalization", "separate_profiles",
            "strip_metadata", "audit_app_permissions",
            "enable_do_not_track"
        ],
        forbidden_outputs=[
            "privacy_score",
            "identity_risk_rating",
            "surveillance_recommendation",
            "adversary_playbook"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_behavioral_evidence": True,
            "max_recency_days": 30,
            "downgrade_for_shared_device": True,
            "always_flag_exposure_surface": True,
        }
    ),
    "platform": AudienceLens(
        id="platform",
        name="Platform / algorithm read",
        icon="📊",
        priorities=[
            "interest_categories", "consumer_intent",
            "demographic_proxies", "behavioral_signals",
            "content_affinity", "engagement_patterns"
        ],
        evidence_preferences=[
            "browser_history", "search_queries", "social_engagement",
            "purchase_history", "location_data", "content_interactions"
        ],
        common_false_positives=[
            "research_reads_as_interest",
            "gift_buying_reads_as_personal_interest",
            "shared_device_signals_mixed",
            "content_creator_reads_as_consumer"
        ],
        risk_sensitivity=0.3,
        repair_preferences=[
            "clear_cookies", "use_privacy_mode",
            "opt_out_ad_personalization", "separate_profiles",
            "limit_platform_sharing"
        ],
        forbidden_outputs=[
            "consumer_value_score",
            "ad_targeting_profile_export",
            "purchase_prediction",
            "content_recommendation"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_behavioral_evidence": True,
            "max_recency_days": 30,
            "downgrade_for_shared_device": True,
        }
    ),
    "search": AudienceLens(
        id="search",
        name="Search engine read",
        icon="🔍",
        priorities=[
            "search_appearance", "result_freshness", "relevance_signals",
            "content_quality", "authority_signals", "query_associations",
            "snippet_accuracy"
        ],
        evidence_preferences=[
            "search_results", "public_pages", "meta_tags",
            "structured_data", "backlinks", "social_profiles",
            "knowledge_panel_entries"
        ],
        common_false_positives=[
            "stale_search_results",
            "same_name_different_person",
            "automated_summary_distortion",
            "outdated_meta_tags",
            "search_bubble_effects"
        ],
        risk_sensitivity=0.7,
        repair_preferences=[
            "fix_search_results", "update_all_bios",
            "add_personal_site", "claim_knowledge_panels",
            "add_schema_markup", "refresh_public_pages"
        ],
        forbidden_outputs=[
            "seo_score",
            "page_rank_estimate",
            "search_ranking_guarantee",
            "click_prediction"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_public_evidence": True,
            "max_recency_days": 60,
            "downgrade_for_stale_results": True,
            "flag_name_collisions": True,
        }
    ),
    "institution": AudienceLens(
        id="institution",
        name="Institution read",
        icon="🏛",
        priorities=[
            "credential_verification", "stability_indicators",
            "formal_records", "compliance_surface",
            "institutional_fit", "background_consistency"
        ],
        evidence_preferences=[
            "academic_records", "employment_verification",
            "financial_history", "official_documents",
            "credentials", "certifications",
            "public_records"
        ],
        common_false_positives=[
            "creative_work_reads_as_risk",
            "gap_periods_reads_as_instability",
            "self_employment_reads_as_unemployed",
            "international_experience_reads_as_unverifiable"
        ],
        risk_sensitivity=0.6,
        repair_preferences=[
            "add_achievement_context", "align_application_materials",
            "clean_public_social", "add_verification_records",
            "document_credential_trail", "bridge_timeline_gaps"
        ],
        forbidden_outputs=[
            "eligibility_prediction",
            "admission_prediction",
            "loan_worthiness",
            "candidate_ranking"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_formal_evidence": True,
            "max_recency_days": 730,
            "downgrade_for_contradictions": True,
            "downgrade_for_self_reported_only": True,
        }
    ),
    "stranger": AudienceLens(
        id="stranger",
        name="Stranger read",
        icon="👁",
        priorities=[
            "first_impression", "public_fragments", "search_appearance",
            "professional_baseline", "social_proof", "legibility"
        ],
        evidence_preferences=[
            "google_results", "public_profiles", "social_bios",
            "top_posts", "linkedin_headline", "personal_website"
        ],
        common_false_positives=[
            "outdated_search_results",
            "same_name_different_person",
            "stale_bio_reading_as_current",
            "automated_summary_garbage"
        ],
        risk_sensitivity=0.9,
        repair_preferences=[
            "fix_search_results", "update_all_bios",
            "add_personal_site", "claim_google_knowledge_panel",
            "separate_from_name_twins"
        ],
        forbidden_outputs=[
            "character_assessment",
            "trustworthiness_score",
            "intelligence_estimate"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_public_evidence": True,
            "max_recency_days": 60,
            "downgrade_for_stale_context": True,
        }
    ),
}
