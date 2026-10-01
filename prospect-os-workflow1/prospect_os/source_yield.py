"""Descriptive source-yield metrics; these never qualify or disqualify prospects."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit
from typing import Any

from .contact_pools import _usable_contact
from .sampling import classify_vertical


def _domain(value: Any) -> str:
    return (urlsplit(str(value or "")).hostname or "").casefold().removeprefix("www.")


def _group(row: dict[str, Any]) -> tuple[str, str, str, str]:
    dataset = str(row.get("source_dataset_url") or "")
    source = str(row.get("source_name") or row.get("source_type") or _domain(dataset) or
                 _domain(row.get("discovery_source_url") or row.get("profile_url")) or "unknown_source")
    country = str(row.get("country") or row.get("country_hint") or row.get("country_name") or
                  row.get("country_iso") or row.get("location_country") or "")
    if not country:
        location = str(row.get("city_country") or row.get("city_hint") or "").strip()
        if "," in location:
            country = location.rsplit(",", 1)[-1].strip()
        elif location.casefold() in {"portugal", "brazil", "brasil", "united states", "usa", "canada"}:
            country = location
    if not country:
        # OpenWineMap country snapshots encode their ISO country in the
        # immutable dataset URL; use that source metadata when city is absent.
        import re
        match = re.search(r"/countries/([A-Z]{2})\.geojson(?:$|[?#])", dataset)
        if match:
            country = match.group(1)
    return source, dataset, country, classify_vertical(row)


def build_source_yield(raw_rows: list[dict[str, Any]], excluded_rows: list[dict[str, Any]],
                       screened_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate original records and screening outcomes per source/country/vertical."""
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "raw_count": 0, "history_excluded": 0, "website_already_present": 0,
        "website_resolved": 0, "website_unresolved": 0, "website_fetch_success": 0,
        "website_fetch_failed": 0, "whatsapp_found": 0, "telegram_found": 0,
        "email_found": 0, "chat_found": 0, "review_count": 0,
        "prelock_pass_count": 0, "prelock_review_count": 0, "prelock_reject_count": 0,
    })
    for row in raw_rows:
        key = _group(row)
        groups[key]["raw_count"] += 1
        if row.get("website_url"):
            groups[key]["website_already_present"] += 1
    raw_by_identity = {}
    for row in raw_rows:
        for field in ("identity_key", "source_id"):
            if row.get(field):
                raw_by_identity[(field, str(row[field]))] = row
    for row in excluded_rows:
        source_row = next((raw_by_identity[(field, str(row[field]))]
                           for field in ("identity_key", "source_id")
                           if row.get(field) and (field, str(row[field])) in raw_by_identity), row)
        groups[_group(source_row)]["history_excluded"] += 1
    for row in screened_rows:
        key = _group(row)
        counts = groups[key]
        source_row = next((raw_by_identity[(field, str(row[field]))]
                           for field in ("identity_key", "source_id")
                           if row.get(field) and (field, str(row[field])) in raw_by_identity), row)
        had_website_in_raw = bool(source_row.get("website_url"))
        status = row.get("website_resolution_status")
        if status == "resolved" and not had_website_in_raw:
            counts["website_resolved"] += 1
        elif status == "unresolved" and not had_website_in_raw:
            counts["website_unresolved"] += 1
        if row.get("contact_enrichment_status") == "completed":
            counts["website_fetch_success"] += 1
        elif row.get("contact_enrichment_status") in {"fetch_failed", "prelock_fetch_failed"}:
            counts["website_fetch_failed"] += 1
        contacts = row.get("contacts") or []
        whatsapp = any(_usable_contact(c, "whatsapp", row.get("website_url")) for c in contacts)
        telegram = any(_usable_contact(c, "telegram", row.get("website_url")) for c in contacts)
        if whatsapp:
            counts["whatsapp_found"] += 1
        if telegram:
            counts["telegram_found"] += 1
        if whatsapp or telegram:
            counts["chat_found"] += 1
        if any(_usable_contact(c, "email", row.get("website_url")) for c in contacts):
            counts["email_found"] += 1
        if row.get("prelock_pool") == "review" or row.get("prelock_status") == "PRELOCK_REVIEW":
            counts["review_count"] += 1
        if row.get("prelock_status") == "PRELOCK_PASS":
            counts["prelock_pass_count"] += 1
        elif row.get("prelock_status") == "PRELOCK_REVIEW":
            counts["prelock_review_count"] += 1
        elif row.get("prelock_status") == "PRELOCK_REJECT":
            counts["prelock_reject_count"] += 1

    results = []
    for (source, dataset, country, vertical), counts in sorted(groups.items()):
        raw_count = counts["raw_count"]
        results.append({
            "source": source,
            "source_name": source,
            "source_dataset_url": dataset,
            "source_domain": _domain(dataset),
            "country": country,
            "sampling_vertical": vertical,
            **counts,
            "whatsapp_yield_rate": counts["whatsapp_found"] / raw_count if raw_count else 0.0,
            "chat_yield_rate": counts["chat_found"] / raw_count if raw_count else 0.0,
            "website_yield_rate": min(1.0, (counts["website_already_present"] + counts["website_resolved"]) / raw_count) if raw_count else 0.0,
            "prelock_pass_rate": counts["prelock_pass_count"] / raw_count if raw_count else 0.0,
        })
    return {"schema_version": 1, "groups": results,
            "note": "Descriptive source prioritization only; ICP qualification is unchanged."}
