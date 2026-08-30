"""Evidence-first prospect gate for lawful, small tobacco/alcohol venues.

This is a separate track from the Web3 P0 runner.  It is deliberately
conservative:

* discovery must come from a structured, non-search source;
* the official site is used for verification, never as the discovery source;
* a map/directory record alone cannot prove the business type, current activity,
  ownership, contactability, USDT acceptance, or reply behaviour;
* unknown evidence is kept in REVIEW_REQUIRED and never promoted by quota;
* no outreach is sent by this module.

The module accepts a raw, source-first record plus separately collected
verification fields.  It does not crawl or message prospects.  Crawlers and
browser adapters should write evidence into the record, then call
``qualify_record``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Iterable
from urllib.parse import urlsplit


SEARCH_ONLY_CHANNELS = {
    "google", "bing", "search_engine", "seo_results", "ai_search",
    "search", "google_maps_search", "bing_maps_search",
}

ALLOWED_DISCOVERY_CHANNELS = {
    "company_registry", "official_business_registry", "liquor_license_registry",
    "tobacco_license_registry", "chamber_directory", "trade_directory",
    "vertical_directory", "industry_directory", "partner_directory",
    "marketplace", "association_directory", "exhibitor_list",
    "map_local_business_directory", "osm", "btcmap", "public_social_profile",
    "community_directory", "forum", "github_ecosystem_directory",
}

TARGET_BUSINESS_TYPES = {
    "tobacco_shop", "cigar_shop", "tabacaria", "tabaccheria", "tobacconist",
    "liquor_store", "wine_shop", "beer_shop", "brewery", "craft_brewery",
    "beer_bar", "pub", "bar", "cocktail_bar", "wine_bar", "whisky_bar",
    "distillery_tasting_room",
}

HIGH_RISK_TERMS = {
    "cannabis", "marijuana", "weed", "drug", "narcotic", "cocaine",
    "gambling", "casino", "sports betting", "betting", "porn", "escort",
    "adult entertainment", "weapon", "firearm", "money laundering",
    "anonymous cash", "mixer", "dark web",
}

TOBACCO_TERMS = {"tobacco", "tabacaria", "tabaccheria", "tobacconist", "cigar"}
ALCOHOL_TERMS = {
    "liquor", "wine", "beer", "brewery", "brewpub", "pub", "bar",
    "cocktail", "whisky", "whiskey", "distillery", "spirits", "alcohol",
}

OWNER_MODELS = {"owner_operated", "independent_small_business"}
CONTACT_CHANNELS = {"whatsapp", "telegram"}
CONTACT_VERIFICATION = {"official_link", "account_verified"}
EVIDENCE_LABELS = {"observed", "self_reported", "inferred", "unknown"}
DIRECT_REPLY_STATUSES = {
    "not_sent", "sent_no_response", "read_no_response", "replied",
    "asked_details", "asked_price", "trial", "paid", "not_interested",
}

ACTIVITY_MAX_DAYS = 30
MAX_LOCATIONS = 2


@dataclass
class GateResult:
    status: str
    reason_codes: list[str] = field(default_factory=list)
    hard_failures: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)


def _text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).strip()


def normalize_channel(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")


def public_url(value: Any) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def domain(value: Any) -> str:
    if not public_url(value):
        return ""
    return (urlsplit(str(value).strip()).hostname or "").casefold().removeprefix("www.")


def _bool(value: Any) -> bool:
    return value is True or str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def age_days(value: Any, run_day: date) -> int | None:
    observed = _date(value)
    return None if observed is None else (run_day - observed).days


def classify_business(record: dict[str, Any]) -> str:
    """Return a conservative target type from an already verified record.

    ``official_business_type`` is intentionally preferred.  Names and raw map
    tags can help route a record to review, but cannot by themselves promote it.
    """
    explicit = str(record.get("official_business_type", "")).strip().casefold()
    aliases = {
        "tobacco shop": "tobacco_shop", "cigar shop": "cigar_shop",
        "liquor store": "liquor_store", "wine shop": "wine_shop",
        "beer shop": "beer_shop", "craft brewery": "craft_brewery",
        "beer bar": "beer_bar", "cocktail bar": "cocktail_bar",
        "wine bar": "wine_bar", "whisky bar": "whisky_bar",
        "distillery tasting room": "distillery_tasting_room",
    }
    if explicit in TARGET_BUSINESS_TYPES:
        return explicit
    if explicit in aliases:
        return aliases[explicit]
    if explicit:
        return explicit.replace(" ", "_")
    raw_tags = record.get("source_tags") or record.get("tags") or {}
    if isinstance(raw_tags, dict):
        raw = _text(raw_tags.get("shop"), raw_tags.get("amenity"), raw_tags.get("craft"), raw_tags.get("tourism"))
    else:
        raw = _text(raw_tags)
    haystack = _text(record.get("company_name"), record.get("category"), raw).casefold()
    if any(term in haystack for term in TOBACCO_TERMS):
        return "tobacco_shop"
    if "brewery" in haystack or "brewpub" in haystack:
        return "brewery"
    if "wine" in haystack and "bar" in haystack:
        return "wine_bar"
    if "whisky" in haystack or "whiskey" in haystack:
        return "whisky_bar"
    if "cocktail" in haystack:
        return "cocktail_bar"
    if "pub" in haystack:
        return "pub"
    if "bar" in haystack:
        return "bar"
    if any(term in haystack for term in ALCOHOL_TERMS):
        return "alcohol_business"
    return "unknown"


def evidence_for(record: dict[str, Any], category: str) -> list[dict[str, Any]]:
    values = record.get("research_evidence") or record.get("evidence") or []
    if not isinstance(values, list):
        return []
    return [
        item for item in values
        if isinstance(item, dict) and str(item.get("category", "")).strip() == category
    ]


def has_matching_evidence(record: dict[str, Any], category: str, source_url: str = "") -> bool:
    for item in evidence_for(record, category):
        label = str(item.get("label", "")).strip().casefold()
        url = str(item.get("source_url", "")).strip()
        if label not in {"observed", "self_reported"}:
            continue
        if source_url and url.rstrip("/").casefold() != source_url.rstrip("/").casefold():
            continue
        if public_url(url):
            return True
    return False


def _risk_terms(record: dict[str, Any]) -> list[str]:
    haystack = _text(
        record.get("company_name"), record.get("official_business_type"),
        record.get("category"), record.get("business_summary"),
        record.get("official_business_summary"),
    ).casefold()
    return sorted(term for term in HIGH_RISK_TERMS if term in haystack)


def _normalized(record: dict[str, Any], run_day: date) -> dict[str, Any]:
    result = dict(record)
    result["discovery_channel"] = normalize_channel(record.get("discovery_channel"))
    result["business_type"] = classify_business(record)
    result["location_count"] = record.get("location_count")
    result["recent_activity_age_days"] = age_days(record.get("recent_activity_at"), run_day)
    result["risk_terms"] = _risk_terms(record)
    result["payment_signal_type"] = str(
        record.get("payment_signal_type") or record.get("crypto_signal_type") or "unknown"
    ).strip().casefold()
    result["usdt_status"] = str(record.get("usdt_status", "unknown")).strip().casefold()
    result["reply_behavior_status"] = str(record.get("reply_behavior_status", "not_tested")).strip().casefold()
    result["contact_channel"] = str(record.get("contact_channel", "")).strip().casefold()
    result["contact_verification"] = str(record.get("contact_verification", "")).strip().casefold()
    result["payment_intent_status"] = str(record.get("payment_intent_status", "unknown")).strip().casefold()
    return result


def qualify_record(record: dict[str, Any], run_day: date) -> GateResult:
    """Apply the hard gate without fetching or contacting anything.

    Status meanings:

    * ``QUARANTINED``: a hard contradiction or prohibited discovery route;
    * ``REVIEW_REQUIRED``: promising, but one or more required facts are unknown;
    * ``READY_FOR_REPLY_TEST``: business, entity, size, activity, public contact,
      and observable reply behaviour are evidenced; a human may send one test
      message.  This still does not mean USDT acceptance or willingness to pay.
    """
    item = _normalized(record, run_day)
    hard: list[str] = []
    missing: list[str] = []

    channel = item["discovery_channel"]
    discovery_url = str(item.get("discovery_source_url", "")).strip()
    website_url = str(item.get("website_url", "")).strip()
    if channel in SEARCH_ONLY_CHANNELS or _bool(item.get("search_discovery")):
        hard.append("search_engine_discovery_forbidden")
    elif channel not in ALLOWED_DISCOVERY_CHANNELS:
        missing.append("off_search_discovery_channel")
    if not public_url(discovery_url):
        missing.append("public_discovery_source_url")
    if not public_url(website_url):
        missing.append("official_website_or_profile_url")
    if public_url(discovery_url) and public_url(website_url) and domain(discovery_url) == domain(website_url):
        hard.append("discovery_source_same_domain_as_official_site")
    if len(str(item.get("discovery_source_note", "")).strip()) < 12:
        missing.append("discovery_source_note")

    if item["risk_terms"]:
        hard.append("high_risk_or_illegal_adjacent_category")

    business_type = item["business_type"]
    if business_type not in TARGET_BUSINESS_TYPES:
        missing.append("verified_tobacco_or_alcohol_business_type")
    if not _bool(item.get("business_type_verified")):
        missing.append("business_type_official_verification")
    if not _bool(item.get("physical_location_verified")):
        missing.append("physical_location_verification")
    physical_source = str(item.get("physical_location_source_url") or item.get("ownership_location_evidence_url") or "").strip()
    if not public_url(physical_source):
        missing.append("physical_location_evidence_url")
    business_source = str(item.get("business_type_source_url", "")).strip()
    if not public_url(business_source):
        missing.append("business_type_source_url")
    if not has_matching_evidence(item, "business_type", business_source):
        missing.append("business_type_evidence")
    if not has_matching_evidence(
        item, "physical_location", physical_source
    ):
        missing.append("physical_location_evidence")

    ownership = str(item.get("ownership_model", "")).strip().casefold()
    chain_status = str(item.get("chain_status", "")).strip().casefold()
    locations = item.get("location_count")
    if ownership not in OWNER_MODELS:
        hard.append("independent_owner_status_not_confirmed") if ownership in {"chain", "franchise"} else missing.append("independent_owner_status")
    if chain_status in {"yes", "chain", "franchise"}:
        hard.append("chain_or_franchise")
    elif chain_status != "no":
        missing.append("chain_status_no")
    if not isinstance(locations, int) or isinstance(locations, bool):
        missing.append("observed_location_count")
    elif locations < 1 or locations > MAX_LOCATIONS:
        hard.append("more_than_two_locations_or_no_entity_location")
    if not public_url(str(item.get("ownership_location_evidence_url", "")).strip()):
        missing.append("ownership_location_evidence_url")
    if not has_matching_evidence(
        item, "ownership_locations", str(item.get("ownership_location_evidence_url", "")).strip()
    ):
        missing.append("ownership_location_evidence")

    activity_age = item["recent_activity_age_days"]
    if activity_age is None:
        missing.append("recent_activity_date")
    elif activity_age < 0 or activity_age > ACTIVITY_MAX_DAYS:
        missing.append("recent_activity_within_30_days")
    if not _bool(item.get("recent_activity_verified")):
        missing.append("recent_activity_verification")
    activity_source = str(item.get("recent_activity_source_url", "")).strip()
    if not public_url(activity_source):
        missing.append("recent_activity_source_url")
    if not has_matching_evidence(item, "recent_activity", activity_source):
        missing.append("recent_activity_evidence")

    contact_channel = item["contact_channel"]
    if contact_channel not in CONTACT_CHANNELS:
        missing.append("whatsapp_or_telegram_channel")
    if not public_url(item.get("contact_url")):
        missing.append("clickable_contact_url")
    if item["contact_verification"] not in CONTACT_VERIFICATION:
        missing.append("contact_account_verification")
    contact_source = str(item.get("contact_source_url", "")).strip()
    if not public_url(contact_source):
        missing.append("contact_source_url")
    if not has_matching_evidence(item, "contact_openness", contact_source):
        missing.append("contact_evidence")

    # Payment evidence is never silently upgraded.  XBT, Bitcoin and Lightning
    # are useful signals but are explicitly not USDT proof.
    if item["usdt_status"] not in {"verified", "crypto_signal", "unknown", "no"}:
        missing.append("valid_usdt_status")
    if item["usdt_status"] == "no":
        hard.append("usdt_explicitly_not_accepted")
    usdt_source = str(item.get("usdt_source_url", "")).strip()
    if item["usdt_status"] == "verified":
        if not public_url(usdt_source):
            missing.append("usdt_source_url")
        if not has_matching_evidence(item, "usdt", usdt_source):
            missing.append("usdt_evidence")
    if item["usdt_status"] == "unknown" and item["payment_signal_type"] == "unknown":
        missing.append("public_crypto_or_usdt_signal")
    if item["usdt_status"] in {"unknown", "crypto_signal"}:
        # This is deliberately a pending commercial question, not a hard gate
        # for the first human reply test.  The output must still expose it so a
        # crypto signal is never presented as confirmed USDT acceptance.
        item["payment_validation_required"] = True
    if item["payment_intent_status"] not in {"unknown", "observed_interest", "asked_price", "trial", "paid", "not_interested"}:
        missing.append("valid_payment_intent_status")

    direct_reply_status = str(item.get("direct_reply_status", "not_sent")).strip().casefold()
    if direct_reply_status not in DIRECT_REPLY_STATUSES:
        missing.append("valid_direct_reply_status")

    # Public reply behaviour is a required pre-contact signal for this track.
    # A WhatsApp button alone is not reply evidence.  Actual direct reply is
    # recorded later by the human outreach operator.
    reply_status = item["reply_behavior_status"]
    if reply_status not in {"observed", "not_tested", "inaccessible"}:
        missing.append("valid_reply_behavior_status")
    if reply_status == "observed" and not has_matching_evidence(item, "reply_behavior", ""):
        missing.append("reply_behavior_evidence")
    if reply_status != "observed":
        missing.append("observed_public_reply_behavior")

    if hard:
        status = "QUARANTINED"
    elif missing:
        status = "REVIEW_REQUIRED"
    else:
        status = "READY_FOR_REPLY_TEST"
    return GateResult(
        status=status,
        reason_codes=sorted(set(hard + missing)),
        hard_failures=sorted(set(hard)),
        missing_evidence=sorted(set(missing)),
        normalized=item,
    )


def screen_records(rows: Iterable[dict[str, Any]], run_day: date, requested: int | None = None) -> dict[str, Any]:
    """Screen only supplied records; never fills a requested quota."""
    counts = {"raw_records": 0, "ready_for_reply_test": 0, "review_required": 0, "quarantined": 0}
    qualified: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        counts["raw_records"] += 1
        key = str(row.get("company_key") or row.get("company_name") or row.get("discovery_source_url") or "").strip().casefold()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result = qualify_record(row, run_day)
        output = dict(result.normalized)
        output.update({
            "qualification_status": result.status,
            "qualification_reason_codes": result.reason_codes,
            "hard_failures": result.hard_failures,
            "missing_evidence": result.missing_evidence,
        "manual_outreach_allowed": result.status == "READY_FOR_REPLY_TEST",
        })
        if result.status == "READY_FOR_REPLY_TEST":
            qualified.append(output)
            counts["ready_for_reply_test"] += 1
        elif result.status == "REVIEW_REQUIRED":
            review.append(output)
            counts["review_required"] += 1
        else:
            quarantine.append(output)
            counts["quarantined"] += 1
    if requested is not None and requested < 0:
        raise ValueError("requested must be non-negative")
    limited = qualified if requested is None else qualified[:requested]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_day": run_day.isoformat(),
        "method": "structured off-search discovery -> identity/size gate -> official business/entity/activity/contact verification -> reply-behaviour gate",
        "requested": requested,
        "shortfall": max(0, requested - len(qualified)) if requested is not None else 0,
        "counts": counts,
        "qualified": limited,
        "review_required": review,
        "quarantined": quarantine,
        "no_quota_filling": True,
        "outreach_sent": False,
    }


def record_reply_test(
    record: dict[str, Any],
    status: str,
    observed_at: str = "",
    evidence_url: str = "",
) -> dict[str, Any]:
    """Record a human-run contact test without sending anything.

    This keeps public reply behaviour and direct reply behaviour separate.  A
    public comment reply may qualify a prospect for a reply test; it must not
    be rewritten as a reply to the operator's message.
    """
    normalized = dict(record)
    clean_status = str(status or "").strip().casefold()
    if clean_status not in DIRECT_REPLY_STATUSES or clean_status == "not_sent":
        raise ValueError(f"status must be one of {sorted(DIRECT_REPLY_STATUSES - {'not_sent'})}")
    normalized["direct_reply_status"] = clean_status
    normalized["direct_reply_observed_at"] = observed_at
    normalized["direct_reply_evidence_url"] = evidence_url
    if clean_status in {"asked_price", "trial", "paid"}:
        normalized["payment_intent_status"] = clean_status
    return normalized


def explain_status(result: GateResult) -> str:
    if result.status == "READY_FOR_REPLY_TEST":
        return "业务、实体、规模、近期活跃度、官方联系入口和公开回复行为均有证据；允许人工发送一条测试消息。USDT与付费意愿仍需单独验证。"
    if result.status == "QUARANTINED":
        return "存在硬性排除项，不能通过补一句推断或提高分数恢复。"
    return "候选可能有价值，但证据链不完整，必须留在验证池，不能进入外联名单。"
