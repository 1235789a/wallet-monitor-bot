"""Quota-aware, resumable prelock expansion over an existing source-first RAW pool."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from prospect_os.buyer_rating import RATING_CONFIG, rate_candidate
from prospect_os.contact_pools import screen_raw_pool
from prospect_os.expansion import (
    MAX_REVIEW_ATTEMPTS, compute_required_slots, load_expansion_state,
    make_review_item, record_review_attempt, review_reason, run_expansion_loop, write_json_atomic,
)
from prospect_os.history_exclusion import exclude_history
from prospect_os.prelock_preflight import preflight_record
from prospect_os.sample_lock import freeze_sample, load_lock
from prospect_os.source_scheduler import schedule_raw, source_key, identity_aliases, segment_key
from prospect_os.review_repair import ReviewRepairer
from prospect_os.sampling import (
    DEFAULT_SEED, FORMAL_30_QUOTAS, SECONDARY, classify_vertical, sampling_record_key,
    stratified_sample, formal_sample,
)
from prospect_os.source_yield import build_source_yield
from prospect_os.website_resolution import resolve_website, resolve_website_pool
from research_buyer_batch import assign_contact_quota


def _source_key(row):
    return source_key(row)


def _historical_source_key(name):
    folded = str(name or "").casefold()
    for token, key in (
        ("startupbase", "startupbase_abstartups"),
        ("himerus", "himerus_retailer_directory"),
        ("vaper.eu", "vaper_eu_pt"),
        ("brasil de vinhos", "brasil_de_vinhos_directory"),
        ("raisin brazil", "brasil_de_vinhos_directory"),
        ("escort guide", "industry_directory"),
        ("mappingbitcoin", "industry_directory"),
    ):
        if token in folded:
            return key
    return str(name or "unknown_source")


def _identity_aliases(row):
    """Crosswalk RAW and prelock records with different source IDs."""
    return identity_aliases(row)


def _review_reason(row):
    return review_reason(row)


def _merge_cache_files(paths, target):
    """Merge only validated JSONL cache entries; source caches are read-only."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    prior = sorted(set(map(Path, paths)) - {target})
    for path in prior + [target]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict) and item.get("key") and isinstance(item.get("row"), dict):
                    rows[item["key"]] = item
            except json.JSONDecodeError:
                continue
    target.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in rows.values()),
                      encoding="utf-8")
    return len(rows)


def _history_inputs(root, explicit):
    inputs = [("history_used", path) for path in explicit]
    for path in (
        root / "runs/buyer-sprint/2026-09-24-1222/history-used-minimal.json",
        root / "runs/buyer-sprint/discovery/west-yorkshire-2026-09-24/previously-contacted-from-session.json",
        root / "runs/buyer-sprint/2026-09-26-deep-contact/supplemental-current-clients.json",
    ):
        if path.exists() and all(path != prior for _, prior in inputs):
            inputs.append(("previous_contacted", path))
    for path in sorted((root / "runs/buyer-sprint").rglob("sampled-lock.json")):
        if path.parent.name == "2026-10-01-continuous-expansion":
            continue
        inputs.append(("previous_sample_lock", path))
    return inputs


