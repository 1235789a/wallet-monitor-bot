from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_VAULT = Path(r"D:\BLTeam\BLTeam")
DEFAULT_DB = DEFAULT_VAULT / "ProspectOS" / "data" / "prospects.db"
TRACKS = {"web3_geo", "handmade_visual"}
WEB3_TARGET = 30  # historical v2 batch size; P0 sprint output is intentionally variable
HANDMADE_TARGET = 0
ACTIVE_SPRINT_POOL = "P0"
P0_MAX_ACTIVITY_DAYS = 3  # one controlled relaxation from the former 48-hour window
P0_MAX_SIZE_UPPER = 40  # exactly 2x the former conservative 20-person ceiling
DIRECT_CONTACT_TYPES = {
    "person", "founder", "business_account", "business_whatsapp",
    "support", "support_bot", "sales",
}
DISALLOWED = {
    "gambling", "casino", "sports betting", "adult", "porn", "tobacco",
    "vape", "weapon", "firearm", "narcotic", "illegal investment",
}
BANNED_COPY = {
    "i hope this message finds you well",
    "elevate your brand",
    "improve your online presence",
    "unlock your potential",
}
# User preference: Telegram is a fallback channel and should be capped at three
# retained candidates per run; WhatsApp remains the preferred channel.
MAX_TELEGRAM = 3
REQUIRED_WHATSAPP = 27
TELEGRAM_MIN_QUALITY_SCORE = 85
TOP_TELEGRAM_CONTACT_TYPES = {"person", "founder", "sales", "business_account"}
AUTO_REPLY_STATUSES = {"yes", "no", "unknown"}
FOLLOW_UP_MAX_COUNT = 1
FOLLOW_UP_MIN_HOURS = 24
FOLLOW_UP_MAX_HOURS = 48
EVIDENCE_LABELS = {"observed", "inferred", "self_reported", "unknown"}
REPLY_BEHAVIOR_STATUSES = {"observed", "not_found", "inaccessible"}
REPLY_BEHAVIOR_STATUS_ALIASES = {
    "observed": "observed",
    "not found": "not_found",
    "not_found": "not_found",
    "not-found": "not_found",
    "inaccessible": "inaccessible",
    "inaccessible/private": "inaccessible",
}
DISCOVERY_CHANNELS = {
    "industry_directory", "vertical_directory", "marketplace", "launch_platform",
    "industry_association", "trade_show", "startup_database", "map_local",
    "social", "community", "forum", "github", "ecosystem_directory",
    "partner_directory", "other_off_search",
}
SEARCH_ONLY_DISCOVERY_CHANNELS = {
    "google", "bing", "search", "search_engine", "seo_results", "ai_search",
}
DISCOVERY_CHANNEL_ALIASES = {
    "industry directory": "industry_directory",
    "vertical directory": "vertical_directory",
    "marketplace": "marketplace",
    "launch platform": "launch_platform",
    "product hunt": "launch_platform",
    "industry association": "industry_association",
    "trade show": "trade_show",
    "startup database": "startup_database",
    "map/local": "map_local",
    "map local": "map_local",
    "linkedin": "social",
    "facebook": "social",
    "instagram": "social",
    "x": "social",
    "twitter": "social",
    "social media": "social",
    "community/forum": "community",
    "ecosystem directory": "ecosystem_directory",
    "partner directory": "partner_directory",
    "off search": "other_off_search",
    "other off search": "other_off_search",
    "search engine": "search_engine",
    "seo results": "seo_results",
    "ai search": "ai_search",
}
BUSINESS_QUALITY_LEVELS = {"strong", "medium", "weak", "unknown"}
DISTRIBUTION_GAP_LEVELS = {"strong", "moderate", "weak", "unknown"}
DISTRIBUTION_GAP_RANK = {"strong": 0, "moderate": 1, "weak": 2, "unknown": 3}
GEO_MATURITY_LEVELS = {"none", "aware", "early", "mature"}
USDT_STATUSES = {
    "verified_settlement_readiness",
    "strong_capability",
    "weak_capability",
    "unknown",
    "no",
}
OUTSOURCING_STATUSES = {"open", "inferred", "unknown", "closed"}
SCORE_LIMITS = {
    "recent_activity": 6,
    "reply_behavior": 12,
    "contact_openness": 4,
    "inquiry_responsiveness": 4,
    "account_authenticity": 4,
    "existing_clients": 10,
    "client_type_fit": 7,
    "decision_maker_access": 5,
    "commercial_activity": 3,
    "geo_gap": 20,
    "partnership_openness": 15,
    "usdt_readiness": 10,
}
REQUIRED_EVIDENCE_CATEGORIES = {
    "discovery",
    "recent_activity",
    "reply_behavior",
    "contact_openness",
    "inquiry_responsiveness",
    "account_authenticity",
    "client",
    "geo_maturity",
    "partnership",
    "usdt",
}
FIRST_MESSAGE_BANNED = BANNED_COPY | {
    "partnership opportunity",
    "book a call",
    "schedule a call",
    "our service",
    "our website",
    "pricing",
    "price",
    "chatgpt",
    "gemini",
    "perplexity",
    "ai search",
}
COMPANY_SUFFIXES = {
    "llc", "ltd", "limited", "inc", "incorporated", "official", "store",
    "company", "co", "private", "pvt",
}
SPRINT_TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
EVIDENCE_STRENGTH = {
    "observed": 4,
    "self_reported": 3,
    "inferred": 2,
    "unknown": 1,
}


