"""
Optic V1 — Audience Lens Configurations
========================================
Each lens has priorities, evidence preferences, common false positives,
risk sensitivity, repair preferences, forbidden outputs, and confidence rules.
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
    "admissions": AudienceLens(
        id="admissions",
        name="Admissions read",
        icon="🎓",
        priorities=[
            "intellectual_seriousness", "consistency", "maturity",
            "achievement_evidence", "trajectory", "curiosity_depth"
        ],
        evidence_preferences=[
            "academic_record", "project_portfolio", "public_writing",
            "recommendations", "extracurricular_depth", "competitions"
        ],
        common_false_positives=[
            "gap_year_reads_as_risk",
            "creative_work_reads_as_soft",
            "online_presence_reads_as_professional_focus"
        ],
        risk_sensitivity=0.5,
        repair_preferences=[
            "add_achievement_context", "align_application_materials",
            "clean_public_social", "add_letter_writers"
        ],
        forbidden_outputs=[
            "admissions_prediction",
            "candidate_ranking",
            "fit_score"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_academic_evidence": True,
            "max_recency_days": 730,
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
    "customer": AudienceLens(
        id="customer",
        name="Customer / client read",
        icon="🤝",
        priorities=[
            "credibility", "reliability", "polish", "domain_authority",
            "social_proof", "professional_presence"
        ],
        evidence_preferences=[
            "testimonials", "portfolio", "credentials", "website",
            "professional_profiles", "published_work"
        ],
        common_false_positives=[
            "small_portfolio_reads_as_inexperienced",
            "no_testimonials_reads_as_risky",
            "personal_content_reads_as_unprofessional"
        ],
        risk_sensitivity=0.5,
        repair_preferences=[
            "add_testimonials", "build_portfolio_page",
            "add_case_studies", "link_credentials",
            "add_faq_page"
        ],
        forbidden_outputs=[
            "professional_quality_score",
            "hiring_recommendation",
            "trust_rating"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_professional_evidence": True,
            "max_recency_days": 365,
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
    "ad_platform": AudienceLens(
        id="ad_platform",
        name="Ad platform read",
        icon="📊",
        priorities=[
            "interest_categories", "consumer_intent",
            "demographic_proxies", "behavioral_signals"
        ],
        evidence_preferences=[
            "browser_history", "search_queries", "social_engagement",
            "purchase_history", "location_data"
        ],
        common_false_positives=[
            "research_reads_as_interest",
            "gift_buying_reads_as_personal_interest",
            "shared_device_signals_mixed"
        ],
        risk_sensitivity=0.3,
        repair_preferences=[
            "clear_cookies", "use_privacy_mode",
            "opt_out_ad_personalization", "separate_profiles"
        ],
        forbidden_outputs=[
            "consumer_value_score",
            "ad_targeting_profile_export",
            "purchase_prediction"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "require_behavioral_evidence": True,
            "max_recency_days": 30,
            "downgrade_for_shared_device": True,
        }
    ),
    "future_agent": AudienceLens(
        id="future_agent",
        name="Future AI agent read",
        icon="🤖",
        priorities=[
            "compressed_summary_risk", "stale_context_risk",
            "machine_readable_persona", "data_portability"
        ],
        evidence_preferences=[
            "structured_profiles", "public_data_feeds",
            "search_snippets", "knowledge_graph_entries"
        ],
        common_false_positives=[
            "summary_distortion",
            "context_collapse",
            "temporal_misalignment",
            "source_attribution_errors"
        ],
        risk_sensitivity=1.0,
        repair_preferences=[
            "add_schema_markup", "maintain_canonical_profiles",
            "refresh_public_data", "claim_knowledge_panels"
        ],
        forbidden_outputs=[
            "ai_readiness_score",
            "future_hirability_prediction",
            "automated_character_assessment"
        ],
        confidence_rules={
            "min_evidence_count": 1,
            "always_flag_stale_context": True,
            "max_recency_days": 30,
            "require_source_attribution": True,
        }
    ),
}
