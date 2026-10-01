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

RESERVE_POOL_TARGET = 42
DEFAULT_BATCH_SIZE = 75
MAX_REVIEW_ATTEMPTS = 3
CHANNEL_TARGETS = {"whatsapp": 24, "telegram": 6}
REVIEW_REASON_ORDER = (
    "location_count_missing", "ownership_missing", "contact_route_uncertain",
    "telegram_route_uncertain", "decision_maker_missing", "buyer_intent_missing",
    "visibility_gap_missing", "website_unresolved", "website_fetch_failed",
    "other_evidence_missing",
)
REVIEW_ACTIONS = {
    "location_count_missing": "check official locations/store locator and independent directory",
    "ownership_missing": "check official about page and independent ownership evidence",
    "contact_route_uncertain": "verify the official-site direct chat URL and route type",
    "telegram_route_uncertain": "verify that the Telegram profile is a direct user account, not a bot/group/channel",
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
    passed = [r for r in pass_records if r.get("prelock_status", r.get("prelock_icp_status")) == "PRELOCK_PASS"
              or r.get("prelock_status") == "PASS"]
    vertical_counts: Counter[str] = Counter(classify_vertical(r) for r in passed)
    track_counts: Counter[str] = Counter(
        str(r.get("sampling_track") or track_for_vertical(classify_vertical(r))).casefold()
        for r in passed
    )
    channel_counts: Counter[str] = Counter(_channel(r) for r in passed)
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
            channel: max(0, target - channel_counts[channel])
            for channel, target in CHANNEL_TARGETS.items()
        },
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
    result = dict(result or row)
    status = str(result.get("prelock_status") or result.get("prelock_icp_status") or "PRELOCK_REVIEW")
    if status in {"PRELOCK_PASS", "PASS"}:
        return {**result, "prelock_status": "PRELOCK_PASS", "review_attempts": attempts,
                "next_review_action": None}
    if status in {"PRELOCK_REJECT", "REJECT"}:
        return {**result, "prelock_status": "PRELOCK_REJECT", "review_attempts": attempts,
                "next_review_action": None}
    reason = str(result.get("review_reason") or row.get("review_reason") or "other_evidence_missing")
    item = make_review_item(result, reason, attempts=attempts,
                            priority=row.get("review_priority"))
    if attempts >= max_attempts:
        item["prelock_status"] = "PRELOCK_PARKED"
        item["next_review_action"] = None
    return item


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


