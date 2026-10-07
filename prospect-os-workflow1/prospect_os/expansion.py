"""Persistent expansion control loop for prelock prospect pools.

Discovery and qualification policies stay in their existing modules. This module only
coordinates batches, review retries, quota gaps, source yield, and terminal states.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .sampling import (
    FORMAL_30_QUOTAS, TRACK_A_VERTICALS, TRACK_B_VERTICALS,
    classify_vertical, sampling_record_key, track_for_vertical,
)
from .source_scheduler import country_key, identity_aliases, segment_key, source_key
from .contact_pools import _usable_contact
from .contact_reachability import route_summary

RESERVE_POOL_TARGET = 42
DEFAULT_BATCH_SIZE = 75
MAX_REVIEW_ATTEMPTS = 3
CHANNEL_TARGETS = {"whatsapp": 24, "telegram": 6}
REVIEW_REASON_ORDER = (
    "location_count_missing", "ownership_missing", "contact_route_uncertain",
    "telegram_route_uncertain", "human_reachability_missing", "team_missing", "decision_maker_missing", "buyer_intent_missing",
    "visibility_gap_missing", "website_unresolved", "website_fetch_failed",
    "other_evidence_missing",
)
REVIEW_ACTIONS = {
    "location_count_missing": "check official locations/store locator and independent directory",
    "ownership_missing": "check official about page and independent ownership evidence",
    "contact_route_uncertain": "verify the official-site direct chat URL and route type",
    "telegram_route_uncertain": "verify that the Telegram profile is a direct user account, not a bot/group/channel",
    "human_reachability_missing": "inspect the official route label or reviewed reply export for human access",
    "team_missing": "inspect an official team page for an explicit small-team size",
    "decision_maker_missing": "check official team page and public founder/owner evidence",
    "buyer_intent_missing": "test one or two representative non-brand buyer queries",
    "visibility_gap_missing": "compare the representative buyer query with direct competitors",
    "website_unresolved": "resolve the official website from the existing discovery record only",
    "website_fetch_failed": "retry the cached official URL once, then retain as unresolved if unavailable",
    "other_evidence_missing": "inspect the precise missing evidence named in the review note",
}
VALID_REVIEW_REASONS = frozenset(REVIEW_ACTIONS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _channel(row: dict[str, Any]) -> str:
    chosen = str(row.get("selected_contact_channel") or "").casefold()
    if chosen in CHANNEL_TARGETS:
        return chosen
    # A dual-route company defaults to WhatsApp. Telegram is counted only when
    # the row explicitly selects it for quota balancing.
    return "whatsapp" if row.get("whatsapp_route") or row.get("whatsapp_url") else str(
        row.get("prelock_channel") or row.get("contact_channel") or "unknown"
    ).casefold()


def compute_required_slots(
    pass_records: list[dict[str, Any]], *, reserve_pool_target: int = RESERVE_POOL_TARGET,
) -> dict[str, Any]:
    """Recompute final-cohort gaps from PRELOCK_PASS records only."""
    passed = []
    seen = set()
    for row in pass_records:
        if (row.get("prelock_status") not in {"PRELOCK_PASS", "PASS"}
                or row.get("buyer_grade") == "C" or row.get("do_not_contact") is True
                or row.get("chain") is True or identity_aliases(row) & seen):
            continue
        seen.update(identity_aliases(row))
        passed.append(row)
    vertical_counts: Counter[str] = Counter(classify_vertical(r) for r in passed)
    capped = {v: min(target, vertical_counts[v]) for v, target in FORMAL_30_QUOTAS.items()}
    track_counts = Counter()
    for vertical, count in capped.items():
        track_counts[track_for_vertical(vertical)] += count
    # Joint vertical/channel capacity: an overfilled vertical and a dual-route
    # company must never satisfy two separate formal slots.
    capacities = {}
    plans = {(0, 0): {}}
    for vertical, target in FORMAL_30_QUOTAS.items():
        counts = Counter()
        for row in passed:
            if classify_vertical(row) != vertical:
                continue
            available = row.get("reachable_contact_channels", row.get("available_contact_channels"))
            if available is None:
                available = [_channel(row)]
            channels = frozenset(ch for ch in available if ch in CHANNEL_TARGETS)
            counts[channels] += 1
        wa, tg, dual = counts[frozenset({"whatsapp"})], counts[frozenset({"telegram"})], counts[frozenset(CHANNEL_TARGETS)]
        options = [(w, t) for w in range(target + 1) for t in range(min(target - w, 6) + 1)
                   if max(0, w - wa) + max(0, t - tg) <= dual]
        next_plans = {}
        for (w0, t0), plan in plans.items():
            for w, t in options:
                if w0 + w <= 24 and t0 + t <= 6:
                    next_plans.setdefault((w0 + w, t0 + t), {**plan, vertical: {"whatsapp": w, "telegram": t}})
        plans = next_plans
        capacities[vertical] = {"whatsapp": min(target, wa + dual), "telegram": min(target, tg + dual)}
    channel_counts = max(plans, key=lambda pair: (sum(pair), pair[1]))
    channels_filled = dict(zip(CHANNEL_TARGETS, channel_counts))
    return {
        "reserve_pool_target": reserve_pool_target,
        "reserve_pool_pass": len(passed),
        "reserve_pool_shortfall": max(0, reserve_pool_target - len(passed)),
        "track_a_shortfall": max(0, 15 - track_counts["track_a"]),
        "track_b_shortfall": max(0, 15 - track_counts["track_b"]),
        "vertical_shortfall": {
            vertical: max(0, int(target) - vertical_counts[vertical])
            for vertical, target in FORMAL_30_QUOTAS.items()
        },
        "channel_shortfall": {
            channel: max(0, target - channels_filled[channel])
            for channel, target in CHANNEL_TARGETS.items()
        },
        "formal_channel_capacity": channels_filled,
        "by_vertical_channel": capacities,
        "formal_channel_plan": plans[channel_counts],
        "pass_by_country": dict(Counter(country_key(row) for row in passed)),
    }


def make_review_item(
    row: dict[str, Any], reason: str, *, attempts: int = 0, priority: int | None = None,
) -> dict[str, Any]:
    if reason not in VALID_REVIEW_REASONS:
        reason = "other_evidence_missing"
    return {
        **row,
        "prelock_status": "PRELOCK_REVIEW",
        "review_reason": reason,
        "review_attempts": max(0, attempts),
        "next_review_action": REVIEW_ACTIONS[reason],
        "review_priority": REVIEW_REASON_ORDER.index(reason) if priority is None else priority,
    }


def record_review_attempt(
    row: dict[str, Any], result: dict[str, Any] | None, *, max_attempts: int = MAX_REVIEW_ATTEMPTS,
) -> dict[str, Any]:
    """Advance one review attempt; park unresolved rows instead of blocking expansion."""
    attempts = int(row.get("review_attempts", 0)) + 1
    result = {**row, **(result or {})}
    if sampling_record_key(result) != sampling_record_key(row) or result.get("company_name") != row.get("company_name"):
        raise ValueError("review repair changed company identity")
    status = str(result.get("prelock_status") or result.get("prelock_icp_status") or "PRELOCK_REVIEW")
    if status in {"PRELOCK_PASS", "PASS"}:
        return {**result, "prelock_status": "PRELOCK_PASS", "review_attempts": attempts,
                "next_review_action": None}
    if status in {"PRELOCK_REJECT", "REJECT"}:
        return {**result, "prelock_status": "PRELOCK_REJECT", "review_attempts": attempts,
                "next_review_action": None}
    reason = review_reason(result)
    item = make_review_item(result, reason, attempts=attempts,
                            priority=row.get("review_priority"))
    if attempts >= max_attempts or result.get("review_evidence_changed") is False:
        item["prelock_status"] = "PRELOCK_PARKED"
        item["next_review_action"] = None
    return item


def review_reason(row):
    missing = " ".join(map(str, row.get("prelock_missing_evidence") or [])).casefold()
    for token, reason in (("location", "location_count_missing"), ("ownership", "ownership_missing"),
                          ("human_contact", "human_reachability_missing"), ("telegram", "telegram_route_uncertain"),
                          ("direct_chat", "contact_route_uncertain"), ("team", "team_missing"),
                          ("decision", "decision_maker_missing"), ("visibility", "visibility_gap_missing"),
                          ("buyer", "buyer_intent_missing"), ("competitor", "buyer_intent_missing"),
                          ("official_website", "website_unresolved"), ("website_live", "website_fetch_failed")):
        if token in missing:
            return reason
    return str(row.get("review_reason") or "other_evidence_missing")


def source_stop_reason(
    stats: dict[str, Any], *, min_screened: int = 30,
) -> str | None:
    """Return an auditable stop reason for a persistently low-yield source."""
    screened = int(stats.get("fresh_raw", stats.get("raw_count", 0)))
    if screened < min_screened:
        return None
    if int(stats.get("whatsapp_found", 0)) + int(stats.get("telegram_found", 0)) == 0:
        return "no_valid_chat_route_in_minimum_screen_window"
    if screened >= 50 and float(stats.get("website_resolution_rate", 1.0)) < 0.15:
        return "website_resolution_rate_below_15_percent_after_50_raw"
    if screened >= 50 and int(stats.get("prelock_pass", 0)) == 0:
        return "zero_prelock_pass_after_50_raw"
    if int(stats.get("stale_or_closed", 0)) >= max(10, screened // 2):
        return "stale_or_closed_records_exceed_half_of_screened_rows"
    if int(stats.get("chain_or_non_icp", 0)) >= max(10, screened // 2):
        return "chain_or_non_icp_records_exceed_half_of_screened_rows"
    return None


def rank_sources(source_yield: dict[str, dict[str, Any]], stopped: set[str] | None = None) -> list[str]:
    """Prioritize pass yield, then chat and website yield; omit stopped sources."""
    stopped = stopped or set()
    candidates = []
    for name, row in source_yield.items():
        if name in stopped or row.get("source_stop_reason"):
            continue
        screened = max(1, int(row.get("fresh_raw", row.get("raw_count", 0))))
        score = (
            4 * int(row.get("prelock_pass", 0)) / screened
            + 2 * (int(row.get("whatsapp_found", 0)) + int(row.get("telegram_found", 0))) / screened
            + float(row.get("website_resolution_rate", 0.0))
        )
        candidates.append((score, name))
    return [name for _, name in sorted(candidates, key=lambda pair: (-pair[0], pair[1]))]


def source_exhausted_criteria(state: dict[str, Any]) -> bool:
    """The only low-yield terminal gate: >=1k RAW, >=8 sources, three weak 100-row batches."""
    batches = state.get("batch_history", [])[-3:]
    return (
        int(state.get("fresh_raw_scanned", 0)) >= 1000
        and len(set(state.get("sources_attempted", []))) >= 8
        and len(batches) == 3
        and all(int(b.get("fresh_raw", 0)) >= 100 and int(b.get("prelock_pass", 0)) <= 1 for b in batches)
    )


def write_json_atomic(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_expansion_state(path: Path, *, reserve_pool_target: int = RESERVE_POOL_TARGET) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        state.setdefault("status", "RUNNING")
        state.setdefault("sources_attempted", [])
        state.setdefault("source_yield", {})
        state.setdefault("batch_history", [])
        state.setdefault("processed_record_keys", [])
        state.setdefault("pass_records", [])
        state.setdefault("review_queue", [])
        state.setdefault("parked_records", [])
        state.setdefault("rejected_records", [])
        state.setdefault("rejected_count", 0)
        state.setdefault("fresh_raw_scanned", 0)
        state.setdefault("consecutive_low_yield_batches", 0)
    else:
        state = {
            "status": "RUNNING", "created_at": utc_now(), "updated_at": utc_now(),
            "fresh_raw_scanned": 0, "sources_attempted": [], "source_yield": {},
            "reserve_pool_target": reserve_pool_target, "reserve_pool_pass": 0,
            "review_queue": [], "parked_records": [], "pass_records": [],
            "rejected_records": [], "rejected_count": 0,
            "processed_record_keys": [],
            "consecutive_low_yield_batches": 0, "batch_history": [],
        }
    state["reserve_pool_target"] = reserve_pool_target
    state["required_slots"] = compute_required_slots(
        state["pass_records"], reserve_pool_target=reserve_pool_target)
    return state


def _merge_rows(current: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {sampling_record_key(r): dict(r) for r in current}
    for row in incoming:
        key = sampling_record_key(row)
        if key in by_id and by_id[key].get("company_name") != row.get("company_name"):
            raise ValueError("expansion output changed company identity")
        by_id[key] = dict(row)
    return list(by_id.values())


def inventory(state):
    return {"pass": len(state["pass_records"]), "review": len(state["review_queue"]),
            "parked": len(state["parked_records"]), "reject": len(state["rejected_records"])}


def rebuild_source_yield(state):
    """Current distinct-company outcomes, with screened companies as denominator."""
    metrics = {}
    rows = sum((state.get(key, []) for key in (
        "pass_records", "review_queue", "parked_records", "rejected_records")), [])
    for row in _merge_rows([], rows):
        name = source_key(row)
        source = metrics.setdefault(name, {"source_name": name, "denominator": "distinct_screened_companies",
                                          "by_country": {}, "by_vertical": {}, "by_segment": {}})
        buckets = [source, source["by_country"].setdefault(country_key(row), {}),
                   source["by_vertical"].setdefault(classify_vertical(row), {}),
                   source["by_segment"].setdefault(segment_key(row), {})]
        routes = {channel: any(_usable_contact(c, channel, row.get("website_url"))
                               for c in row.get("contacts", [])) for channel in CHANNEL_TARGETS}
        # Compatibility for old outcome records without a contacts inventory.
        if "contacts" not in row:
            routes = {ch: row.get("prelock_channel") == ch for ch in CHANNEL_TARGETS}
        humans = set(route_summary(row, _usable_contact)["reachable_contact_channels"])
        status = str(row.get("prelock_status", "PRELOCK_REVIEW")).removeprefix("PRELOCK_").casefold()
        for bucket in buckets:
            additions = {"fresh_raw": 1, "screened_count": 1,
                         "website_resolved": int(bool(row.get("website_url"))),
                         "website_fetch_success": int(row.get("contact_enrichment_status") == "completed"),
                         "website_fetch_failed": int(row.get("contact_enrichment_status") == "fetch_failed"),
                         "whatsapp_found": int(routes["whatsapp"]), "telegram_found": int(routes["telegram"]),
                         "human_whatsapp_found": int("whatsapp" in humans),
                         "human_telegram_found": int("telegram" in humans),
                         "prelock_pass": int(status == "pass"), "prelock_review": int(status == "review"),
                         "prelock_parked": int(status == "parked"), "prelock_reject": int(status == "reject")}
            for key, count in additions.items():
                bucket[key] = bucket.get(key, 0) + count
    for name, source in metrics.items():
        for bucket in [source, *source["by_country"].values(), *source["by_vertical"].values(),
                       *source["by_segment"].values()]:
            n = bucket["screened_count"]
            bucket.update(raw_count=n, pass_rate=round(bucket["prelock_pass"] / n, 4),
                          whatsapp_yield=round(bucket["whatsapp_found"] / n, 4),
                          telegram_yield=round(bucket["telegram_found"] / n, 4),
                          website_resolution_rate=round(bucket["website_resolved"] / n, 4))
            reason = source_stop_reason(bucket)
            if reason:
                bucket["source_stop_reason"] = reason
        previous = state.get("source_yield", {}).get(name, {})
        if previous.get("source_stop_reason") in {"source_returned_empty_batch", "duplicate_only_batch"}:
            source["source_stop_reason"] = previous["source_stop_reason"]
    # Retain explicit discovery stop decisions even if a source has no outcomes.
    for name, old in state.get("source_yield", {}).items():
        if name not in metrics and old.get("source_stop_reason"):
            metrics[name] = {"source_name": name, "source_stop_reason": old["source_stop_reason"]}
    state["source_yield"] = metrics
    return metrics


def run_expansion_loop(
    *, state_path: Path, required_slots_path: Path, source_yield_path: Path,
    discover_batch: Callable[..., dict[str, Any]],
    screen_and_preflight: Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]],
    repair_review: Callable[[dict[str, Any], str], dict[str, Any]],
    sample_ready: Callable[[list[dict[str, Any]]], bool],
    reserve_pool_target: int = RESERVE_POOL_TARGET, batch_size: int = DEFAULT_BATCH_SIZE,
    max_review_attempts: int = MAX_REVIEW_ATTEMPTS, max_cycles: int | None = None,
    max_fresh_raw: int | None = None, max_review_records: int | None = None,
    reviews_per_cycle: int = 10,
) -> dict[str, Any]:
    """Resume bounded batches; preserve every outcome and count repairs separately."""
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    if reviews_per_cycle < 1 or any(value is not None and value < 0 for value in (
            max_cycles, max_fresh_raw, max_review_records)):
        raise ValueError("execution budgets must be nonnegative; reviews_per_cycle must be positive")
    state_path, required_slots_path, source_yield_path = map(Path, (state_path, required_slots_path, source_yield_path))
    state = load_expansion_state(state_path, reserve_pool_target=reserve_pool_target)
    initial = inventory(state)
    usage = {"fresh_raw_processed": 0, "raw_to_pass": 0, "raw_to_review": 0, "raw_to_reject": 0,
             "review_attempts": 0, "review_to_pass": 0, "review_to_parked": 0, "review_to_reject": 0,
             "contact_cache_hits": 0, "website_page_attempts": 0}
    state["this_run"] = usage

    def checkpoint():
        state["required_slots"] = compute_required_slots(state["pass_records"], reserve_pool_target=reserve_pool_target)
        state["reserve_pool_pass"] = len(state["pass_records"])
        state["current_totals"] = inventory(state)
        state["rejected_count"] = len(state["rejected_records"])
        state["review_queue_count"], state["parked"] = len(state["review_queue"]), len(state["parked_records"])
        state["updated_at"] = utc_now()
        rebuild_source_yield(state)
        write_json_atomic(required_slots_path, state["required_slots"])
        write_json_atomic(source_yield_path, state["source_yield"])
        write_json_atomic(state_path, state)

    def ready():
        return len(state["pass_records"]) >= reserve_pool_target and sample_ready(state["pass_records"])

    if state.get("status") in {"SAMPLE_READY", "SOURCE_EXHAUSTED"}:
        checkpoint()
        return state
    state["status"] = "RUNNING"
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        checkpoint()
        if ready():
            state["status"] = "SAMPLE_READY"
            break
        budget = reviews_per_cycle
        if max_review_records is not None:
            budget = min(budget, max_review_records - usage["review_attempts"])
        queue = sorted(state["review_queue"], key=lambda row: (
            int(row.get("review_attempts", 0)), int(row.get("review_priority", 99)), sampling_record_key(row)))
        attempted = queue[:max(0, budget)]
        # Keep each item in the persisted queue until its own outcome is saved.
        for item in attempted:
            try:
                repaired = repair_review(item, str(item.get("next_review_action") or "inspect missing evidence"))
                updated = record_review_attempt(item, repaired, max_attempts=max_review_attempts)
            except Exception as exc:
                updated = record_review_attempt(item, {**item, "review_error": str(exc)}, max_attempts=max_review_attempts)
            usage["review_attempts"] += 1
            key = sampling_record_key(item)
            state["review_queue"] = [row for row in state["review_queue"] if sampling_record_key(row) != key]
            status = updated["prelock_status"]
            target = {"PRELOCK_PASS": "pass_records", "PRELOCK_REVIEW": "review_queue",
                      "PRELOCK_PARKED": "parked_records", "PRELOCK_REJECT": "rejected_records"}[status]
            state[target] = _merge_rows(state[target], [updated])
            if status != "PRELOCK_REVIEW":
                usage[{"PRELOCK_PASS": "review_to_pass", "PRELOCK_PARKED": "review_to_parked",
                       "PRELOCK_REJECT": "review_to_reject"}[status]] += 1
            checkpoint()
        if ready():
            state["status"] = "SAMPLE_READY"
            break
        remaining_budget = batch_size if max_fresh_raw is None else min(batch_size, max_fresh_raw - usage["fresh_raw_processed"])
        if remaining_budget <= 0:
            state.update(status="PROGRESS", pause_reason="fresh_raw_budget_reached")
            break
        stopped = {name for name, metrics in state["source_yield"].items() if metrics.get("source_stop_reason")}
        try:
            batch = discover_batch(required_slots=state["required_slots"],
                preferred_sources=rank_sources(state["source_yield"], stopped),
                stopped_sources=sorted(stopped), batch_size=remaining_budget)
        except Exception as exc:
            state.update(status="EXECUTION_BLOCKED", blocked_reason=str(exc))
            break
        source = str(batch.get("source_name") or "unknown_source")
        rows = batch.get("records") or []
        if not rows:
            state["last_batch_result"] = {"source_name": source, "fresh_raw": 0,
                                           "note": "no new eligible RAW in supplied pool"}
            if batch.get("all_sources_exhausted"):
                # Give remaining targeted reviews their bounded budget even
                # when RAW is empty; lack of RAW must not discard that queue.
                if attempted and state["review_queue"] and (max_review_records is None or usage["review_attempts"] < max_review_records):
                    continue
                state["status"] = "SOURCE_EXHAUSTED" if source_exhausted_criteria(state) else "PROGRESS"
                state["pause_reason"] = "supplied_raw_pool_exhausted"
                break
            state["source_yield"].setdefault(source, {"source_name": source})["source_stop_reason"] = "source_returned_empty_batch"
            continue
        prior_rows = sum((state[key] for key in ("pass_records", "review_queue", "parked_records", "rejected_records")), [])
        aliases = set().union(*(identity_aliases(row) for row in prior_rows)) if prior_rows else set()
        processed = set(state["processed_record_keys"])
        fresh = []
        for row in rows:
            if sampling_record_key(row) in processed or identity_aliases(row) & aliases:
                continue
            fresh.append({**row, "expansion_source_key": source_key(row) if source == "mixed_raw" else source})
            aliases.update(identity_aliases(row))
        if len(fresh) > remaining_budget:
            state.update(status="EXECUTION_BLOCKED", blocked_reason="discovery exceeded requested batch budget")
            break
        if not fresh:
            state["source_yield"].setdefault(source, {"source_name": source})["source_stop_reason"] = "duplicate_only_batch"
            continue
        try:
            screened = screen_and_preflight(fresh, state["required_slots"])
            expected = {sampling_record_key(row): row for row in fresh}
            if (not isinstance(screened, list) or len(screened) != len(fresh)
                    or {sampling_record_key(row) for row in screened} != set(expected)
                    or any(row.get("company_name") != expected[sampling_record_key(row)].get("company_name") for row in screened)):
                raise ValueError("screen/preflight must return exactly one unchanged identity per RAW company")
        except Exception as exc:
            state.update(status="EXECUTION_BLOCKED", blocked_reason=str(exc))
            break
        counts = Counter()
        for original in screened:
            row = {**original, "expansion_source_key": expected[sampling_record_key(original)]["expansion_source_key"]}
            status = str(row.get("prelock_status") or "PRELOCK_REVIEW")
            if status in {"PASS", "PRELOCK_PASS"}:
                row["prelock_status"] = "PRELOCK_PASS"
                state["pass_records"] = _merge_rows(state["pass_records"], [row])
                counts["prelock_pass"] += 1
            elif status in {"REJECT", "PRELOCK_REJECT"}:
                row["prelock_status"] = "PRELOCK_REJECT"
                state["rejected_records"] = _merge_rows(state["rejected_records"], [row])
                counts["prelock_reject"] += 1
            else:
                item = make_review_item(row, review_reason(row), attempts=int(row.get("review_attempts", 0)))
                state["review_queue"] = _merge_rows(state["review_queue"], [item])
                counts["prelock_review"] += 1
            name = row["expansion_source_key"]
            if name not in state["sources_attempted"]:
                state["sources_attempted"].append(name)
            usage["contact_cache_hits"] += int(row.get("contact_cache_hit", False))
            usage["website_page_attempts"] += int(row.get("contact_page_attempts", 0))
        state["processed_record_keys"] = sorted(processed | set(expected))
        state["fresh_raw_scanned"] += len(fresh)
        usage["fresh_raw_processed"] += len(fresh)
        for key, counter in (("raw_to_pass", "prelock_pass"), ("raw_to_review", "prelock_review"), ("raw_to_reject", "prelock_reject")):
            usage[key] += counts[counter]
        record = {"source_name": source, "source_names": sorted({row["expansion_source_key"] for row in fresh}),
                  "fresh_raw": len(fresh), **{key: counts[key] for key in ("prelock_pass", "prelock_review", "prelock_reject")},
                  "completed_at": utc_now()}
        state["batch_history"].append(record)
        state["last_batch_result"] = record
        checkpoint()
        if ready():
            state["status"] = "SAMPLE_READY"
            break
        if batch.get("all_sources_exhausted") and source_exhausted_criteria(state):
            state["status"] = "SOURCE_EXHAUSTED"
            break
    if state["status"] == "RUNNING":
        state.update(status="PROGRESS", pause_reason="cycle_budget_reached")
    state["terminal_status"] = state["status"] if state["status"] in {"SAMPLE_READY", "SOURCE_EXHAUSTED", "EXECUTION_BLOCKED"} else None
    state["this_run_inventory_change"] = {key: inventory(state)[key] - initial[key] for key in initial}
    checkpoint()
    return state
