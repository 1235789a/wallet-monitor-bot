"""Configurable, evidence-backed buyer priority scoring before sample lock.

Hard ICP gates remain in prelock_preflight.py. A score never changes PRELOCK status.
Only explicitly supplied, source-backed rating assessments earn points.
"""
from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit


RATING_CONFIG: dict[str, Any] = {
    "version": "buyer-rating-v1",
    "weights": {
        "buyer_intent": 25,
        "geo_opportunity": 20,
        "decision_maker_reachability": 20,
        "business_quality": 15,
        "active_customer_acquisition": 10,
        "competitive_pressure": 5,
        "evidence_completeness": 5,
    },
    "grades": {"S": [85, 100], "A": [70, 84], "B": [55, 69], "C": [0, 54]},
    "evidence_labels": {"observed", "self_reported", "inferred"},
    "formal_exclude_grades": {"C"},
    "formal_channels": {"whatsapp": 24, "telegram": 6},
}


def _valid_evidence(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    url = str(item.get("url") or item.get("source_url") or "")
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and item.get("label") in RATING_CONFIG["evidence_labels"]
            and bool(item.get("checked_at")) and bool(item.get("claim")))


def rate_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Attach v1 score from rating_assessment; unsupported/unknown claims score 0."""
    result = dict(row)
    assessment = row.get("rating_assessment") or (row.get("prelock_assessment") or {}).get("rating_assessment") or {}
    if not isinstance(assessment, dict):
        assessment = {}
    breakdown: dict[str, int] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    reasons: list[str] = []
    for dimension, ceiling in RATING_CONFIG["weights"].items():
        item = assessment.get(dimension) or {}
        if not isinstance(item, dict):
            item = {}
        valid = [entry for entry in (item.get("evidence") or []) if _valid_evidence(entry)]
        raw_score = item.get("score", 0)
        try:
            requested = max(0, min(ceiling, int(raw_score)))
        except (TypeError, ValueError):
            requested = 0
        # A positive score without traceable evidence is discarded.
        score = requested if valid else 0
        breakdown[dimension] = score
        evidence[dimension] = valid
        if score:
            reason = str(item.get("reason") or "").strip()
            if reason:
                reasons.append(reason)
            else:
                reasons.append(f"{dimension}: {score}/{ceiling}, evidence attached")
        elif requested:
            reasons.append(f"{dimension}: requested score withheld because valid evidence is missing")
        else:
            reasons.append(f"{dimension}: no scored, traceable rating evidence supplied")
    score = sum(breakdown.values())
    grade = next((name for name, (lo, hi) in RATING_CONFIG["grades"].items()
                  if lo <= score <= hi), "C")
    result.update(
        buyer_priority_score=score,
        buyer_grade=grade,
        rating_breakdown=breakdown,
        rating_reasons=reasons,
        rating_evidence=evidence,
        rating_version=RATING_CONFIG["version"],
        rating_assessment_status=("complete" if all(evidence.values()) else "partial"),
    )
    return result


def rating_summary(rows: list[dict[str, Any]], *, needed_total: int = 30,
                   vertical_quotas: dict[str, int] | None = None) -> dict[str, Any]:
    """Summarize prelock states, grades, valid contact routes, and exact quota gaps."""
    grade_counts = Counter(row.get("buyer_grade", "C") for row in rows)
    statuses = Counter(row.get("prelock_status", "PRELOCK_REVIEW") for row in rows)
    channels = Counter()
    prelock_channels = Counter()
    qualified = Counter()
    available_by_vertical: dict[str, Counter[str]] = {}
    for row in rows:
        available = row.get("available_contact_channels")
        if not isinstance(available, list) or not available:
            selected = str(row.get("selected_contact_channel") or row.get("prelock_channel") or "").casefold()
            available = [selected] if selected in {"whatsapp", "telegram"} else []
        available = list(dict.fromkeys(str(ch).casefold() for ch in available
                                       if str(ch).casefold() in {"whatsapp", "telegram"}))
        for route in available:
            channels[route] += 1
            if row.get("prelock_status") == "PRELOCK_PASS":
                prelock_channels[route] += 1
            if row.get("prelock_status") == "PRELOCK_PASS":
                qualified[f"{route}_{row.get('buyer_grade', 'C').casefold()}"] += 1
        vertical = str(row.get("sampling_vertical") or row.get("vertical") or "unknown")
        available_by_vertical.setdefault(vertical, Counter()).update(available)
    if needed_total == 30:
        target_channels = dict(RATING_CONFIG["formal_channels"])
    else:
        tg = round(needed_total / 5)
        target_channels = {"whatsapp": needed_total - tg, "telegram": tg}
    qualified_pool = [r for r in rows if r.get("prelock_status") == "PRELOCK_PASS"
                      and r.get("buyer_grade") not in RATING_CONFIG["formal_exclude_grades"]]
    quotas = vertical_quotas or {}
    # Estimate already fillable formal slots after enforcing vertical caps.
    # This avoids counting surplus candidates from an overfilled vertical as
    # satisfying channel quotas for the final 30.
    grade_order = {"S": 0, "A": 1, "B": 2}
    formal_by_vertical: dict[str, list[dict[str, Any]]] = {}
    present_verticals: Counter[str] = Counter()
    for vertical, target in quotas.items():
        candidates = [r for r in qualified_pool
                      if str(r.get("sampling_vertical") or r.get("vertical") or "unknown") == vertical]
        candidates.sort(key=lambda r: (grade_order.get(r.get("buyer_grade"), 9),
                                       -int(r.get("buyer_priority_score") or 0),
                                       -int((r.get("rating_breakdown") or {}).get("decision_maker_reachability") or 0),
                                       -int((r.get("rating_breakdown") or {}).get("buyer_intent") or 0),
                                       str(r.get("identity_key") or r.get("source_id") or r.get("company_name") or "")))
        formal_by_vertical[vertical] = candidates[:target]
        present_verticals[vertical] = len(formal_by_vertical[vertical])
    formal_slots = [row for vertical in quotas for row in formal_by_vertical[vertical]]
    selected_channels = Counter()
    flexible = []
    for row in formal_slots:
        available = row.get("available_contact_channels") or [row.get("selected_contact_channel") or row.get("prelock_channel")]
        available = set(str(ch).casefold() for ch in available)
        if available == {"telegram"}:
            selected_channels["telegram"] += 1
        elif available == {"whatsapp"}:
            selected_channels["whatsapp"] += 1
        elif {"whatsapp", "telegram"}.issubset(available):
            flexible.append(row)
    telegram_slots = max(0, target_channels["telegram"] - selected_channels["telegram"])
    use_dual_for_tg = min(telegram_slots, len(flexible))
    selected_channels["telegram"] += use_dual_for_tg
    selected_channels["whatsapp"] += len(flexible) - use_dual_for_tg
    channel_remaining = {
        "whatsapp": max(0, target_channels["whatsapp"] - selected_channels["whatsapp"]),
        "telegram": max(0, target_channels["telegram"] - selected_channels["telegram"]),
    }
    required_slots = {}
    vertical_missing = {vertical: max(0, target - present_verticals[vertical])
                        for vertical, target in quotas.items()}
    # Allocate the remaining exact Telegram slots proportionally to each
    # vertical's formal quota using largest remainders. This is a discovery
    # plan, not an eligibility decision; availability is reported separately.
    allocated_tg = {vertical: 0 for vertical in quotas}
    if quotas and channel_remaining["telegram"]:
        total_weight = sum(quotas.values()) or 1
        shares = {vertical: channel_remaining["telegram"] * target / total_weight
                  for vertical, target in quotas.items()}
        for vertical in quotas:
            allocated_tg[vertical] = min(vertical_missing[vertical], int(shares[vertical]))
        left = channel_remaining["telegram"] - sum(allocated_tg.values())
        order = sorted(quotas, key=lambda v: (-(shares[v] - int(shares[v])),
                                              list(quotas).index(v)))
        while left:
            progressed = False
            for vertical in order:
                if allocated_tg[vertical] < vertical_missing[vertical]:
                    allocated_tg[vertical] += 1
                    left -= 1
                    progressed = True
                    if not left:
                        break
            if not progressed:
                break
    wa_remaining = channel_remaining["whatsapp"]
    for vertical, target in quotas.items():
        rows_v = formal_by_vertical[vertical]
        wa = sum("whatsapp" in (r.get("available_contact_channels") or [r.get("prelock_channel")]) for r in rows_v)
        tg = sum("telegram" in (r.get("available_contact_channels") or [r.get("prelock_channel")]) for r in rows_v)
        missing = vertical_missing[vertical]
        tg_slots = allocated_tg[vertical]
        wa_slots = min(max(0, missing - tg_slots), wa_remaining)
        wa_remaining -= wa_slots
        required_slots[vertical] = {
            "total": missing,
            "whatsapp": wa_slots,
            "telegram": tg_slots,
            "available_whatsapp_candidates": wa,
            "available_telegram_candidates": tg,
        }
    return {
        "rating_version": RATING_CONFIG["version"],
        "total_reviewed": len(rows),
        "prelock_pass": statuses["PRELOCK_PASS"],
        "prelock_review": statuses["PRELOCK_REVIEW"],
        "prelock_reject": statuses["PRELOCK_REJECT"],
        "grades": {g: grade_counts[g] for g in ("S", "A", "B", "C")},
        "channels": {"whatsapp": channels["whatsapp"], "telegram": channels["telegram"]},
        "prelock_pass_channels": {"whatsapp": prelock_channels["whatsapp"],
                                  "telegram": prelock_channels["telegram"]},
        "qualified_channels": {f"{channel}_{grade.lower()}": qualified[f"{channel}_{grade.lower()}"]
                               for channel in ("whatsapp", "telegram") for grade in ("S", "A", "B")},
        "needed_total": needed_total,
        "needed_whatsapp": target_channels["whatsapp"],
        "needed_telegram": target_channels["telegram"],
        "whatsapp_shortfall": channel_remaining["whatsapp"],
        "telegram_shortfall": channel_remaining["telegram"],
        "vertical_shortfall": {v: max(0, n - present_verticals[v]) for v, n in quotas.items()},
        "prelock_pass_by_vertical": dict(Counter(
            str(r.get("sampling_vertical") or r.get("vertical") or "unknown")
            for r in rows if r.get("prelock_status") == "PRELOCK_PASS")),
        "currently_fillable_formal_slots": {
            "total": len(formal_slots),
            "whatsapp": selected_channels["whatsapp"],
            "telegram": selected_channels["telegram"],
        },
        "currently_fillable_formal_tracks": dict(Counter(
            str(r.get("sampling_track") or r.get("track") or "unknown") for r in formal_slots)),
        "track_shortfall": {
            "track_a": max(0, 15 - sum(1 for r in formal_slots if
                (r.get("sampling_track") or r.get("track") or
                 ("track_a" if str(r.get("sampling_vertical") or r.get("vertical")) in
                  {"web3_blockchain", "ai_software_b2b_agency"} else "track_b")) == "track_a")),
            "track_b": max(0, 15 - sum(1 for r in formal_slots if
                (r.get("sampling_track") or r.get("track") or
                 ("track_a" if str(r.get("sampling_vertical") or r.get("vertical")) in
                  {"web3_blockchain", "ai_software_b2b_agency"} else "track_b")) == "track_b")),
        },
        "prelock_pass_by_track": dict(Counter(
            str(r.get("sampling_track") or r.get("track") or "unknown")
            for r in rows if r.get("prelock_status") == "PRELOCK_PASS")),
        "eligible_pass_by_track": dict(Counter(
            str(r.get("sampling_track") or r.get("track") or "unknown") for r in formal_slots)),
        "required_slots": required_slots,
    }
