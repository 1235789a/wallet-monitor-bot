"""Evidence-gated, low-cost ICP and buyer-intent check before sampling."""

from __future__ import annotations

from typing import Any

from .contact_pools import _usable_contact
from .sampling import classify_vertical, track_for_vertical
from .source_pool import public_http_url


def _draft_queries(row: dict[str, Any], track: str) -> list[dict[str, Any]]:
    """Draft two commercial-intent queries for later testing, never treat them as evidence."""
    city = str(row.get("city_hint") or row.get("city") or row.get("country") or "").strip()
    if track == "track_b":
        vertical = classify_vertical(row).replace("_", " ")
        place = f" in {city}" if city else ""
        candidates = [f"best {vertical}{place}", f"buy {vertical}{place}" ]
    else:
        service = str(row.get("service_category") or row.get("services") or
                      row.get("industry_hint") or row.get("category") or "B2B technology service")
        service = " ".join(service.split())[:80]
        candidates = [f"best {service} provider", f"hire {service} company pricing"]
    return [{"query": query, "tested": False, "status": "suggested_only",
             "buyer_intent": None, "competitor_evidence": None, "evidence_urls": []}
            for query in candidates]


def preflight_record(row: dict[str, Any]) -> dict[str, Any]:
    """Assess structured, already gathered evidence; this function does no search."""
    result = dict(row)
    ev = row.get("prelock_assessment") or {}
    if not isinstance(ev, dict):
        ev = {}
    vertical = classify_vertical(row)
    inferred_track = track_for_vertical(vertical)
    # An unrecognized source label is not evidence that a company is outside
    # the ICP. A human-backed preflight may supply a track after checking the
    # company's site and source evidence; otherwise it stays in REVIEW.
    assessed_track = str(ev.get("track") or "").casefold()
    track = assessed_track if assessed_track in {"track_a", "track_b"} else inferred_track
    missing: list[str] = []
    rejects: list[str] = []
    icp_reasons: list[str] = []
    intent_reasons: list[str] = []
    evidence_urls = list(ev.get("evidence_urls") or [])
    business_url = str(ev.get("business_evidence_url") or "")
    if public_http_url(business_url):
        evidence_urls.append(business_url)

    # The site must have loaded successfully and a direct, official chat route
    # must be present. Failed page access remains REVIEW rather than absence.
    if row.get("contact_enrichment_status") != "completed" or not row.get("pages_checked"):
        missing.append("website_live_evidence")
    if not public_http_url(str(row.get("website_url") or "")):
        missing.append("official_website")
    contacts = row.get("contacts") or []
    has_chat = (any(_usable_contact(c, "whatsapp", row.get("website_url")) for c in contacts)
                or any(_usable_contact(c, "telegram", row.get("website_url")) for c in contacts))
    if not has_chat:
        if (row.get("contact_enrichment_status") == "completed" and row.get("pages_checked")
                and row.get("prelock_access_limited") is not True):
            rejects.append("no_valid_direct_chat_route")
        else:
            missing.append("direct_chat_route_not_yet_verified")

    if ev.get("business_real") is False:
        rejects.append("business_not_real_or_inactive")
    elif ev.get("business_real") is not True:
        missing.append("real_business_evidence")
    if ev.get("active_business") is False:
        rejects.append("business_not_active")
    elif ev.get("active_business") is not True:
        missing.append("active_business_evidence")
    if ev.get("vertical_match") is False:
        rejects.append("outside_current_vertical")
    elif ev.get("vertical_match") is not True:
        missing.append("vertical_fit_evidence")

    if track == "track_b":
        chain = ev.get("chain")
        locations = ev.get("locations")
        ownership = str(ev.get("ownership_type") or "").casefold()
        if chain is True or (isinstance(locations, int) and locations > 2):
            rejects.append("chain_or_more_than_two_locations")
        elif chain is not False or not isinstance(locations, int):
            missing.append("independent_location_evidence")
        elif locations < 1:
            rejects.append("invalid_location_count")
        if ownership and ownership not in {"independent", "owner_operated", "founder_led"}:
            rejects.append("not_independently_operated")
        elif not ownership:
            missing.append("independent_ownership_evidence")
        for key in ("ownership_evidence_url", "location_evidence_url"):
            if not public_http_url(str(ev.get(key) or "")):
                missing.append(key)
            else:
                evidence_urls.append(ev[key])
        icp_reasons.append("Track B requires independent ownership and no more than two locations")
    elif track == "track_a":
        for key, reason in (("is_b2b", "not_b2b"), ("not_enterprise", "enterprise_scale"),
                            ("small_team_evidence", "small_team_not_supported"),
                            ("purchasable_service", "no_purchasable_service")):
            value = ev.get(key)
            if key in {"is_b2b", "not_enterprise", "purchasable_service"}:
                if value is False:
                    rejects.append(reason)
                elif value is not True:
                    missing.append(key)
            elif not value:
                missing.append(key)
        for key in ("b2b_evidence_url", "team_evidence_url", "service_evidence_url"):
            if not public_http_url(str(ev.get(key) or "")):
                missing.append(key)
            else:
                evidence_urls.append(ev[key])
        icp_reasons.append("Track A requires a real small B2B provider with a purchasable service")
    elif track == "secondary":
        if ev.get("vertical_match") is False:
            rejects.append("outside_track_a_or_track_b")
        else:
            missing.append("formal_track_assignment_evidence")

    queries = (ev.get("buyer_queries") or row.get("prelock_buyer_queries")
               or _draft_queries(row, track))
    if not isinstance(queries, list) or not 1 <= len(queries) <= 2:
        missing.append("one_or_two_tested_buyer_queries")
        queries = queries if isinstance(queries, list) else []
    else:
        valid_queries = [q for q in queries if isinstance(q, dict)]
        if len(valid_queries) != len(queries) or any(q.get("tested") is not True for q in valid_queries):
            missing.append("buyer_query_test_evidence")
        elif all(q.get("buyer_intent") is False for q in valid_queries):
            rejects.append("no_reasonable_purchase_scenario")
            intent_reasons.append("Tested high-intent queries did not show a purchase scenario")
        else:
            positive = [q for q in valid_queries if q.get("buyer_intent") is True]
            if not positive:
                missing.append("buyer_intent_evidence")
            backed = []
            for query in positive:
                urls = query.get("evidence_urls") or ([query.get("evidence_url")] if query.get("evidence_url") else [])
                has_url = any(public_http_url(str(url)) for url in urls)
                if query.get("competitor_evidence") and has_url:
                    backed.append(query)
                    evidence_urls.extend(urls)
                else:
                    if not query.get("competitor_evidence"):
                        missing.append("competitor_or_substitute_evidence")
                    if not has_url:
                        missing.append("buyer_query_evidence_url")
            if not backed and positive:
                missing.append("buyer_intent_competitor_evidence")
            intent_reasons.append("At least one tested query must show purchase intent and a named competitor or substitute")

    if not ev.get("business_evidence_url") and not any(public_http_url(str(u)) for u in evidence_urls):
        missing.append("preflight_evidence_urls")
    rejects = list(dict.fromkeys(rejects))
    missing = list(dict.fromkeys(missing))
    if rejects:
        status = "PRELOCK_REJECT"
        icp_status = "REJECT" if any(reason in rejects for reason in (
            "business_not_real_or_inactive", "business_not_active", "outside_current_vertical",
            "chain_or_more_than_two_locations", "invalid_location_count", "not_independently_operated",
            "not_b2b", "enterprise_scale", "no_purchasable_service", "outside_track_a_or_track_b")) else "REVIEW"
        buyer_status = "REJECT" if "no_reasonable_purchase_scenario" in rejects else ("REVIEW" if icp_status == "REVIEW" else "PASS")
    elif missing:
        status, icp_status, buyer_status = "PRELOCK_REVIEW", "REVIEW", "REVIEW"
    else:
        status, icp_status, buyer_status = "PRELOCK_PASS", "PASS", "PASS"
    result.update(
        prelock_status=status,
        prelock_icp_status=icp_status,
        prelock_icp_reason="; ".join(rejects + missing + icp_reasons) or "; ".join(icp_reasons),
        prelock_buyer_intent_status=buyer_status,
        prelock_buyer_queries=queries,
        prelock_competitor_evidence=[q.get("competitor_evidence") for q in queries if isinstance(q, dict) and q.get("competitor_evidence")],
        prelock_evidence_urls=list(dict.fromkeys(str(u) for u in evidence_urls if public_http_url(str(u)))),
        prelock_missing_evidence=missing,
        prelock_reject_reasons=rejects,
    )
    return result