def now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def ensure_v2_schema(conn: sqlite3.Connection) -> None:
    """Add v2 storage without rewriting workflow 1's historical company records."""
    evidence_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(evidence)")
    }
    with conn:
        if "evidence_label" not in evidence_columns:
            conn.execute(
                "ALTER TABLE evidence ADD COLUMN evidence_label TEXT NOT NULL DEFAULT 'unknown'"
            )
            conn.execute(
                """
                UPDATE evidence
                SET evidence_label=CASE
                    WHEN is_verified_fact=1 THEN 'observed'
                    ELSE 'inferred'
                END
                """
            )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS partnership_assessments (
                assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL UNIQUE REFERENCES companies(company_id) ON DELETE CASCADE,
                decision_maker_name TEXT NOT NULL,
                decision_maker_role TEXT NOT NULL,
                decision_maker_source_url TEXT NOT NULL,
                recent_activity_at TEXT NOT NULL,
                recent_activity_evidence TEXT NOT NULL,
                reply_behavior_observed INTEGER NOT NULL CHECK(reply_behavior_observed IN (0,1)),
                reply_behavior_evidence TEXT NOT NULL,
                reply_openness_evidence TEXT NOT NULL,
                client_evidence TEXT NOT NULL,
                geo_maturity TEXT NOT NULL,
                geo_maturity_evidence TEXT NOT NULL,
                partnership_evidence TEXT NOT NULL,
                outsourcing_status TEXT NOT NULL,
                usdt_status TEXT NOT NULL,
                usdt_evidence TEXT NOT NULL,
                reply_score INTEGER NOT NULL,
                reply_score_uncapped INTEGER NOT NULL,
                client_score INTEGER NOT NULL,
                geo_gap_score INTEGER NOT NULL,
                partner_score INTEGER NOT NULL,
                usdt_score INTEGER NOT NULL,
                raw_total INTEGER NOT NULL,
                operational_tier TEXT NOT NULL,
                score_breakdown_json TEXT NOT NULL,
                qualification_questions_json TEXT NOT NULL,
                assessment_source_urls_json TEXT NOT NULL,
                decision_maker_status TEXT NOT NULL DEFAULT 'unknown',
                auto_reply_status TEXT NOT NULL DEFAULT 'unknown',
                assessed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prospect_identities (
                identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
                identity_type TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                normalized_value TEXT NOT NULL,
                source_url TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(identity_type, normalized_value)
            );

            CREATE INDEX IF NOT EXISTS idx_assessments_tier
                ON partnership_assessments(operational_tier, raw_total DESC);
            CREATE INDEX IF NOT EXISTS idx_identities_company
                ON prospect_identities(company_id);
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('prospecting_prompt_version', '2')"
        )
        assessment_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(partnership_assessments)")
        }
        if "sprint_tier" not in assessment_columns:
            conn.execute(
                "ALTER TABLE partnership_assessments ADD COLUMN sprint_tier TEXT NOT NULL DEFAULT 'P3'"
            )
        if "evidence_certainty" not in assessment_columns:
            conn.execute(
                "ALTER TABLE partnership_assessments ADD COLUMN evidence_certainty TEXT NOT NULL DEFAULT 'low'"
            )
        if "sprint_rank_key_json" not in assessment_columns:
            conn.execute(
                "ALTER TABLE partnership_assessments ADD COLUMN sprint_rank_key_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "decision_maker_status" not in assessment_columns:
            conn.execute(
                "ALTER TABLE partnership_assessments ADD COLUMN decision_maker_status TEXT NOT NULL DEFAULT 'unknown'"
            )
        if "auto_reply_status" not in assessment_columns:
            conn.execute(
                "ALTER TABLE partnership_assessments ADD COLUMN auto_reply_status TEXT NOT NULL DEFAULT 'unknown'"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assessments_sprint_tier "
            "ON partnership_assessments(sprint_tier, recent_activity_at DESC, raw_total DESC)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('prospecting_prompt_version', '3-p0-sprint')"
        )


def public_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def normalize_domain(url: str) -> str:
    try:
        host = (urlsplit(url.strip()).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_telegram(value: str) -> str:
    raw = value.strip()
    if "t.me/" in raw.lower():
        raw = urlsplit(raw).path.strip("/").split("/")[0]
    raw = raw.lstrip("@").strip().lower()
    return raw if re.fullmatch(r"[a-z0-9_]{5,32}", raw) else ""


def normalize_whatsapp(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits if 8 <= len(digits) <= 15 and not digits.startswith("0") else ""


def canonical_contact(candidate: dict[str, Any]) -> tuple[str, str]:
    channel = str(candidate.get("contact_channel", "")).lower().strip()
    raw = str(candidate.get("contact_value", ""))
    if channel == "telegram":
        normalized = normalize_telegram(raw)
        return normalized, f"https://t.me/{normalized}" if normalized else ""
    if channel == "whatsapp":
        normalized = normalize_whatsapp(raw)
        return normalized, f"https://wa.me/{normalized}" if normalized else ""
    return "", ""


def normalize_company_name(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.casefold())
    return " ".join(word for word in words if word not in COMPANY_SUFFIXES)


def normalize_identity(identity_type: str, value: str) -> str:
    if identity_type == "person":
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
    if identity_type in {"facebook", "linkedin", "instagram", "x"}:
        try:
            parsed = urlsplit(value.strip())
        except ValueError:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname.casefold()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parsed.path.rstrip('/').casefold()}"
    return value.strip().casefold()


def normalize_discovery_channel(value: Any) -> str:
    """Normalize the non-search source used to discover a company."""
    raw = str(value or "").strip().casefold()
    if not raw:
        return ""
    if raw in DISCOVERY_CHANNEL_ALIASES:
        return DISCOVERY_CHANNEL_ALIASES[raw]
    normalized = re.sub(r"[\s/-]+", "_", raw)
    return DISCOVERY_CHANNEL_ALIASES.get(normalized, normalized)


def evidence_text(entries: list[dict[str, Any]], category: str) -> str:
    matches = [entry for entry in entries if entry["category"] == category]
    if not matches:
        return "Unknown"
    return " | ".join(
        f"{entry['label'].replace('_', '-').title()}: {entry['claim']} ({entry.get('source_url') or 'no source'})"
        for entry in matches
    )


def normalize_reply_behavior_status(value: Any) -> str:
    """Normalize the explicit reply-behaviour state used for P0 gating."""
    raw = str(value or "").strip().casefold()
    return REPLY_BEHAVIOR_STATUS_ALIASES.get(raw, raw)


def resolve_reply_behavior_status(
    item: dict[str, Any],
    evidence: list[dict[str, Any]],
    inaccessible_hint: bool = False,
) -> str:
    """Resolve Observed / Not found / Inaccessible without treating Unknown as positive."""
    explicit = normalize_reply_behavior_status(item.get("reply_behavior_status"))
    if explicit:
        return explicit
    reply_entries = [entry for entry in evidence if entry["category"] == "reply_behavior"]
    if any(entry["label"] == "observed" for entry in reply_entries):
        return "observed"
    if inaccessible_hint or any(
        token in entry["claim"].casefold()
        for entry in reply_entries
        for token in ("inaccessible", "not accessible", "private", "无法访问")
    ):
        return "inaccessible"
    return "not_found"


def reply_score_details(
    status: str,
    scores: dict[str, int],
) -> tuple[int, int, int, str]:
    """Return display score, effective score, raw observed-components score and basis."""
    raw = sum(
        scores[key]
        for key in (
            "recent_activity", "reply_behavior", "contact_openness",
            "inquiry_responsiveness", "account_authenticity",
        )
    )
    if status == "observed":
        return raw, raw, raw, "Observed — scored from public reply evidence strength."
    if status == "not_found":
        capped = min(raw, 12)
        return capped, capped, raw, "Not found — capped at 12/30 and pending verification."
    if status == "inaccessible":
        inferred = sum(
            scores[key] for key in ("recent_activity", "contact_openness", "account_authenticity")
        )
        return inferred, inferred, raw, "Inferred — reply evidence inaccessible; estimated only from activity, contact openness and account authenticity."
    raise ValueError(f"unsupported reply behaviour status: {status}")


def reply_behavior_display(item: dict[str, Any]) -> str:
    """Human-readable status that keeps Not found and Inferred distinct in reports."""
    status = str(item.get("reply_behavior_status", "not_found"))
    prefix = {
        "observed": "Observed",
        "not_found": "Not found — 待验证",
        "inaccessible": "Inferred — Inaccessible",
    }.get(status, status.title())
    return f"{prefix}: {evidence_text(item['research_evidence'], 'reply_behavior')}"


def stable_company_id(candidate: dict[str, Any], attempt: int = 0) -> str:
    prefix = "W3" if candidate["track"] == "web3_geo" else "HM"
    seed = "|".join(
        (
            candidate["track"],
            candidate["canonical_domain"],
            normalize_company_name(candidate["company_name"]),
            candidate["country"].casefold(),
            str(attempt),
        )
    )
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{suffix}"


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def company_size_upper_bound(value: str) -> int:
    """Return a conservative upper bound; unknown size must not qualify as P0."""
    numbers = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", value)]
    if not numbers:
        return 10_000
    lowered = value.casefold()
    if any(token in lowered for token in ("solo", "freelancer", "individual")):
        return 1
    return max(numbers)


def strongest_evidence_label(
    evidence: list[dict[str, Any]], category: str
) -> str:
    labels = [entry["label"] for entry in evidence if entry["category"] == category]
    if not labels:
        return "unknown"
    return max(labels, key=lambda label: EVIDENCE_STRENGTH.get(label, 0))


def evidence_certainty(evidence: list[dict[str, Any]]) -> str:
    counts = Counter(entry["label"] for entry in evidence)
    confirmed = counts["observed"] + counts["self_reported"]
    unknown_count = counts["unknown"] + counts["not_found"] + counts["not-found"]
    if counts["observed"] >= 5 and unknown_count <= 1:
        return "high"
    if confirmed >= 5 and unknown_count <= 3:
        return "medium-high"
    if confirmed >= 3:
        return "medium"
    return "low"


def classify_decision_maker_status(item: dict[str, Any], scores: dict[str, int]) -> str:
    """Separate named leadership from a contact that is actually decision-maker reachable."""
    contact_type = str(item.get("contact_type", "")).strip().lower()
    role = str(item.get("decision_maker_role", "")).casefold()
    direct_types = {"person", "founder"}
    leadership_terms = (
        "founder", "owner", "director", "ceo", "chief executive", "managing director",
        "principal", "partner", "老板", "负责人", "创始人",
    )
    if contact_type in direct_types and scores.get("decision_maker_access", 0) >= 4:
        return "confirmed"
    if any(term in role for term in leadership_terms):
        return "named_not_direct"
    return "unknown"


def assign_sprint_tier(
    item: dict[str, Any],
    evidence: list[dict[str, Any]],
    activity_age: int,
    scores: dict[str, int],
    observed_reply: bool,
    reply_behavior_status: str,
) -> tuple[str, str, list[Any]]:
    """Evidence-first tiering for the temporary five-day sprint."""
    size_upper = company_size_upper_bound(str(item["company_size_estimate"]))
    partnership_label = strongest_evidence_label(evidence, "partnership")
    contact_label = strongest_evidence_label(evidence, "contact_openness")
    client_label = strongest_evidence_label(evidence, "client")
    recent_label = strongest_evidence_label(evidence, "recent_activity")
    decision_access = scores["decision_maker_access"]
    resource_fit = (
        scores["existing_clients"] + scores["client_type_fit"]
        + scores["commercial_activity"] + scores["geo_gap"]
    )
    explicit_partner = (
        str(item["outsourcing_status"]).strip().lower() == "open"
        and partnership_label in {"observed", "self_reported"}
    )
    confirmed_usdt = str(item["usdt_status"]).strip().lower() == "verified_settlement_readiness"
    business_quality = str(item.get("business_quality", "unknown")).strip().lower()
    distribution_gap = str(item.get("distribution_gap", "unknown")).strip().lower()
    founder_direct = (
        str(item["contact_type"]).strip().lower() in {"person", "founder"}
        and decision_access >= 4
        and contact_label == "observed"
    )
    contact_claims = " ".join(
        entry["claim"].casefold()
        for entry in evidence
        if entry["category"] == "contact_openness" and entry["label"] == "observed"
    )
    public_dm_invite = (
        contact_label == "observed"
        and str(item["contact_type"]).strip().lower() in DIRECT_CONTACT_TYPES
        and any(token in contact_claims for token in ("invite", "direct", "message", "whatsapp", "telegram", "dm"))
    )
    strong_signals = sum(
        (observed_reply, explicit_partner, confirmed_usdt, founder_direct, public_dm_invite)
    )
    core_ok = (
        recent_label == "observed"
        and client_label in {"observed", "self_reported"}
        and str(item["geo_maturity"]).strip().lower() != "mature"
        and str(item["outsourcing_status"]).strip().lower() != "closed"
        and decision_access >= 3
        and resource_fit >= 30
        and size_upper <= 50
    )
    p0 = (
        core_ok
        and activity_age <= P0_MAX_ACTIVITY_DAYS
        and size_upper <= P0_MAX_SIZE_UPPER
        and decision_access >= 4
        and reply_behavior_status == "observed"
        and classify_decision_maker_status(item, scores) == "confirmed"
        and business_quality == "strong"
        and distribution_gap in {"strong", "moderate"}
        and scores["geo_gap"] >= 12
        and strong_signals >= 1
        # Support/bot routes and explicit auto-replies are not decision-maker
        # paths. Keep them in the wider pool for later verification, but do not
        # let them occupy the reply-first P0 queue.
        and str(item.get("contact_type", "")).strip().lower() not in {"support", "support_bot"}
        and str(item.get("auto_reply_status", "unknown")).strip().lower() != "yes"
    )
    p1 = (
        core_ok
        and activity_age <= 7
        and decision_access >= 4
        and strong_signals >= 2
    )
    p2 = core_ok and activity_age <= 30 and scores["geo_gap"] >= 10
    if p0:
        tier = "P0"
        why = "3天内活跃、最多40人的小型团队，公开回复行为已观察，且联系方式确认属于决策人。"
    elif p1:
        tier = "P1"
        why = "核心条件和多项强信号已验证，但活动时效或小团队条件未达到P0。"
    elif p2:
        tier = "P2"
        why = "基本商业条件已验证；回复、合作或USDT等信息仍有Unknown。"
    else:
        tier = "P3"
        why = "具备后续验证价值，但当前缺少P0/P1/P2所需的关键确定性证据。"
    certainty = evidence_certainty(evidence)
    crypto_rank = {
        "verified_settlement_readiness": 0,
        "strong_capability": 1,
        "weak_capability": 2,
        "unknown": 3,
        "no": 4,
    }.get(str(item["usdt_status"]).strip().lower(), 5)
    reply_score, _, _, _ = reply_score_details(reply_behavior_status, scores)
    client_score = sum(
        scores[key]
        for key in (
            "existing_clients", "client_type_fit", "decision_maker_access",
            "commercial_activity",
        )
    )
    decision_status_rank = {
        "confirmed": 0,
        "named_not_direct": 1,
        "unknown": 2,
    }.get(classify_decision_maker_status(item, scores), 2)
    auto_reply_penalty = int(
        str(item.get("auto_reply_status", "unknown")).strip().lower() == "yes"
        or str(item.get("contact_type", "")).strip().lower() in {"support", "support_bot"}
    )
    # Outreach ordering deliberately puts reply likelihood first.  GEO fit and
    # settlement compatibility are tie-breakers, not reply-rate proxies.
    rank_key: list[Any] = [
        SPRINT_TIER_ORDER[tier],
        -reply_score,
        auto_reply_penalty,
        decision_status_rank,
        -scores["decision_maker_access"],
        -client_score,
        -scores["partnership_openness"],
        -scores["geo_gap"],
        DISTRIBUTION_GAP_RANK.get(distribution_gap, 3),
        activity_age,
        size_upper,
        crypto_rank,
    ]
    return tier, why, rank_key


def validate_candidates(
    rows: list[dict[str, Any]], conn: sqlite3.Connection, day: str
) -> list[dict[str, Any]]:
    errors: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    run_day = datetime.strptime(day, "%Y-%m-%d").date()
    required = {
        "company_name", "website_url", "country", "track", "industry",
        "business_summary", "company_size_estimate", "size_confidence",
        "activity_signal", "contact_channel", "contact_value",
        "contact_clickable_url", "contact_type", "contact_source_url",
        "contact_verified_at", "verified_facts", "cautious_inference",
        "personalization_hook", "fit_reason", "source_urls",
        "decision_maker_name", "decision_maker_role", "decision_maker_source_url",
        "recent_activity_at", "research_evidence", "score_breakdown",
        "geo_maturity", "outsourcing_status", "usdt_status", "first_message",
        "discovery_channel", "discovery_source_url", "discovery_source_note",
        "business_quality", "distribution_gap",
    }

    for index, raw in enumerate(rows, 1):
        item = dict(raw)
        # Older manifests may not have this field.  Unknown is explicit and
        # never contributes positive evidence.
        item["auto_reply_status"] = str(item.get("auto_reply_status", "unknown")).strip().lower()
        name = str(item.get("company_name", f"row {index}")).strip()
        missing = sorted(key for key in required if item.get(key) in (None, "", []))
        if missing:
            errors.append(f"{name}: missing {', '.join(missing)}")
            continue
        if item["track"] != "web3_geo":
            errors.append(f"{name}: workflow 1 currently accepts Web3 only")
        if not public_url(str(item["website_url"])):
            errors.append(f"{name}: invalid website URL")
        domain = normalize_domain(str(item["website_url"]))
        if not domain:
            errors.append(f"{name}: cannot normalize domain")

        discovery_channel = normalize_discovery_channel(item.get("discovery_channel"))
        discovery_source_url = str(item.get("discovery_source_url", "")).strip()
        discovery_source_note = str(item.get("discovery_source_note", "")).strip()
        if discovery_channel in SEARCH_ONLY_DISCOVERY_CHANNELS:
            errors.append(
                f"{name}: search-only discovery channel {discovery_channel} is forbidden; "
                "search engines are diagnostic only"
            )
        elif discovery_channel not in DISCOVERY_CHANNELS:
            errors.append(
                f"{name}: discovery_channel must be an off-search source, got {discovery_channel or 'Unknown'}"
            )
        if not public_url(discovery_source_url):
            errors.append(f"{name}: discovery_source_url must be a public off-search source URL")
        elif domain and normalize_domain(discovery_source_url) == domain:
            errors.append(
                f"{name}: discovery_source_url must be independent of the company website"
            )
        if len(discovery_source_note) < 12:
            errors.append(f"{name}: discovery_source_note must explain how the company was found")

        business_quality = str(item.get("business_quality", "")).strip().lower()
        distribution_gap = str(item.get("distribution_gap", "")).strip().lower()
        if business_quality not in BUSINESS_QUALITY_LEVELS:
            errors.append(f"{name}: business_quality must be strong, medium, weak or unknown")
        elif business_quality in {"weak", "unknown"}:
            errors.append(f"{name}: business quality is not strong enough for the active P0 pool")
        if distribution_gap not in DISTRIBUTION_GAP_LEVELS:
            errors.append(f"{name}: distribution_gap must be strong, moderate, weak or unknown")
        elif distribution_gap in {"weak", "unknown"}:
            errors.append(f"{name}: search distribution gap is too weak or unverified for the active P0 pool")

        contact, canonical_url = canonical_contact(item)
        if not contact:
            errors.append(f"{name}: invalid direct contact")
        supplied = str(item["contact_clickable_url"]).rstrip("/").lower()
        if supplied != canonical_url.rstrip("/").lower():
            errors.append(f"{name}: non-canonical contact link; expected {canonical_url}")
        if str(item["contact_type"]).lower() not in DIRECT_CONTACT_TYPES:
            errors.append(f"{name}: contact type is not a direct business contact")
        if not public_url(str(item["contact_source_url"])):
            errors.append(f"{name}: missing public contact source")

        facts = item["verified_facts"]
        sources = item["source_urls"]
        if not isinstance(facts, list) or len(facts) < 2:
            errors.append(f"{name}: needs at least two verified facts")
        if not isinstance(sources, list) or not sources or any(not public_url(str(x)) for x in sources):
            errors.append(f"{name}: invalid evidence source list")
        if not public_url(str(item["decision_maker_source_url"])):
            errors.append(f"{name}: invalid decision-maker source URL")

        risk_text = " ".join(
            str(item.get(key, "")).casefold()
            for key in ("company_name", "industry", "business_summary", "activity_signal")
        )
        found_risks = sorted(term for term in DISALLOWED if term in risk_text)
        if found_risks:
            errors.append(f"{name}: disallowed category signal {found_risks}")

        try:
            activity_day = datetime.strptime(str(item["recent_activity_at"]), "%Y-%m-%d").date()
            activity_age = (run_day - activity_day).days
            if activity_age < 0 or activity_age > 30:
                errors.append(f"{name}: no qualifying public activity in the last 30 days")
        except ValueError:
            activity_age = 999
            errors.append(f"{name}: recent_activity_at must be YYYY-MM-DD")

        evidence = item["research_evidence"]
        valid_evidence: list[dict[str, Any]] = []
        inaccessible_reply_hint = False
        if not isinstance(evidence, list):
            errors.append(f"{name}: research_evidence must be a list")
            evidence = []
        for evidence_index, raw_entry in enumerate(evidence, 1):
            if not isinstance(raw_entry, dict):
                errors.append(f"{name}: evidence #{evidence_index} must be an object")
                continue
            entry = {
                "category": str(raw_entry.get("category", "")).strip().lower(),
                "label": str(raw_entry.get("label", "")).strip().lower(),
                "claim": str(raw_entry.get("claim", "")).strip(),
                "source_url": str(raw_entry.get("source_url", "")).strip(),
            }
            if entry["category"] not in REQUIRED_EVIDENCE_CATEGORIES:
                errors.append(f"{name}: evidence #{evidence_index} has invalid category")
            special_reply_label = entry["category"] == "reply_behavior" and entry["label"] in {
                "not_found", "not-found", "inaccessible"
            }
            if entry["label"] not in EVIDENCE_LABELS and not special_reply_label:
                errors.append(f"{name}: evidence #{evidence_index} has invalid label")
            if entry["category"] == "reply_behavior" and entry["label"] == "inaccessible":
                # Inaccessible is a state, not positive evidence. Store its
                # evidence label as Inferred so it can never be rendered as Observed.
                inaccessible_reply_hint = True
                entry["label"] = "inferred"
            if not entry["claim"]:
                errors.append(f"{name}: evidence #{evidence_index} has no claim")
            if entry["label"] not in {"unknown", "not_found", "not-found"} and not public_url(entry["source_url"]):
                errors.append(f"{name}: evidence #{evidence_index} needs a public source URL")
            if entry["label"] in {"unknown", "not_found", "not-found"} and entry["source_url"] and not public_url(entry["source_url"]):
                errors.append(f"{name}: evidence #{evidence_index} has invalid source URL")
            valid_evidence.append(entry)
        present_categories = {entry["category"] for entry in valid_evidence}
        missing_categories = sorted(REQUIRED_EVIDENCE_CATEGORIES - present_categories)
        if missing_categories:
            errors.append(f"{name}: missing evidence categories {', '.join(missing_categories)}")
        discovery_evidence = [
            entry for entry in valid_evidence
            if entry["category"] == "discovery"
            and entry["label"] in {"observed", "self_reported"}
        ]
        if not discovery_evidence:
            errors.append(
                f"{name}: discovery evidence must confirm the off-search source before website/search diagnostics"
            )
        elif not any(
            entry["source_url"].rstrip("/").casefold()
            == discovery_source_url.rstrip("/").casefold()
            for entry in discovery_evidence
        ):
            errors.append(
                f"{name}: discovery evidence source must match discovery_source_url"
            )

        breakdown = item["score_breakdown"]
        if not isinstance(breakdown, dict):
            errors.append(f"{name}: score_breakdown must be an object")
            breakdown = {}
        missing_scores = sorted(set(SCORE_LIMITS) - set(breakdown))
        extra_scores = sorted(set(breakdown) - set(SCORE_LIMITS))
        if missing_scores:
            errors.append(f"{name}: missing score fields {', '.join(missing_scores)}")
        if extra_scores:
            errors.append(f"{name}: unknown score fields {', '.join(extra_scores)}")
        clean_scores: dict[str, int] = {}
        for key, limit in SCORE_LIMITS.items():
            value = breakdown.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= limit:
                errors.append(f"{name}: {key} score must be an integer from 0 to {limit}")
                clean_scores[key] = 0
            else:
                clean_scores[key] = value

        expected_activity_score = (
            6 if activity_age <= 1 else 5 if activity_age <= 3 else
            4 if activity_age <= 7 else 3 if activity_age <= 14 else
            2 if activity_age <= 30 else 0
        )
        if clean_scores["recent_activity"] != expected_activity_score:
            errors.append(
                f"{name}: recent_activity score must be {expected_activity_score} for {activity_age} days ago"
            )

        observed_reply = any(
            entry["category"] == "reply_behavior"
            and entry["label"] == "observed"
            and entry["claim"].casefold() != "unknown"
            for entry in valid_evidence
        )
        reply_behavior_status = resolve_reply_behavior_status(
            item, valid_evidence, inaccessible_hint=inaccessible_reply_hint
        )
        if reply_behavior_status not in REPLY_BEHAVIOR_STATUSES:
            errors.append(
                f"{name}: reply_behavior_status must be observed, not_found or inaccessible"
            )
        if reply_behavior_status == "observed" and not observed_reply:
            errors.append(f"{name}: Observed reply_behavior_status requires observed public reply evidence")
        if reply_behavior_status != "observed" and observed_reply:
            errors.append(f"{name}: observed public reply evidence cannot be labelled {reply_behavior_status}")
        if reply_behavior_status != "observed" and clean_scores["reply_behavior"] != 0:
            errors.append(
                f"{name}: non-Observed reply behavior must have reply_behavior score 0"
            )

        if item["auto_reply_status"] not in AUTO_REPLY_STATUSES:
            errors.append(f"{name}: auto_reply_status must be yes, no or unknown")

        geo_maturity = str(item["geo_maturity"]).strip().lower()
        if geo_maturity not in GEO_MATURITY_LEVELS:
            errors.append(f"{name}: invalid geo_maturity")
        if geo_maturity == "mature" or clean_scores["geo_gap"] == 0:
            errors.append(f"{name}: mature GEO delivery is a hard exclusion")
        outsourcing_status = str(item["outsourcing_status"]).strip().lower()
        if outsourcing_status not in OUTSOURCING_STATUSES:
            errors.append(f"{name}: invalid outsourcing_status")
        if outsourcing_status == "closed" or clean_scores["partnership_openness"] == 0:
            errors.append(f"{name}: explicitly closed to outside partnerships")

        usdt_status = str(item["usdt_status"]).strip().lower()
        usdt_score = clean_scores["usdt_readiness"]
        if usdt_status not in USDT_STATUSES:
            errors.append(f"{name}: invalid usdt_status")
        elif usdt_status == "verified_settlement_readiness" and usdt_score != 10:
            errors.append(f"{name}: verified settlement readiness must score 10")
        elif usdt_status == "strong_capability" and not 8 <= usdt_score <= 10:
            errors.append(f"{name}: strong USDT capability must score 8-10")
        elif usdt_status == "weak_capability" and not 1 <= usdt_score <= 7:
            errors.append(f"{name}: weak USDT capability must score 1-7")
        elif usdt_status in {"unknown", "no"} and usdt_score != 0:
            errors.append(f"{name}: unknown/no USDT readiness must score 0")

        score_status = (
            reply_behavior_status
            if reply_behavior_status in REPLY_BEHAVIOR_STATUSES
            else "not_found"
        )
        reply_score, reply_score_effective, reply_score_raw, reply_score_basis = reply_score_details(
            score_status, clean_scores
        )
        client_score = sum(clean_scores[key] for key in (
            "existing_clients", "client_type_fit", "decision_maker_access",
            "commercial_activity",
        ))
        raw_total = (
            reply_score + client_score + clean_scores["geo_gap"]
            + clean_scores["partnership_openness"] + usdt_score
        )
        uncapped_total = raw_total + reply_score_raw - reply_score
        natural_tier = "S" if raw_total >= 80 else "A" if raw_total >= 70 else "B" if raw_total >= 60 else "Reject"
        operational_tier = "B — Reply Test Required" if reply_behavior_status != "observed" and raw_total >= 60 else natural_tier
        if raw_total < 60:
            errors.append(f"{name}: total score {raw_total} is below the acceptance threshold")
        sprint_tier, sprint_tier_reason, sprint_rank_key = assign_sprint_tier(
            item, valid_evidence, activity_age, clean_scores, observed_reply,
            score_status,
        )
        if ACTIVE_SPRINT_POOL == "P0" and sprint_tier != "P0":
            errors.append(
                f"{name}: current five-day sprint accepts P0 only; calculated {sprint_tier}"
            )

        message = str(item["first_message"]).strip()
        count = word_count(message)
        intro_markers = ("i'm ", "i’m ", "i am ", "my name is ")
        if not any(marker in message.casefold() for marker in intro_markers):
            errors.append(f"{name}: first message must include a brief self-introduction")
        if not 10 <= count <= 45:
            errors.append(f"{name}: first message has {count} words, expected 10-45")
        if message.count("?") != 1:
            errors.append(f"{name}: first message must contain exactly one question")
        question_text = message.rsplit("?", 1)[0].rsplit(".", 1)[-1]
        if word_count(question_text) > 18:
            errors.append(f"{name}: first-message question should be answerable in one short sentence")
        message_lower = message.casefold()
        if any(phrase in message_lower for phrase in FIRST_MESSAGE_BANNED):
            errors.append(f"{name}: first message contains pitch, pricing or generic language")
        if any(term in message_lower for term in ("http://", "https://", "www.", " usdt", " geo ", " aeo ", " llm ")):
            errors.append(f"{name}: first message jumps ahead of the reply-first sequence")
        hook_terms = {
            token for token in re.findall(r"[a-z0-9]+", str(item["personalization_hook"]).casefold())
            if len(token) >= 5
        }
        message_terms = set(re.findall(r"[a-z0-9]+", message_lower))
        if name.casefold() not in message_lower and len(hook_terms & message_terms) < 2:
            errors.append(f"{name}: first message is not tied to a real business observation")

        social_profiles = item.get("social_profiles") or {}
        if not isinstance(social_profiles, dict):
            errors.append(f"{name}: social_profiles must be an object")
            social_profiles = {}
        identities = [
            {
                "identity_type": "person",
                "raw_value": str(item["decision_maker_name"]).strip(),
                "normalized_value": normalize_identity("person", str(item["decision_maker_name"])),
                "source_url": str(item["decision_maker_source_url"]),
            }
        ]
        for identity_type, value in social_profiles.items():
            identity_type = str(identity_type).strip().lower()
            if identity_type not in {"facebook", "linkedin", "instagram", "x"}:
                errors.append(f"{name}: unsupported social profile type {identity_type}")
                continue
            normalized_identity = normalize_identity(identity_type, str(value))
            if not normalized_identity:
                errors.append(f"{name}: invalid {identity_type} profile URL")
                continue
            identities.append({
                "identity_type": identity_type,
                "raw_value": str(value).strip(),
                "normalized_value": normalized_identity,
                "source_url": str(value).strip(),
            })

        all_source_urls = list(dict.fromkeys(
            [str(url) for url in sources]
            + [str(item["contact_source_url"]), str(item["decision_maker_source_url"])]
            + [entry["source_url"] for entry in valid_evidence if entry["source_url"]]
        ))
        clean_scores["reply_score_raw"] = reply_score_raw
        clean_scores["reply_score_uncapped"] = reply_score
        clean_scores["reply_score_effective"] = reply_score
        clean_scores["client_score"] = client_score
        clean_scores["uncapped_total"] = uncapped_total
        clean_scores["raw_total"] = raw_total

        decision_maker_status = classify_decision_maker_status(item, clean_scores)

        item.update({
            "canonical_domain": domain,
            "discovery_channel": discovery_channel,
            "discovery_source_url": discovery_source_url,
            "discovery_source_note": discovery_source_note,
            "business_quality": business_quality,
            "distribution_gap": distribution_gap,
            "normalized_contact": contact,
            "contact_channel": str(item["contact_channel"]).lower(),
            "contact_type": str(item["contact_type"]).lower(),
            "contact_clickable_url": canonical_url,
            "research_evidence": valid_evidence,
            "score_breakdown": clean_scores,
            "reply_behavior_observed": observed_reply,
            "reply_behavior_status": reply_behavior_status,
            "reply_score_basis": reply_score_basis,
            "reply_score": reply_score,
            "reply_score_uncapped": reply_score,
            "decision_maker_status": decision_maker_status,
            "auto_reply_status": item["auto_reply_status"],
            "client_score": client_score,
            "geo_gap_score": clean_scores["geo_gap"],
            "partner_score": clean_scores["partnership_openness"],
            "usdt_score": usdt_score,
            "raw_total": raw_total,
            "operational_tier": operational_tier,
            "sprint_tier": sprint_tier,
            "sprint_tier_reason": sprint_tier_reason,
            "sprint_rank_key": sprint_rank_key,
            "evidence_certainty": evidence_certainty(valid_evidence),
            "fit_level": sprint_tier,
            "geo_maturity": geo_maturity,
            "outsourcing_status": outsourcing_status,
            "usdt_status": usdt_status,
            "identities": identities,
            "source_urls": all_source_urls,
            "outreach_message": message,
            "stage": "ready",
            "tags": list(dict.fromkeys(
                ["prompt-v3", "prompt-v4-off-search", "p0-3d-sprint", "web3-geo", "off-search-discovery"]
                + [str(x).strip() for x in item.get("tags", []) if str(x).strip()]
            )),
            "outreach_quality": {
                "specific": True, "reply_first": True, "no_pitch": True,
                "one_question": True, "word_count": count,
            },
        })
        normalized_rows.append(item)

    if not normalized_rows:
        errors.append("P0 sprint produced no qualified prospects")
    track_counts = Counter(item.get("track") for item in normalized_rows)
    if set(track_counts) - {"web3_geo"}:
        errors.append(f"P0 sprint accepts Web3 only: tracks={dict(track_counts)}")
    channel_counts = Counter(item.get("contact_channel") for item in normalized_rows)
    if set(channel_counts) - {"whatsapp", "telegram"}:
        errors.append(f"unsupported sprint contact channels: {dict(channel_counts)}")
    if channel_counts.get("telegram", 0) > MAX_TELEGRAM:
        errors.append(f"Telegram count exceeds the retained maximum of {MAX_TELEGRAM}")
    for item in normalized_rows:
        if item["contact_channel"] != "telegram":
            continue
        name = item["company_name"]
        if item["sprint_tier"] != "P0":
            errors.append(f"{name}: current Telegram output must qualify for P0")
        if item["contact_type"] not in TOP_TELEGRAM_CONTACT_TYPES:
            errors.append(f"{name}: Telegram must reach a person, founder, sales or business account")
        score = item.get("telegram_quality_score")
        if not isinstance(score, int) or isinstance(score, bool) or score < TELEGRAM_MIN_QUALITY_SCORE:
            errors.append(f"{name}: Telegram quality score must be >= {TELEGRAM_MIN_QUALITY_SCORE}")
        if not str(item.get("telegram_quality_reason", "")).strip():
            errors.append(f"{name}: missing Telegram quality assessment")

    domains = [item["canonical_domain"] for item in normalized_rows]
    contacts = [(item["contact_channel"], item["normalized_contact"]) for item in normalized_rows]
    people = [item["identities"][0]["normalized_value"] for item in normalized_rows]
    identity_keys = [
        (identity["identity_type"], identity["normalized_value"])
        for item in normalized_rows for identity in item["identities"]
    ]
    if len(domains) != len(set(domains)):
        errors.append("batch contains duplicate domains")
    if len(contacts) != len(set(contacts)):
        errors.append("batch contains duplicate contacts")
    if len(people) != len(set(people)):
        errors.append("batch contains duplicate decision-maker names")
    if len(identity_keys) != len(set(identity_keys)):
        errors.append("batch contains duplicate person or social identities")

    existing_domains = {row[0] for row in conn.execute("SELECT canonical_domain FROM companies")}
    existing_contacts = {(row[0], row[1]) for row in conn.execute("SELECT channel, normalized_value FROM contacts")}
    existing_identities = {
        (row[0], row[1])
        for row in conn.execute("SELECT identity_type, normalized_value FROM prospect_identities")
    }
    for item in normalized_rows:
        if item["canonical_domain"] in existing_domains:
            errors.append(f"{item['company_name']}: historical duplicate domain")
        if (item["contact_channel"], item["normalized_contact"]) in existing_contacts:
            errors.append(f"{item['company_name']}: historical duplicate contact")
        for identity in item["identities"]:
            key = (identity["identity_type"], identity["normalized_value"])
            if key in existing_identities:
                errors.append(f"{item['company_name']}: historical duplicate {identity['identity_type']}")

    existing_names = list(conn.execute("SELECT company_name, country, company_id FROM companies"))
    for item in normalized_rows:
        candidate_name = normalize_company_name(item["company_name"])
        for old_name, old_country, old_id in existing_names:
            if str(old_country).casefold() != str(item["country"]).casefold():
                continue
            score = SequenceMatcher(None, candidate_name, normalize_company_name(old_name)).ratio()
            if score >= 0.88:
                errors.append(f"{item['company_name']}: fuzzy historical duplicate {old_id} ({score:.2f})")

    if errors:
        raise ValueError("\n".join(errors))
    return normalized_rows


def run_id_for(day: str, source_bytes: bytes) -> str:
    suffix = hashlib.sha256(day.encode("ascii") + b"|" + source_bytes).hexdigest()[:8].upper()
    return f"RUN-{day}-{suffix}"


def insert_run(
    conn: sqlite3.Connection,
    day: str,
    run_id: str,
    rows: list[dict[str, Any]],
) -> None:
    stamp = now_iso()
    with conn:
        previous = conn.execute(
            "SELECT status FROM daily_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if previous:
            raise RuntimeError(f"identical source was already processed as {run_id}")
        conn.execute(
            """
            INSERT INTO daily_runs(
                run_id, run_date, started_at, web3_target, handmade_target,
                web3_qualified, handmade_qualified, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                run_id,
                day,
                stamp,
                len(rows),
                HANDMADE_TARGET,
                len(rows),
                HANDMADE_TARGET,
                f"Prompt v4 off-search P0 sprint passed: {len(rows)} evidence-qualified Web3 prospects; no quota filling",
            ),
        )
        used_ids = {row[0] for row in conn.execute("SELECT company_id FROM companies")}
        for item in rows:
            attempt = 0
            company_id = stable_company_id(item, attempt)
            while company_id in used_ids:
                attempt += 1
                company_id = stable_company_id(item, attempt)
            used_ids.add(company_id)
            item["company_id"] = company_id
            conn.execute(
                """
                INSERT INTO companies(
                    company_id, company_name, canonical_domain, website_url, country, track,
                    industry, business_summary, company_size_estimate, size_confidence,
                    activity_signal, public_crypto_signal, crypto_signal_source_url,
                    verified_facts_json, cautious_inference, personalization_hook,
                    fit_level, fit_reason, source_urls_json, outreach_message,
                    outreach_quality_json, first_seen_at, last_seen_at, times_found,
                    stage, do_not_contact, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, 1, 'ready', 0, ?, ?
                )
                """,
                (
                    company_id, item["company_name"], item["canonical_domain"],
                    item["website_url"], item["country"], item["track"], item["industry"],
                    item["business_summary"], item["company_size_estimate"],
                    item["size_confidence"], item["activity_signal"],
                    item.get("public_crypto_signal", ""),
                    item.get("crypto_signal_source_url", ""),
                    json.dumps(item["verified_facts"], ensure_ascii=False),
                    item["cautious_inference"], item["personalization_hook"],
                    item["fit_level"], item["fit_reason"],
                    json.dumps(item["source_urls"], ensure_ascii=False),
                    item["first_message"],
                    json.dumps(item["outreach_quality"], ensure_ascii=False),
                    stamp, stamp, stamp, stamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO contacts(
                    company_id, channel, raw_value, normalized_value, clickable_url,
                    contact_type, source_url, verified_at, is_valid, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    company_id, item["contact_channel"], item["contact_value"],
                    item["normalized_contact"], item["contact_clickable_url"],
                    item["contact_type"], item["contact_source_url"],
                    item["contact_verified_at"], stamp, stamp,
                ),
            )
            for identity in item["identities"]:
                conn.execute(
                    """
                    INSERT INTO prospect_identities(
                        company_id, identity_type, raw_value, normalized_value,
                        source_url, verified_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id, identity["identity_type"], identity["raw_value"],
                        identity["normalized_value"], identity["source_url"],
                        item["contact_verified_at"], stamp,
                    ),
                )
            primary_source = item["source_urls"][0]
            for fact in item["verified_facts"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence(
                        company_id, evidence_type, claim, source_url, verified_at,
                        is_verified_fact, created_at, evidence_label
                    ) VALUES (?, 'verified_fact', ?, ?, ?, 1, ?, 'observed')
                    """,
                    (company_id, fact, primary_source, item["contact_verified_at"], stamp),
                )
            if item.get("public_crypto_signal") and item.get("crypto_signal_source_url"):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence(
                        company_id, evidence_type, claim, source_url, verified_at,
                        is_verified_fact, created_at, evidence_label
                    ) VALUES (?, 'public_crypto_signal', ?, ?, ?, 1, ?, 'observed')
                    """,
                    (
                        company_id, item["public_crypto_signal"],
                        item["crypto_signal_source_url"], item["contact_verified_at"], stamp,
                    ),
                )
            conn.execute(
                """
                INSERT OR IGNORE INTO evidence(
                    company_id, evidence_type, claim, source_url, verified_at,
                    is_verified_fact, created_at, evidence_label
                ) VALUES (?, 'cautious_inference', ?, ?, ?, 0, ?, 'inferred')
                """,
                (
                    company_id, item["cautious_inference"], primary_source,
                    item["contact_verified_at"], stamp,
                ),
            )
            for entry in item["research_evidence"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence(
                        company_id, evidence_type, claim, source_url, verified_at,
                        is_verified_fact, created_at, evidence_label
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id, entry["category"], entry["claim"], entry["source_url"],
                        item["contact_verified_at"],
                        1 if entry["label"] == "observed" else 0,
                        stamp, entry["label"],
                    ),
                )
            qualification_questions = [
                "Do clients ask about visibility in ChatGPT, Gemini, Perplexity or AI Overviews?",
                "Is that work handled in-house?",
                "Are you open to outside delivery, referral or white-label fulfilment?",
                "Are you comfortable settling international partner invoices in USDT?",
                "If yes, which network do you normally use?",
            ]
            conn.execute(
                """
                INSERT INTO partnership_assessments(
                    company_id, decision_maker_name, decision_maker_role,
                    decision_maker_source_url, recent_activity_at,
                    recent_activity_evidence, reply_behavior_observed,
                    reply_behavior_evidence, reply_openness_evidence,
                    client_evidence, geo_maturity, geo_maturity_evidence,
                    partnership_evidence, outsourcing_status, usdt_status,
                    usdt_evidence, reply_score, reply_score_uncapped,
                    client_score, geo_gap_score, partner_score, usdt_score,
                    raw_total, operational_tier, score_breakdown_json,
                    qualification_questions_json, assessment_source_urls_json,
                    assessed_at, created_at, updated_at,
                    sprint_tier, evidence_certainty, sprint_rank_key_json,
                    decision_maker_status, auto_reply_status
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    company_id, item["decision_maker_name"], item["decision_maker_role"],
                    item["decision_maker_source_url"], item["recent_activity_at"],
                    evidence_text(item["research_evidence"], "recent_activity"),
                    1 if item["reply_behavior_observed"] else 0,
                    evidence_text(item["research_evidence"], "reply_behavior"),
                    evidence_text(item["research_evidence"], "contact_openness"),
                    evidence_text(item["research_evidence"], "client"),
                    item["geo_maturity"],
                    evidence_text(item["research_evidence"], "geo_maturity"),
                    evidence_text(item["research_evidence"], "partnership"),
                    item["outsourcing_status"], item["usdt_status"],
                    evidence_text(item["research_evidence"], "usdt"),
                    item["reply_score"], item["reply_score_uncapped"],
                    item["client_score"], item["geo_gap_score"],
                    item["partner_score"], item["usdt_score"], item["raw_total"],
                    item["operational_tier"],
                    json.dumps(item["score_breakdown"], ensure_ascii=False),
                    json.dumps(qualification_questions, ensure_ascii=False),
                    json.dumps(item["source_urls"], ensure_ascii=False),
                    item["contact_verified_at"], stamp, stamp,
                    item["sprint_tier"], item["evidence_certainty"],
                    json.dumps(item["sprint_rank_key"], ensure_ascii=False),
                    item["decision_maker_status"], item["auto_reply_status"],
                ),
            )
            for tag in item["tags"]:
                conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
                tag_id = conn.execute("SELECT tag_id FROM tags WHERE name=?", (tag,)).fetchone()[0]
                conn.execute(
                    "INSERT OR IGNORE INTO company_tags(company_id, tag_id) VALUES (?, ?)",
                    (company_id, tag_id),
                )
            conn.execute(
                """
                INSERT INTO daily_candidates(
                    run_id, company_id, candidate_name, track, disposition,
                    exclusion_reason, candidate_json, created_at
                ) VALUES (?, ?, ?, ?, 'new', '', ?, ?)
                """,
                (
                    run_id, company_id, item["company_name"], item["track"],
                    json.dumps(item, ensure_ascii=False), stamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO company_stage_history(
                    company_id, from_stage, to_stage, reason, changed_at
                ) VALUES (?, NULL, 'ready', 'qualified daily import', ?)
                """,
                (company_id, stamp),
            )


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def yaml_quote(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def display_status(value: Any) -> str:
    """Keep storage enums stable while rendering the user-facing Unknown label."""
    text = str(value).strip()
    return "Unknown" if text.casefold() == "unknown" else text


def render_card(item: dict[str, Any], vault: Path, stamp: str) -> None:
    folder = "Web3" if item["track"] == "web3_geo" else "Handmade"
    path = vault / "ProspectOS" / "Companies" / folder / f"{item['company_id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    tag_json = json.dumps(item["tags"], ensure_ascii=False)
    fact_lines = "\n".join(f"- {fact}" for fact in item["verified_facts"])
    source_lines = "\n".join(f"- [{url}]({url})" for url in item["source_urls"])
    evidence_rows = []
    for entry in item["research_evidence"]:
        source = f"[来源]({entry['source_url']})" if entry["source_url"] else "无来源"
        evidence_rows.append(
            f"| {entry['category']} | {entry['label']} | "
            f"{markdown_escape(entry['claim'])} | {source} |"
        )
    telegram_quality_section = ""
    if item["contact_channel"] == "telegram":
        telegram_quality_section = f"""
## Telegram 质量评估

- 评分：{item['telegram_quality_score']}/100
- 结论：{item['telegram_quality_reason']}
"""
    text = f"""---
company_id: {yaml_quote(item['company_id'])}
company_name: {yaml_quote(item['company_name'])}
domain: {yaml_quote(item['canonical_domain'])}
website: {yaml_quote(item['website_url'])}
country: {yaml_quote(item['country'])}
track: {yaml_quote(item['track'])}
industry: {yaml_quote(item['industry'])}
discovery_channel: {yaml_quote(item['discovery_channel'])}
discovery_source: {yaml_quote(item['discovery_source_url'])}
business_quality: {yaml_quote(item['business_quality'])}
distribution_gap: {yaml_quote(item['distribution_gap'])}
fit_level: {yaml_quote(item['sprint_tier'])}
raw_total: {item['raw_total']}
sprint_tier: {yaml_quote(item['sprint_tier'])}
evidence_certainty: {yaml_quote(item['evidence_certainty'])}
reply_observed: {str(item['reply_behavior_observed']).lower()}
reply_behavior_status: {yaml_quote(item['reply_behavior_status'])}
reply_score: {item['reply_score_uncapped']}/30
decision_maker_status: {yaml_quote(display_status(item['decision_maker_status']))}
auto_reply_status: {yaml_quote(display_status(item['auto_reply_status']))}
geo_maturity: {yaml_quote(item['geo_maturity'])}
usdt_status: {yaml_quote(item['usdt_status'])}
stage: "ready"
contact_channel: {yaml_quote(item['contact_channel'])}
contact_url: {yaml_quote(item['contact_clickable_url'])}
contact_source: {yaml_quote(item['contact_source_url'])}
first_seen_at: {yaml_quote(stamp)}
last_seen_at: {yaml_quote(stamp)}
last_contacted_at: ""
next_follow_up_at: ""
do_not_contact: false
tags: {tag_json}
---

# {item['company_name']}

> [!info] SQLite 是唯一真实数据源
> 此卡片由工作流1生成。消息必须人工检查和发送，系统不会自动联系商家。

## 决策人

- 姓名：{item['decision_maker_name']}
- 角色：{item['decision_maker_role']}
- 是否决策人：{display_status(item['decision_maker_status'])}
- 来源：[{item['decision_maker_source_url']}]({item['decision_maker_source_url']})

## 公司简介

{item['business_summary']}

## 发现链路与搜索诊断

- 发现渠道：{item['discovery_channel']}
- 发现来源：[{item['discovery_source_url']}]({item['discovery_source_url']})
- 发现记录：{item['discovery_source_note']}
- 业务质量：{item['business_quality']}（先验证业务，再判断搜索）
- 搜索分发缺口：{item['distribution_gap']}（Google/Bing/AI Search仅作为诊断证据）

## 5天冲刺分层

- 当前池：{item['sprint_tier']}
- 证据确定性：{item['evidence_certainty']}
- 分层理由：{item['sprint_tier_reason']}
- 最近活动：{item['recent_activity_at']}
- 团队规模：{item['company_size_estimate']}

## 已验证事实

{fact_lines}

## 谨慎推断

{item['cautious_inference']}

## v2 五维评分

| 维度 | 得分 |
|---|---:|
| Reply Score（回复概率） | {item['reply_score_uncapped']}/30 |
| 有效计分贡献 | {item['reply_score']}/30 |
| 客户/渠道价值 | {item['client_score']}/25 |
| GEO交付缺口 | {item['geo_gap_score']}/20 |
| 合作开放度 | {item['partner_score']}/15 |
| USDT就绪度 | {item['usdt_score']}/10 |
| **总分** | **{item['raw_total']}/100** |

- 运营等级：{item['operational_tier']}
- Reply Behaviour：{item['reply_behavior_status']}
- Reply Score计算依据：{item['reply_score_basis']}
- 回复行为证据：{reply_behavior_display(item)}
- 自动回复：{display_status(item['auto_reply_status'])}
- GEO成熟度：{item['geo_maturity']}
- 外包/合作状态：{item['outsourcing_status']}
- USDT状态：{item['usdt_status']}（不等同于确认接受USDT付款）

{telegram_quality_section}

## 个性化观察

{item['personalization_hook']}

## 首条开场消息

{item['first_message']}

> 首条消息只用于获得回复：不推销、不发网站、不谈价格、不约电话、不提前询问USDT。

> 跟进规则：人工发送后等待24–48小时，最多补发一次简短跟进；仍无回复就停止，不自动联系。

## 联系方式

| 渠道 | 联系方式类型 | 是否决策人 | 是否自动回复 | 链接 | 来源 | 状态 |
|---|---|---|---|---|---|---|
| {item['contact_channel']} | {item['contact_type']} | {display_status(item['decision_maker_status'])} | {display_status(item['auto_reply_status'])} | [打开]({item['contact_clickable_url']}) | [来源]({item['contact_source_url']}) | 有效 |

## 证据来源

{source_lines}

## v2 证据明细

| 类别 | 标签 | 内容 | 来源 |
|---|---|---|---|
{chr(10).join(evidence_rows)}

## 回复后的资格确认顺序

1. 确认真实客户类型。
2. 询问客户是否提出ChatGPT、Gemini、Perplexity或AI Overviews可见性需求。
3. 确认是否内部交付。
4. 确认是否接受外部交付、推荐或白标合作。
5. 最后才确认国际合作发票是否可用USDT结算及常用网络。

## 最近互动历史

| 时间 | 类型 | 状态变化 | 原始反馈 |
|---|---|---|---|
| - | - | - | 暂无互动 |

## 人工笔记

<!-- USER-NOTES-START -->

<!-- USER-NOTES-END -->
"""
    path.write_text(text, encoding="utf-8")


def render_outputs(
    conn: sqlite3.Connection,
    day: str,
    run_id: str,
    rows: list[dict[str, Any]],
    vault: Path,
) -> tuple[Path, Path]:
    report_dir = vault / "ProspectOS" / "Daily Reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    run_suffix = run_id.rsplit("-", 1)[-1]
    report_stem = f"{day}-{ACTIVE_SPRINT_POOL}-{run_suffix}"
    report_path = report_dir / f"{report_stem}.md"
    csv_path = report_dir / f"{report_stem}.csv"
    stamp = now_iso()
    ordered = sorted(
        rows,
        key=lambda x: tuple(x["sprint_rank_key"])
        + (-x["raw_total"], x["company_name"].casefold()),
    )
    headers = [
        "排名", "冲刺池", "证据确定性", "分层理由", "company_id", "决策人/公司", "角色",
        "联系人身份", "联系方式类型", "是否决策人", "是否自动回复",
        "企业规模", "最近活动", "国家", "主要业务", "官网",
        "发现渠道", "发现来源", "业务质量", "搜索分发缺口",
        "近期活动证据", "Reply Behaviour状态", "公开回复行为", "联系开放度", "客户证据",
        "USDT状态", "USDT证据", "GEO成熟度", "合作证据",
        "Reply Score /30", "有效回复贡献/30", "客户/25", "GEO缺口/20", "合作/15", "USDT/10",
        "总分/100", "运营等级", "公开联系方式", "联系方式来源", "最佳首条消息",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for rank, item in enumerate(ordered, 1):
            writer.writerow(
                [
                    rank, item["sprint_tier"], item["evidence_certainty"],
                    item["sprint_tier_reason"], item["company_id"],
                    f"{item['decision_maker_name']} / {item['company_name']}",
                    item["decision_maker_role"],
                    item["decision_maker_name"], item["contact_type"],
                    display_status(item["decision_maker_status"]),
                    display_status(item["auto_reply_status"]),
                    item["company_size_estimate"],
                    item["recent_activity_at"], item["country"], item["industry"],
                    item["website_url"],
                    item["discovery_channel"], item["discovery_source_url"],
                    item["business_quality"], item["distribution_gap"],
                    evidence_text(item["research_evidence"], "recent_activity"),
                    item["reply_behavior_status"],
                    reply_behavior_display(item),
                    evidence_text(item["research_evidence"], "contact_openness"),
                    evidence_text(item["research_evidence"], "client"),
                    item["usdt_status"], evidence_text(item["research_evidence"], "usdt"),
                    item["geo_maturity"], evidence_text(item["research_evidence"], "partnership"),
                    item["reply_score_uncapped"], item["reply_score"],
                    item["client_score"], item["geo_gap_score"],
                    item["partner_score"], item["usdt_score"], item["raw_total"],
                    item["operational_tier"], item["contact_clickable_url"],
                    item["contact_source_url"], item["first_message"],
                ]
            )
    table_rows = []
    for rank, item in enumerate(ordered, 1):
        facebook_url = str((item.get("social_profiles") or {}).get("facebook", "")).strip()
        contact_links = f"[{item['contact_channel'].title()}]({item['contact_clickable_url']})"
        if facebook_url:
            contact_links += f" · [Facebook]({facebook_url})"
        table_rows.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    markdown_escape(item["sprint_tier"]),
                    markdown_escape(item["decision_maker_name"]),
                    markdown_escape(f"{item['decision_maker_name']} / {item['company_name']}"),
                    markdown_escape(item["decision_maker_role"]),
                    markdown_escape(display_status(item["decision_maker_status"])),
                    markdown_escape(item["contact_type"]),
                    markdown_escape(display_status(item["auto_reply_status"])),
                    markdown_escape(item["company_size_estimate"]),
                    markdown_escape(item["recent_activity_at"]),
                    markdown_escape(evidence_text(item["research_evidence"], "recent_activity")),
                    markdown_escape(item["reply_behavior_status"]),
                    markdown_escape(f"{item['reply_score_uncapped']}/30"),
                    markdown_escape(reply_behavior_display(item)),
                    markdown_escape(item["fit_reason"]),
                    markdown_escape(evidence_text(item["research_evidence"], "partnership")),
                    markdown_escape(
                        f"{item['usdt_status']}: "
                        f"{evidence_text(item['research_evidence'], 'usdt')}"
                    ),
                    markdown_escape(item["evidence_certainty"]),
                    contact_links,
                    markdown_escape(item["sprint_tier_reason"]),
                    markdown_escape(item["first_message"]),
                ]
            )
            + " |"
        )
    due = list(
        conn.execute(
            """
            SELECT company_id, company_name, next_follow_up_at
            FROM companies
            WHERE stage='not_now' AND next_follow_up_at IS NOT NULL
              AND substr(next_follow_up_at, 1, 10) <= ?
            ORDER BY next_follow_up_at
            """,
            (day,),
        )
    )
    due_rows = "\n".join(f"| {r[0]} | {markdown_escape(r[1])} | {r[2]} |" for r in due)
    if not due_rows:
        due_rows = "| - | - | 今日无到期跟进 |"
    discovery_rows = "\n".join(
        "| "
        + " | ".join(
            [
                str(rank),
                markdown_escape(item["company_name"]),
                markdown_escape(item["discovery_channel"]),
                f"[来源]({item['discovery_source_url']})",
                markdown_escape(item["business_quality"]),
                markdown_escape(item["distribution_gap"]),
            ]
        )
        + " |"
        for rank, item in enumerate(ordered, 1)
    )
    if not discovery_rows:
        discovery_rows = "| - | - | - | - | - | - |"
    review_count = conn.execute(
        "SELECT COUNT(*) FROM dedupe_review_queue WHERE status='open'"
    ).fetchone()[0]
    report = f"""---
report_date: "{day}"
run_id: "{run_id}"
generated_at: "{stamp}"
---

# Prospect OS 日报 — {day}

## 1. 执行摘要

- 当前模式：只输出 🔥 P0 — 3-Day Controlled Sprint，不设数量目标，不为凑数降标准。
- 本轮P0：{len(ordered)}家Web3；WhatsApp {sum(x['contact_channel'] == 'whatsapp' for x in ordered)}家；Telegram {sum(x['contact_channel'] == 'telegram' for x in ordered)}家。
- 排序优先级：回复概率 → 决策人概率 → 真实业务价值 → 合作开放度 → GEO相关性；活动新鲜度用于门槛和同分排序。
- 发现顺序：非搜索渠道发现 → 验证独立官网与真实业务 → 最后用搜索检查分发缺口；Google、Bing、AI Search只做诊断，不做主要发现源。
- 本轮甜蜜点：业务质量为Strong、搜索分发缺口为Strong/Moderate；不因搜索差而把没有真实业务的项目塞入名单。
- Reply Behaviour分为Observed、Not found和Inaccessible：Not found最高12/30并待验证；Inaccessible只能按活跃度、联系方式和账号真实性推断。
- AI/GEO的一次提及不再自动排除；只有成熟商业化GEO交付才排除。
- 人工审核队列当前未解决：{review_count}。

> [!success] P0硬门槛已满足
> 仅保留3天内活跃、最多40人团队、业务质量Strong、搜索分发缺口Strong/Moderate、公开回复行为为Observed、且联系方式确认属于决策人的对象；客服/机器人/明确自动回复路径不占用P0名额。

## 2. 🔥 P0 — 3-Day Controlled Sprint

| 排名 | 池 | 联系人身份 | 决策人/公司 | 角色 | 是否决策人 | 联系方式类型 | 是否自动回复 | 规模 | 最近活动 | 最近活动证据 | Reply Behaviour状态 | Reply Score /30 | 回复行为证据 | 资源/GEO匹配 | 合作证据 | USDT/加密证据 | 确定性 | 联系方式 | 分层理由 | 推荐首条消息 |
|---:|---|---|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|---|
{chr(10).join(table_rows)}

### 发现链路摘要

| 排名 | 公司 | 非搜索发现渠道 | 发现来源 | 业务质量 | 搜索分发缺口 |
|---:|---|---|---|---|---|
{discovery_rows}

## 3. 到期跟进

| company_id | 公司名称 | next_follow_up_at |
|---|---|---|
{due_rows}

## 4. 人工审核队列

- 今日新增待审核：0
- 当前未解决：{review_count}

## 5. 数据质量提醒

- 每家均保存来源页、可点击联系方式、决策人身份、证据标签和完整评分明细。
- Telegram本批次最多3家并维持质量门槛；其他情况下优先WhatsApp。
- 每家必须保留发现渠道、发现来源、业务质量和搜索分发缺口；发现来源不能等同于客户官网。
- 先看业务质量和活跃度，再看SEO/GEO；搜索诊断不能反过来成为客户发现方式。
- Reply Behaviour必须单独标记：Observed按证据强度计分；Not found最高12/30并标记待验证；Inaccessible只能标记Inferred，不能标记Observed。
- 联系人身份、联系方式类型、最近活动证据、回复行为证据、是否决策人和是否自动回复必须单独标注；Unknown不当作正面证据。
- USDT技术能力与确认接受USDT结算分开记录，未确认时绝不写“接受USDT”。
- 首条消息必须有简短自我介绍、一个真实业务观察和一个易于一句话回答的问题；不立即发网站、价格、长篇介绍，也不主动强调GEO/ChatGPT/Gemini/AI Search。
- 人工发送后24–48小时最多跟进一次，仍不回复就停止；自动回复、菜单或“已送达未回复”不能直接判定为拒绝。
- Reply Score /30 独立表示回复概率，不因GEO、AI或Web3熟悉度加分；只有Observed且联系人为决策人时才允许进入P0；排序优先级为回复概率 → 决策人概率 → 真实业务 → 合作开放度 → GEO相关性。
- 首条消息只用于获得回复；外联仍由人工检查和发送。
- 不保证回复、排名、流量、销量或转化。
"""
    report_path.write_text(report, encoding="utf-8")
    for item in rows:
        render_card(item, vault, stamp)
    render_dashboard(conn, vault, day, stamp)
    render_views(conn, vault, day, stamp)
    return report_path, csv_path


def render_dashboard(conn: sqlite3.Connection, vault: Path, day: str, stamp: str) -> None:
    counts = {
        "companies": conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        "ready": conn.execute(
            "SELECT COUNT(*) FROM companies WHERE stage IN ('discovered','verified','qualified','ready')"
        ).fetchone()[0],
        "contacted": conn.execute(
            "SELECT COUNT(*) FROM companies WHERE stage='contacted'"
        ).fetchone()[0],
        "interested": conn.execute(
            "SELECT COUNT(*) FROM companies WHERE stage='interested'"
        ).fetchone()[0],
        "review": conn.execute(
            "SELECT COUNT(*) FROM dedupe_review_queue WHERE status='open'"
        ).fetchone()[0],
        "dnc": conn.execute(
            "SELECT COUNT(*) FROM companies WHERE do_not_contact=1"
        ).fetchone()[0],
    }
    text = f"""# Prospect OS Dashboard

更新时间：{stamp}

> [!important] 数据源规则
> SQLite 是唯一真实数据源；这里的卡片、视图和日报由工作流生成。实际消息必须人工检查和发送。

> [!warning] 当前5天冲刺硬门槛
> 只输出 P0：回复概率优先，其次是决策人可达、真实业务与合作开放度；同时要求非搜索渠道发现、业务质量Strong、搜索分发缺口Strong/Moderate、3天内活跃、最多40人团队、资源/GEO匹配，并至少有一项强确认信号。客服/机器人/明确自动回复路径不占用P0名额。

今日正式输出：按P0质量门槛生成；不为凑数降低标准。

## 当前概览

| 指标 | 数量 |
|---|---:|
| 公司总数 | {counts['companies']} |
| 等待联系 | {counts['ready']} |
| 已联系未回复 | {counts['contacted']} |
| 感兴趣 | {counts['interested']} |
| 去重人工审核 | {counts['review']} |
| do_not_contact | {counts['dnc']} |

## 快捷入口

- [[Views/今日新商家|今日新商家]]
- [[Views/等待联系|等待联系]]
- [[Views/到期跟进|到期跟进]]
- [[Views/去重人工审核|去重人工审核]]
- [[Views/Prospect OS.base|Bases 动态视图]]
- [[Feedback/Feedback Inbox|填写联系反馈]]
- [[Daily Reports|日报目录（最新P0报告按时间保存）]]
- [[System/scheduled-task-setup|定时任务说明]]
"""
    (vault / "ProspectOS" / "Dashboard.md").write_text(text, encoding="utf-8")


def render_views(conn: sqlite3.Connection, vault: Path, day: str, stamp: str) -> None:
    views_dir = vault / "ProspectOS" / "Views"
    views_dir.mkdir(parents=True, exist_ok=True)
    company_views = {
        "今日新商家.md": ("今日新商家", "substr(c.first_seen_at,1,10)=?", (day,)),
        "Web3商家.md": ("Web3 商家", "c.track='web3_geo'", ()),
        "手工商家.md": ("手工商家", "c.track='handmade_visual'", ()),
        "等待联系.md": (
            "等待联系",
            "c.stage IN ('discovered','verified','qualified','ready') AND c.do_not_contact=0",
            (),
        ),
        "已联系未回复.md": ("已联系未回复", "c.stage='contacted'", ()),
        "已回复.md": ("已回复", "c.stage='replied'", ()),
        "感兴趣.md": ("感兴趣", "c.stage='interested'", ()),
        "到期跟进.md": (
            "到期跟进",
            "c.stage='not_now' AND c.next_follow_up_at IS NOT NULL "
            "AND substr(c.next_follow_up_at,1,10)<=?",
            (day,),
        ),
        "do_not_contact.md": (
            "do_not_contact",
            "(c.do_not_contact=1 OR c.stage='do_not_contact')",
            (),
        ),
    }
    for filename, (title, where_sql, params) in company_views.items():
        records = list(
            conn.execute(
                f"""
                SELECT c.company_id, c.company_name, c.country, c.track, c.stage,
                       c.next_follow_up_at, ct.clickable_url
                FROM companies c
                LEFT JOIN contacts ct ON ct.contact_id=(
                    SELECT MIN(c2.contact_id) FROM contacts c2
                    WHERE c2.company_id=c.company_id AND c2.is_valid=1
                )
                WHERE {where_sql}
                ORDER BY c.track, c.company_name COLLATE NOCASE
                """,
                params,
            )
        )
        lines = []
        for company_id, name, country, track, stage, next_follow, contact_url in records:
            folder = "Web3" if track == "web3_geo" else "Handmade"
            contact = f"[打开]({contact_url})" if contact_url else "无有效联系方式"
            lines.append(
                f"| [[../Companies/{folder}/{company_id}|{company_id}]] "
                f"| {markdown_escape(name)} | {markdown_escape(country)} | {track} "
                f"| {stage} | {contact} | {next_follow or ''} |"
            )
        if not lines:
            lines.append("| - | 暂无 | - | - | - | - | - |")
        content = f"""# {title}

更新时间：{stamp}

| ID | 公司 | 国家 | 类型 | Stage | 联系方式 | 下次跟进 |
|---|---|---|---|---|---|---|
{chr(10).join(lines)}

> 这是无需插件的备用视图，由工作流1从 SQLite 同步生成。
"""
        (views_dir / filename).write_text(content, encoding="utf-8")

    reviews = list(
        conn.execute(
            """
            SELECT review_id, existing_company_id, candidate_name,
                   candidate_country, similarity_score, reason
            FROM dedupe_review_queue
            WHERE status='open'
            ORDER BY created_at
            """
        )
    )
    review_lines = [
        f"| {r[0]} | {r[1]} | {markdown_escape(r[2])} | {markdown_escape(r[3])} "
        f"| {r[4]:.3f} | {markdown_escape(r[5])} |"
        for r in reviews
    ]
    if not review_lines:
        review_lines.append("| - | - | 暂无 | - | - | - |")
    review_text = f"""# 去重人工审核

更新时间：{stamp}

| Review ID | 已有公司 | 候选公司 | 国家 | 相似度 | 原因 |
|---|---|---|---|---|---|
{chr(10).join(review_lines)}
"""
    (views_dir / "去重人工审核.md").write_text(review_text, encoding="utf-8")


def validate_database(
    conn: sqlite3.Connection,
    day: str,
    run_id: str,
    vault: Path,
) -> list[str]:
    issues: list[str] = []
    foreign_keys = list(conn.execute("PRAGMA foreign_key_check"))
    if foreign_keys:
        issues.append(f"foreign key issues: {foreign_keys}")
    counts = dict(
        conn.execute(
            """
            SELECT track, COUNT(*)
            FROM daily_candidates
            WHERE run_id=? AND disposition='new'
            GROUP BY track
            """,
            (run_id,),
        )
    )
    expected_count = conn.execute(
        "SELECT COUNT(*) FROM daily_candidates WHERE run_id=? AND disposition='new'",
        (run_id,),
    ).fetchone()[0]
    if counts != {"web3_geo": expected_count} or expected_count < 1:
        issues.append(f"run track counts invalid: {counts}")
    channel_counts = dict(
        conn.execute(
            """
            SELECT ct.channel, COUNT(*)
            FROM daily_candidates dc
            JOIN contacts ct ON ct.company_id=dc.company_id AND ct.is_valid=1
            WHERE dc.run_id=? AND dc.disposition='new'
            GROUP BY ct.channel
            """,
            (run_id,),
        )
    )
    if set(channel_counts) - {"telegram", "whatsapp"}:
        issues.append(f"run contact channels invalid: {channel_counts}")
    if channel_counts.get("telegram", 0) > MAX_TELEGRAM:
        issues.append(f"run contains too many Telegram prospects: {channel_counts}")
    invalid_contacts = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_candidates dc
        JOIN contacts ct ON ct.company_id=dc.company_id
        WHERE dc.run_id=? AND dc.disposition='new' AND ct.is_valid<>1
        """,
        (run_id,),
    ).fetchone()[0]
    if invalid_contacts:
        issues.append(f"run contains {invalid_contacts} invalid contacts")
    assessment_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_candidates dc
        JOIN partnership_assessments pa ON pa.company_id=dc.company_id
        WHERE dc.run_id=? AND dc.disposition='new'
        """,
        (run_id,),
    ).fetchone()[0]
    if assessment_count != expected_count:
        issues.append(f"run has {assessment_count} assessments, expected {expected_count}")
    invalid_tiers = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_candidates dc
        JOIN partnership_assessments pa ON pa.company_id=dc.company_id
        WHERE dc.run_id=? AND dc.disposition='new'
          AND pa.operational_tier NOT IN ('S', 'A', 'B — Reply Test Required')
        """,
        (run_id,),
    ).fetchone()[0]
    if invalid_tiers:
        issues.append(f"run contains {invalid_tiers} invalid operational tiers")
    invalid_sprint_tiers = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_candidates dc
        JOIN partnership_assessments pa ON pa.company_id=dc.company_id
        WHERE dc.run_id=? AND dc.disposition='new' AND pa.sprint_tier<>'P0'
        """,
        (run_id,),
    ).fetchone()[0]
    if invalid_sprint_tiers:
        issues.append(f"run contains {invalid_sprint_tiers} non-P0 prospects")
    run_suffix = run_id.rsplit("-", 1)[-1]
    report_stem = f"{day}-{ACTIVE_SPRINT_POOL}-{run_suffix}"
    report_path = vault / "ProspectOS" / "Daily Reports" / f"{report_stem}.md"
    csv_path = vault / "ProspectOS" / "Daily Reports" / f"{report_stem}.csv"
    if not report_path.exists() or not csv_path.exists():
        issues.append("formal report or CSV missing")
    return issues