def run_expansion(
    raw_rows, initial_rows, *, root, run_dir, history_sources,
    source_yield_report=None, batch_size=75, workers=12, max_pages=2,
    reserve_pool_target=42, seed=DEFAULT_SEED,
    max_records=100, max_reviews=20, max_cycles=3, review_evidence=(),
    screen_fn=None, resolver_fn=resolve_website, repairer=None,
):
    root, run_dir = Path(root), Path(run_dir)
    if not 1 <= max_pages <= 2:
        raise ValueError("prelock screening supports one or two pages; deeper research belongs after Sample Lock")
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "expansion-state.json"
    required_path = run_dir / "required_slots.json"
    yield_path = run_dir / "source-yield.json"
    excluded_path = run_dir / "excluded-history.json"
    website_cache = run_dir / "website-resolution.jsonl"
    contact_cache = run_dir / "prelock-screen.jsonl"

    # Merge read-only caches from prior runs so previously inspected sites are not fetched again.
    prior_contact_caches = list((root / "runs/buyer-sprint").rglob("prelock-screen.jsonl"))
    prior_website_caches = list((root / "runs/buyer-sprint").rglob("website-resolution.jsonl"))
    contact_cache_rows = _merge_cache_files(prior_contact_caches, contact_cache)
    website_cache_rows = _merge_cache_files(prior_website_caches, website_cache)

    if state_path.exists():
        state = load_expansion_state(state_path, reserve_pool_target=reserve_pool_target)
    else:
        pass_rows = [dict(r) for r in initial_rows if r.get("prelock_status") == "PRELOCK_PASS"]
        review_rows = [make_review_item(dict(r), _review_reason(r),
                                        attempts=int(r.get("review_attempts", 0)))
                       for r in initial_rows if r.get("prelock_status") == "PRELOCK_REVIEW"]
        rejects = [dict(r) for r in initial_rows if r.get("prelock_status") == "PRELOCK_REJECT"]
        source_yield = {}
        if source_yield_report:
            for item in source_yield_report.get("sources", []):
                name = _historical_source_key(item.get("source_name"))
                source_yield[name] = {
                    "source_name": name,
                    "raw_count": int(item.get("raw_added", 0)),
                    "fresh_raw": int(item.get("raw_added", 0)),
                    "website_resolved": int(item.get("website_resolved", 0)),
                    "website_resolution_rate": float(item.get("website_resolution_rate",
                        item.get("website_fetch_success", 0) / max(1, item.get("raw_added", 0)))),
                    "website_fetch_success": int(item.get("website_fetch_success", 0)),
                    "website_fetch_failed": int(item.get("website_fetch_failed", 0)),
                    "whatsapp_found": int(item.get("verified_whatsapp", 0)),
                    "telegram_found": int(item.get("verified_telegram", 0)),
                    "prelock_pass": int(item.get("prelock_pass", 0)),
                    "prelock_review": int(item.get("prelock_review", 0)),
                    "prelock_reject": int(item.get("prelock_reject", 0)),
                    "pass_rate": float(item.get("pass_yield_rate", 0)),
                    "whatsapp_yield": float(item.get("whatsapp_yield_rate", 0)),
                    "telegram_yield": float(item.get("telegram_yield_rate", 0)),
                }
            for item in source_yield_report.get("groups", []):
                name = _historical_source_key(item.get("source_name") or item.get("source"))
                metrics = source_yield.setdefault(name, {"source_name": name, "by_segment": {}})
                metrics.setdefault("by_segment", {})[segment_key(item)] = {
                    "fresh_raw": int(item.get("screened_count", 0)),
                    "prelock_pass": int(item.get("prelock_pass_count", 0)),
                    "human_whatsapp_found": int(item.get("human_whatsapp_found", 0)),
                    "human_telegram_found": int(item.get("human_telegram_found", 0)),
                }
        state = {
            "status": "RUNNING", "fresh_raw_scanned": 0, "sources_attempted": [],
            "source_yield": source_yield, "reserve_pool_target": reserve_pool_target,
            "reserve_pool_pass": len(pass_rows), "pass_records": pass_rows,
            "review_queue": review_rows, "parked_records": [], "rejected_records": rejects,
            "rejected_count": len(rejects), "consecutive_low_yield_batches": 0,
            "batch_history": [], "merged_contact_cache_entries": contact_cache_rows,
            "merged_website_cache_entries": website_cache_rows,
        }
        state["required_slots"] = compute_required_slots(pass_rows, reserve_pool_target=reserve_pool_target)
        write_json_atomic(state_path, state)

    if "historical_source_yield" not in state:
        state["historical_source_yield"] = state.get("source_yield", {})
    state["schema_version"] = 2
    write_json_atomic(state_path, state)

    # Historical locked cohorts remain immutable. A resume may report them,
    # but never attempts to freeze an empty or newly selected replacement.
    if state.get("status") == "SAMPLE_READY" and (run_dir / "sampled-lock.json").exists():
        load_lock(run_dir / "sampled-lock.json")
        state["this_run"] = {"fresh_raw_processed": 0, "review_attempts": 0}
        return state
    if state.get("status") != "SAMPLE_READY":
        updates = {sampling_record_key(row): row for row in review_evidence}
        retained = []
        for row in state.get("parked_records", []):
            patch = updates.get(sampling_record_key(row))
            digest = hashlib.sha256(json.dumps(patch, sort_keys=True).encode()).hexdigest() if patch else None
            if patch and digest != row.get("review_input_sha256"):
                state["review_queue"].append(make_review_item(row, _review_reason(row), attempts=0))
            else:
                retained.append(row)
        state["parked_records"] = retained
        initial_excluded = []
        for key in ("pass_records", "review_queue", "parked_records", "rejected_records"):
            state[key], historical = exclude_history(state.get(key, []), history_sources)
            initial_excluded.extend(historical)
        state["initial_history_excluded"] = len(initial_excluded)
        previous_passes = state.get("pass_records", [])
        state["pass_records"] = []
        for row in previous_passes:
            checked = rate_candidate(preflight_record(row))
            if checked["prelock_status"] == "PRELOCK_PASS":
                state["pass_records"].append(checked)
            elif checked["prelock_status"] == "PRELOCK_REJECT":
                state["rejected_records"].append(checked)
            else:
                state["review_queue"].append(make_review_item(checked, _review_reason(checked)))
        write_json_atomic(state_path, state)

    eligible, excluded = exclude_history(raw_rows, history_sources)
    write_json_atomic(excluded_path, excluded)
    excluded_ids = {sampling_record_key(r) for r in raw_rows if any(
        str(e.get("identity_key") or "") == str(r.get("identity_key") or "") and r.get("identity_key")
        for e in excluded)}
    processed_rows = (state.get("pass_records", []) + state.get("review_queue", [])
                      + state.get("parked_records", []) + state.get("rejected_records", []))
    processed_aliases = set().union(*(_identity_aliases(r) for r in processed_rows)) if processed_rows else set()
    pending = [dict(r) for r in eligible
               if not (_identity_aliases(r) & processed_aliases)
               and sampling_record_key(r) not in excluded_ids]
    grouped = defaultdict(list)
    for row in pending:
        # Keep this production loop focused on the already-approved formal
        # verticals. Secondary/unknown RAW remains in the master pool but cannot
        # consume contact-screening capacity or distort source yield.
        if classify_vertical(row) != SECONDARY:
            grouped[_source_key(row)].append(row)

    selection = {"rows": [], "summary": {}, "channel_assignment": {}}

    def sample_ready(rows):
        qualified = [r for r in rows if r.get("prelock_status") == "PRELOCK_PASS"
                     and r.get("buyer_grade") not in RATING_CONFIG["formal_exclude_grades"]]
        if len(qualified) < reserve_pool_target:
            return False
        chosen, summary = formal_sample(qualified, seed=seed)
        if len(chosen) != 30 or summary["eligible_pool"] < reserve_pool_target:
            return False
        chosen, assignment = assign_contact_quota(
            chosen, seed=seed, required=RATING_CONFIG["formal_channels"])
        counts = Counter(r.get("prelock_channel") for r in chosen)
        by_vertical = Counter(r.get("sampling_vertical") or classify_vertical(r) for r in chosen)
        if (not assignment.get("feasible")
            or counts != Counter({"whatsapp": 24, "telegram": 6})
            or summary.get("track_counts") != {"track_a": 15, "track_b": 15}
            or any(by_vertical[v] != n for v, n in FORMAL_30_QUOTAS.items())):
            return False
        selection.update(rows=chosen, summary=summary, channel_assignment=assignment)
        return True

    cached_keys = set()
    if contact_cache.exists():
        for line in contact_cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cached_keys.add(sampling_record_key(json.loads(line)["row"]))

    def discover_batch(*, required_slots, preferred_sources, stopped_sources, batch_size):
        current = load_expansion_state(state_path, reserve_pool_target=reserve_pool_target)
        processed = sum((current.get(key, []) for key in (
            "pass_records", "review_queue", "parked_records", "rejected_records")), [])
        candidates = [row for rows in grouped.values() for row in rows]
        processed_keys = set(current.get("processed_record_keys", []))
        candidates = [row for row in candidates if sampling_record_key(row) not in processed_keys]
        yields = {**current.get("historical_source_yield", {}), **current.get("source_yield", {})}
        planned = schedule_raw(candidates, required_slots, yields,
                               batch_size=batch_size, seed=seed, processed=processed,
                               cached_keys=cached_keys, stopped_sources=stopped_sources)
        return {"source_name": "mixed_raw", "records": planned,
                "all_sources_exhausted": not planned}

    def screen_and_preflight(rows, _slots):
        resolved = resolve_website_pool(
            rows, cache_path=website_cache, resolver_fn=resolver_fn,
            workers=min(workers, 24),
        )
        pools = screen_raw_pool(
            resolved, cache_path=contact_cache, workers=workers, max_pages=max_pages, screen_fn=screen_fn,
            retry_failed=False,
        )
        screened = [r for key in ("chat", "review", "email", "email_review")
                    for r in pools.get(key, [])]
        assessed = [rate_candidate(preflight_record(row)) for row in screened]
        # Preserve the existing peer exclusion as a hard reject, and include
        # every input row in batch accounting so yield metrics cannot silently
        # omit excluded/email-only candidates.
        for row in pools.get("peer_excluded", []):
            assessed.append({**row, "prelock_status": "PRELOCK_REJECT",
                             "prelock_reject_reasons": [row.get("peer_exclusion_reason") or "peer_agency"]})
        accounted = {sampling_record_key(row) for row in assessed}
        for row in rows:
            if sampling_record_key(row) not in accounted:
                assessed.append({**row, "prelock_status": "PRELOCK_REVIEW",
                                 "prelock_icp_reason": "screening result missing; retain for review",
                                 "review_reason": "other_evidence_missing"})
        return assessed

    repairer = repairer or ReviewRepairer(run_dir / "review-evidence-cache", raw_rows=raw_rows,
                                          evidence_rows=review_evidence, max_pages=2, max_queries=2)

    def repair_review(row, action):
        if _review_reason(row) == "website_unresolved":
            row = resolver_fn(row)
        return repairer(row, action)

    result = run_expansion_loop(
        state_path=state_path, required_slots_path=required_path, source_yield_path=yield_path,
        discover_batch=discover_batch, screen_and_preflight=screen_and_preflight,
        repair_review=repair_review, sample_ready=sample_ready,
        reserve_pool_target=reserve_pool_target, batch_size=batch_size,
        max_review_attempts=MAX_REVIEW_ATTEMPTS, max_fresh_raw=max_records,
        max_review_records=max_reviews, max_cycles=max_cycles,
    )
    result["review_collection_usage"] = getattr(repairer, "usage", {})
    result["excluded_history"] = len(excluded)
    result["pending_raw_remaining"] = sum(sampling_record_key(row) not in set(result.get("processed_record_keys", []))
        for rows in grouped.values() for row in rows)
    result["merged_contact_cache_entries"] = contact_cache_rows
    result["merged_website_cache_entries"] = website_cache_rows
    if result.get("status") == "SAMPLE_READY":
        lock_path = run_dir / "sampled-lock.json"
        lock = freeze_sample(lock_path, selection["rows"], seed=seed, limit=30,
                             summary={**selection["summary"],
                                      "contact_quota_assignment": selection["channel_assignment"],
                                      "reserve_pool_pass": len(result["pass_records"])})
        result["sample_lock_created"] = True
        result["sample_lock"] = str(lock_path)
        write_json_atomic(run_dir / "sampling-summary.json", lock.get("sampling_summary", {}))
    else:
        result["sample_lock_created"] = False
    write_json_atomic(state_path, result)
    write_json_atomic(run_dir / "expansion-result.json", {
        "terminal_status": result.get("terminal_status"), "status": result.get("status"),
        "this_run": result.get("this_run"),
        "current_totals": result.get("current_totals"),
        "cumulative_fresh_raw_scanned": result.get("fresh_raw_scanned"),
        "sources_attempted": result.get("sources_attempted"),
        "reserve_pool_target": reserve_pool_target,
        "reserve_pool_pass": len(result.get("pass_records", [])),
        "review_queue": len(result.get("review_queue", [])),
        "parked": len(result.get("parked_records", [])),
        "rejected": result.get("rejected_count", 0),
        "required_slots": result.get("required_slots"),
        "source_yield": result.get("source_yield"),
        "sample_lock_created": result.get("sample_lock_created", False),
    })
    return result


