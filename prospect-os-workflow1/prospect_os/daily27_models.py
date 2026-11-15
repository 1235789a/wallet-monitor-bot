"""Data models, enums, and state machine for MultiHub GEO Daily 27 pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DAILY_QUOTA_TARGETS = {"WA": 15, "TG": 2, "FB": 10}
TOTAL_DAILY_QUOTA = 27
RETAIL_EXPERIMENT_QUOTA = {"wine": 1, "vape": 1, "adult": 1}

SEGMENTS = {
    "CORE_B2B",
    "REGULATED_RETAIL_RESEARCH",
    "PARTNER_CANDIDATE",
    "REJECTED_OR_HOLD",
}

EVIDENCE_CARD_TYPES = {
    "AI_LIVE_TEST_CARD",      # Real AI search session + raw screenshot + prompt/model/time/answer
    "STUDY_FACT_CARD",        # Official website fact research card explicitly marked AI NOT TESTED
    "NONE",
}


@dataclass
class AITestRecord:
    """Stores verbatim live AI search test details (Requirement 8)."""
    tested: bool = False
    platform: str = ""
    model: str = ""
    tested_at_utc: str = ""
    exact_prompt: str = ""
    verbatim_answer: str = ""
    cited_urls: list[str] = field(default_factory=list)
    raw_screenshot_path: str = ""
    raw_screenshot_sha256: str = ""
    session_url: str = ""
    note: str = "AI_NOT_TESTED"

    @property
    def is_strict_live_proof(self) -> bool:
        return bool(
            self.tested
            and self.platform
            and self.tested_at_utc
            and self.exact_prompt
            and self.verbatim_answer
            and self.raw_screenshot_path
            and self.raw_screenshot_sha256
        )


@dataclass
class CandidateRecord:
    """Unified prospect record preserving original_prospect_id end-to-end."""
    original_prospect_id: str
    company_name: str
    discovery_source_url: str
    discovery_channel: str = "independent_directory"
    raw_source_dataset: str = ""
    official_url: str = ""
    canonical_domain: str = ""
    alias_domains: list[str] = field(default_factory=list)
    parent_or_sub_brands: list[str] = field(default_factory=list)
    country_or_region: str = "Global"
    target_language: str = "en"
    claimed_size_range: str = "UNKNOWN"
    estimated_min_employees: int | None = None
    estimated_max_employees: int | None = None
    independent_operated: bool = True
    location_count: int = 1
    segment: str = "CORE_B2B"
    retail_category: str | None = None  # wine, vape, adult

    # Channel & contact fields
    channel: str = "UNASSIGNED"  # WA, TG, FB, UNASSIGNED
    allocated_slot: str = ""     # e.g., WA-01..WA-15, TG-01..TG-02, FB-01..FB-10, RETAIL-01..03, PARTNER
    contact_url: str = ""
    contact_route_source: str = ""
    all_public_links: list[str] = field(default_factory=list)
    route_status: str = "UNVERIFIED"
    fb_route_status: str | None = None
    fb_route_type: str | None = None  # PERSON vs COMPANY_PAGE
    recipient_name: str = ""
    recipient_role: str = ""
    recipient_verified: bool = False
    recipient_opt_in_status: str = "UNKNOWN"

    # Business, activity & buyer scenario fields
    primary_service: str = ""
    observed_site_fact: str = ""
    recent_30d_activity_status: str = "UNKNOWN"
    recent_30d_activity_evidence: str = ""
    recent_30d_activity_url: str = ""
    buyer_question: str = ""
    buyer_scenario: str = ""
    geo_opportunity_hypothesis: str = ""

    # Deduplication & History fields
    history_status: str = "UNCHECKED"
    exclusion_checks: dict[str, bool] = field(default_factory=dict)
    matched_history_sources: list[str] = field(default_factory=list)
    is_in_progress_resume: bool = False

    # Evidence & Image fields
    raw_web_screenshot_path: str = ""
    raw_web_screenshot_sha256: str = ""
    ai_test: AITestRecord = field(default_factory=AITestRecord)
    evidence_card_type: str = "NONE"
    png_path: str = ""
    png_drive_url: str = ""
    png_sha256: str = ""
    png_dimensions: str = ""

    # Outreach Copy & QA fields
    first_contact_draft: str = ""
    outreach_qa_status: str = "PENDING"
    outreach_qa_score: int = 0
    outreach_qa_issues: list[str] = field(default_factory=list)

    # Four-stage funnel flags (Requirement 10)
    low_cost_screen_passed: bool = False
    research_completed: bool = False
    image_completed: bool = False
    contact_qualified: bool = False
    strict_evidence_verified: bool = False
    send_ready: bool = False
    is_retail_research: bool = False
    auto_send_enabled: bool = False
    send_status: str = "NOT_SENT"

    # Hold / Rejection tracking
    stage: str = "RAW"
    hold_or_reject_reasons: list[str] = field(default_factory=list)
    last_updated_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