def run_expansion_loop(
    *,
    state_path: Path,
    required_slots_path: Path,
    source_yield_path: Path,
    discover_batch: Callable[..., dict[str, Any]],
    screen_and_preflight: Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]],
    repair_review: Callable[[dict[str, Any], str], dict[str, Any]],
    sample_ready: Callable[[list[dict[str, Any]]], bool],
    reserve_pool_target: int = RESERVE_POOL_TARGET,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_review_attempts: int = MAX_REVIEW_ATTEMPTS,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    """Keep discovering until sample-ready/exhausted; REVIEW never ends the run.

    Callbacks must use existing discovery, history, website/contact and ICP/buyer-intent
    implementations. All candidates and state are checkpointed after every batch.
    """
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")
    state_path, required_slots_path, source_yield_path = map(Path, (state_path, required_slots_path, source_yield_path))
    state = load_expansion_state(state_path, reserve_pool_target=reserve_pool_target)
    if state.get("status") in {"SAMPLE_READY", "SOURCE_EXHAUSTED"}:
        return state

    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        passes = state["pass_records"]
        state["required_slots"] = compute_required_slots(passes, reserve_pool_target=reserve_pool_target)
        write_json_atomic(required_slots_path, state["required_slots"])
        if len(passes) >= reserve_pool_target and sample_ready(passes):
            state["status"] = "SAMPLE_READY"
            break

        # Cheap repair first. Unresolved reviews are parked after the finite attempt budget.
        queue = sorted(state["review_queue"], key=lambda r: (
            int(r.get("review_priority", 99)), int(r.get("review_attempts", 0)),
            sampling_record_key(r),
        ))
        state["review_queue"] = []
        for item in queue:
            if item.get("prelock_status") != "PRELOCK_REVIEW":
                continue
            try:
                result = repair_review(item, str(item.get("next_review_action") or "inspect missing evidence"))
                updated = record_review_attempt(item, result, max_attempts=max_review_attempts)
            except Exception as exc:
                updated = record_review_attempt(item, {**item, "review_error": str(exc)},
                                                max_attempts=max_review_attempts)
            if updated["prelock_status"] == "PRELOCK_PASS":
                state["pass_records"] = _merge_rows(state["pass_records"], [updated])
            elif updated["prelock_status"] == "PRELOCK_REVIEW":
                state["review_queue"].append(updated)
            elif updated["prelock_status"] == "PRELOCK_PARKED":
                state["parked_records"] = _merge_rows(state["parked_records"], [updated])
            else:
                state["rejected_count"] += 1
                state["rejected_records"] = _merge_rows(state.get("rejected_records", []), [updated])
        passes = state["pass_records"]
        state["required_slots"] = compute_required_slots(passes, reserve_pool_target=reserve_pool_target)
        if len(passes) >= reserve_pool_target and sample_ready(passes):
            state["status"] = "SAMPLE_READY"
            break

        stopped = {name for name, metrics in state["source_yield"].items() if metrics.get("source_stop_reason")}
        order = rank_sources(state["source_yield"], stopped)
        try:
            batch = discover_batch(
                required_slots=state["required_slots"], preferred_sources=order,
                stopped_sources=sorted(stopped), batch_size=batch_size,
            )
        except Exception as exc:
            state.update(status="EXECUTION_BLOCKED", blocked_reason=str(exc))
            break

        rows = batch.get("records") or []
        source = str(batch.get("source_name") or "unknown_source")
        if source not in state["sources_attempted"]:
            state["sources_attempted"].append(source)
        if not rows:
            state["source_exhausted"] = bool(batch.get("all_sources_exhausted"))
            if state["source_exhausted"] and source_exhausted_criteria(state):
                state["status"] = "SOURCE_EXHAUSTED"
                break
            state["last_batch_result"] = {"source_name": source, "fresh_raw": 0,
                                          "note": "no rows returned; switch source or resume after adding sources"}
            if state["source_exhausted"]:
                # Keep a nonterminal checkpoint if the candidate-source registry is
                # exhausted before the evidence-based SOURCE_EXHAUSTED threshold.
                state["status"] = "PROGRESS"
                break
            state["source_yield"].setdefault(source, {"source_name": source})[
                "source_stop_reason"] = "source_returned_empty_batch"
            state["status"] = "RUNNING"
            write_json_atomic(state_path, state)
            continue

        processed_ids = set(state.get("processed_record_keys", [])) | {
            sampling_record_key(x) for x in state["pass_records"]
                         + state["review_queue"] + state["parked_records"]
                         + state.get("rejected_records", [])}
        fresh_rows = [r for r in rows if sampling_record_key(r) not in processed_ids]
        if not fresh_rows:
            state["last_batch_result"] = {"source_name": source, "fresh_raw": 0,
                                          "note": "batch contained only already processed identities"}
            state["source_yield"].setdefault(source, {"source_name": source})[
                "source_stop_reason"] = "duplicate_only_batch"
            state["status"] = "RUNNING"
            write_json_atomic(state_path, state)
            continue
        try:
            screened = screen_and_preflight(fresh_rows, state["required_slots"])
            if not isinstance(screened, list):
                raise TypeError("screen_and_preflight must return a list")
        except Exception as exc:
            state.update(status="EXECUTION_BLOCKED", blocked_reason=str(exc))
            break
        if {sampling_record_key(r) for r in screened} - {sampling_record_key(r) for r in fresh_rows}:
            raise ValueError("screen/preflight introduced a company outside the RAW batch")
        # Persist all completed outcomes, including REJECT. This prevents a
        # resume from re-counting or re-fetching rows merely because they were
        # not retained in the review/pass queues.
        state["processed_record_keys"] = sorted(
            set(state.get("processed_record_keys", []))
            | {sampling_record_key(row) for row in fresh_rows}
        )

        metrics = state["source_yield"].setdefault(source, {
            "source_name": source, "fresh_raw": 0, "website_resolved": 0,
            "website_fetch_success": 0, "website_fetch_failed": 0,
            "whatsapp_found": 0, "telegram_found": 0, "prelock_pass": 0,
            "prelock_review": 0, "prelock_reject": 0, "prelock_parked": 0,
        })
        batch_counts = Counter()
        for row in screened:
            status = str(row.get("prelock_status") or row.get("prelock_icp_status") or "PRELOCK_REVIEW")
            country = str(row.get("country") or row.get("country_code") or "unknown")
            vertical = classify_vertical(row)
            country_stats = metrics.setdefault("by_country", {}).setdefault(country, {
                "fresh_raw": 0, "website_resolved": 0, "whatsapp_found": 0,
                "telegram_found": 0, "prelock_pass": 0, "prelock_review": 0,
                "prelock_reject": 0,
            })
            vertical_stats = metrics.setdefault("by_vertical", {}).setdefault(vertical, {
                "fresh_raw": 0, "website_resolved": 0, "whatsapp_found": 0,
                "telegram_found": 0, "prelock_pass": 0, "prelock_review": 0,
                "prelock_reject": 0,
            })
            channels_found = {
                "whatsapp_found": bool(row.get("whatsapp_route") or row.get("whatsapp_url")
                                       or row.get("prelock_channel") == "whatsapp"),
                "telegram_found": bool(row.get("telegram_route") or row.get("telegram_url")
                                       or row.get("prelock_channel") == "telegram"),
            }
            website_resolved = bool(row.get("website_url")) and row.get("website_resolution_status") != "unresolved"
            website_status = str(row.get("website_fetch_status") or row.get("contact_enrichment_status")
                                 or row.get("research_status") or "")
            fetch_success = website_status in {"ok", "success", "completed", "pages_collected"}
            fetch_failed = website_status in {"fetch_failed", "website_fetch_failed"}
            for bucket in (country_stats, vertical_stats):
                bucket["fresh_raw"] += 1
                bucket["website_resolved"] += int(website_resolved)
                for channel, found in channels_found.items():
                    bucket[channel] += int(found)
            if status in {"PASS", "PRELOCK_PASS"}:
                row["prelock_status"] = "PRELOCK_PASS"
                state["pass_records"] = _merge_rows(state["pass_records"], [row])
                metrics["prelock_pass"] += 1; batch_counts["prelock_pass"] += 1
                country_stats["prelock_pass"] += 1; vertical_stats["prelock_pass"] += 1
            elif status in {"REJECT", "PRELOCK_REJECT"}:
                metrics["prelock_reject"] += 1; batch_counts["prelock_reject"] += 1
                country_stats["prelock_reject"] += 1; vertical_stats["prelock_reject"] += 1
                state["rejected_count"] += 1
                state["rejected_records"] = _merge_rows(state.get("rejected_records", []), [row])
            else:
                item = make_review_item(row, str(row.get("review_reason") or "other_evidence_missing"),
                                        attempts=int(row.get("review_attempts", 0)))
                state["review_queue"] = _merge_rows(state["review_queue"], [item])
                metrics["prelock_review"] += 1; batch_counts["prelock_review"] += 1
                country_stats["prelock_review"] += 1; vertical_stats["prelock_review"] += 1
            metrics["website_resolved"] += int(website_resolved)
            metrics["website_fetch_success"] += int(fetch_success)
            metrics["website_fetch_failed"] += int(fetch_failed)
            metrics["whatsapp_found"] += int(channels_found["whatsapp_found"])
            metrics["telegram_found"] += int(channels_found["telegram_found"])
        metrics["fresh_raw"] += len(fresh_rows)
        metrics["raw_count"] = metrics["fresh_raw"]
        metrics["pass_rate"] = round(metrics["prelock_pass"] / metrics["fresh_raw"], 4)
        metrics["whatsapp_yield"] = round(metrics["whatsapp_found"] / metrics["fresh_raw"], 4)
        metrics["telegram_yield"] = round(metrics["telegram_found"] / metrics["fresh_raw"], 4)
        metrics["website_resolution_rate"] = round(metrics["website_resolved"] / metrics["fresh_raw"], 4)
        reason = source_stop_reason(metrics)
        if reason:
            metrics["source_stop_reason"] = reason

        state["fresh_raw_scanned"] += len(fresh_rows)
        state["reserve_pool_pass"] = len(state["pass_records"])
        record = {"source_name": source, "fresh_raw": len(fresh_rows),
                  "prelock_pass": batch_counts["prelock_pass"],
                  "prelock_review": batch_counts["prelock_review"],
                  "prelock_reject": batch_counts["prelock_reject"],
                  "completed_at": utc_now()}
        state["batch_history"].append(record)
        state["consecutive_low_yield_batches"] = (
            int(state.get("consecutive_low_yield_batches", 0)) + 1
            if record["prelock_pass"] <= 1 else 0
        )
        state["last_batch_result"] = record
        state["updated_at"] = utc_now()
        state["required_slots"] = compute_required_slots(
            state["pass_records"], reserve_pool_target=reserve_pool_target)
        if len(state["pass_records"]) >= reserve_pool_target and sample_ready(state["pass_records"]):
            state["status"] = "SAMPLE_READY"
            break
        if batch.get("all_sources_exhausted") and source_exhausted_criteria(state):
            state["status"] = "SOURCE_EXHAUSTED"
            break
        state["status"] = "RUNNING"

        write_json_atomic(required_slots_path, state["required_slots"])
        write_json_atomic(source_yield_path, state["source_yield"])
        write_json_atomic(state_path, state)

    state["review_queue_count"] = len(state["review_queue"])
    state["parked"] = len(state["parked_records"])
    state["terminal_status"] = state.get("status") if state.get("status") in {
        "SAMPLE_READY", "SOURCE_EXHAUSTED", "EXECUTION_BLOCKED"
    } else None
    state["updated_at"] = utc_now()
    write_json_atomic(required_slots_path, state["required_slots"])
    write_json_atomic(source_yield_path, state["source_yield"])
    write_json_atomic(state_path, state)
    return state