def execute(source: Path, day: str, db_path: Path, vault: Path, dry_run: bool) -> dict[str, Any]:
    source_bytes = source.read_bytes()
    rows = json.loads(source_bytes.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("candidate source must be a JSON array")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        ensure_v2_schema(conn)
        normalized = validate_candidates(rows, conn, day)
        if dry_run:
            return {
                "dry_run": True,
                "valid": len(normalized),
                "web3": sum(x["track"] == "web3_geo" for x in normalized),
                "handmade": sum(x["track"] == "handmade_visual" for x in normalized),
                "whatsapp": sum(x["contact_channel"] == "whatsapp" for x in normalized),
                "telegram": sum(x["contact_channel"] == "telegram" for x in normalized),
                "tiers": dict(Counter(x["operational_tier"] for x in normalized)),
                "sprint_tiers": dict(Counter(x["sprint_tier"] for x in normalized)),
                "reply_behaviour": dict(Counter(x["reply_behavior_status"] for x in normalized)),
                "discovery_channels": dict(Counter(x["discovery_channel"] for x in normalized)),
                "business_quality": dict(Counter(x["business_quality"] for x in normalized)),
                "distribution_gap": dict(Counter(x["distribution_gap"] for x in normalized)),
                "average_score": round(sum(x["raw_total"] for x in normalized) / len(normalized), 1),
            }
        run_id = run_id_for(day, source_bytes)
        insert_run(conn, day, run_id, normalized)
        report_path, csv_path = render_outputs(conn, day, run_id, normalized, vault)
        with conn:
            conn.execute(
                "UPDATE daily_runs SET status='completed', completed_at=? WHERE run_id=?",
                (now_iso(), run_id),
            )
        issues = validate_database(conn, day, run_id, vault)
        if issues:
            with conn:
                conn.execute(
                    "UPDATE daily_runs SET status='incomplete', notes=? WHERE run_id=?",
                    ("; ".join(issues), run_id),
                )
            raise RuntimeError("; ".join(issues))
        return {
            "complete": True,
            "run_id": run_id,
            "new": len(normalized),
            "duplicate": 0,
            "review": 0,
            "excluded": 0,
            "web3": len(normalized),
            "handmade": HANDMADE_TARGET,
            "whatsapp": sum(x["contact_channel"] == "whatsapp" for x in normalized),
            "telegram": sum(x["contact_channel"] == "telegram" for x in normalized),
            "sprint_tiers": dict(Counter(x["sprint_tier"] for x in normalized)),
            "discovery_channels": dict(Counter(x["discovery_channel"] for x in normalized)),
            "business_quality": dict(Counter(x["business_quality"] for x in normalized)),
            "distribution_gap": dict(Counter(x["distribution_gap"] for x in normalized)),
            "report": str(report_path),
            "csv": str(csv_path),
            "database_companies": conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "database_valid_contacts": conn.execute(
                "SELECT COUNT(*) FROM contacts WHERE is_valid=1"
            ).fetchone()[0],
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prospect OS workflow 1 compatible daily runner")
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.migrate_only:
            conn = sqlite3.connect(args.db)
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                ensure_v2_schema(conn)
                result = {
                    "complete": True,
                    "migration": "prompt-v2",
                    "database": str(args.db),
                    "historical_companies_preserved": conn.execute(
                        "SELECT COUNT(*) FROM companies"
                    ).fetchone()[0],
                }
            finally:
                conn.close()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.source is None or args.date is None:
            parser.error("source and --date are required unless --migrate-only is used")
        datetime.strptime(args.date, "%Y-%m-%d")
        result = execute(args.source, args.date, args.db, args.vault, args.dry_run)
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