def main():
    parser = argparse.ArgumentParser(description="Resume source-first prelock expansion from cached Prospect OS state")
    parser.add_argument("--source", type=Path, required=True, help="Existing merged source-first RAW JSON array")
    parser.add_argument("--initial-prelock", type=Path, required=True, help="Existing prelock-rated-candidates.json")
    parser.add_argument("--source-yield", type=Path, help="Existing source-yield-priority-ranking JSON")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--history", type=Path, action="append", default=[])
    parser.add_argument("--batch-size", type=int, default=75)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--max-records", type=int, default=100)
    parser.add_argument("--max-reviews", type=int, default=20)
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--review-evidence", type=Path, help="Reviewed evidence updates for existing company IDs")
    parser.add_argument("--reserve-pool-target", type=int, default=42)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    root = Path.cwd()
    raw = json.loads(args.source.read_text(encoding="utf-8"))
    initial = json.loads(args.initial_prelock.read_text(encoding="utf-8"))
    yield_report = json.loads(args.source_yield.read_text(encoding="utf-8")) if args.source_yield else None
    history = _history_inputs(root, args.history)
    result = run_expansion(
        raw, initial, root=root, run_dir=args.run_dir, history_sources=history,
        source_yield_report=yield_report, batch_size=args.batch_size, workers=args.workers,
        max_pages=args.pages, reserve_pool_target=args.reserve_pool_target, seed=args.seed,
        max_records=args.max_records, max_reviews=args.max_reviews, max_cycles=args.max_cycles,
        review_evidence=json.loads(args.review_evidence.read_text(encoding="utf-8")) if args.review_evidence else (),
    )
    print(json.dumps({
        "terminal_status": result.get("terminal_status"),
        "status": result.get("status"),
        "this_run": result.get("this_run"),
        "current_totals": result.get("current_totals"),
        "cumulative_fresh_raw_scanned": result.get("fresh_raw_scanned"),
        "sources_attempted": len(result.get("sources_attempted", [])),
        "prelock_pass": len(result.get("pass_records", [])),
        "prelock_review": len(result.get("review_queue", [])),
        "prelock_parked": len(result.get("parked_records", [])),
        "prelock_reject": result.get("rejected_count", 0),
        "required_slots": result.get("required_slots"),
        "sample_lock_created": result.get("sample_lock_created", False),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
