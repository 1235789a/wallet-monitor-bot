"""Quota-aware, resumable prelock expansion over an existing source-first RAW pool."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from prospect_os.buyer_rating import RATING_CONFIG, rate_candidate
from prospect_os.contact_pools import screen_raw_pool
from prospect_os.expansion import (
    MAX_REVIEW_ATTEMPTS, compute_required_slots, load_expansion_state,
    make_review_item, record_review_attempt, run_expansion_loop, write_json_atomic,
)
from prospect_os.history_exclusion import exclude_history
from prospect_os.prelock_preflight import preflight_record
from prospect_os.sample_lock import freeze_sample
from prospect_os.sampling import (
    DEFAULT_SEED, FORMAL_30_QUOTAS, SECONDARY, classify_vertical, sampling_record_key,
    stratified_sample,
)
from prospect_os.source_yield import build_source_yield
from prospect_os.website_resolution import resolve_website, resolve_website_pool
from research_buyer_batch import assign_contact_quota


def _source_key(row):
    for field in ("source_type", "source_dataset_url", "source_name",
                  "discovery_source_url", "profile_url"):
        value = str(row.get(field) or "").strip()
        if value:
            return (urlsplit(value).hostname or value).casefold().removeprefix("www.") if value.startswith(("http://", "https://")) else value
    return "unknown_source"


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
    aliases = {"record:" + sampling_record_key(row)}
    domain = urlsplit(str(row.get("website_url") or row.get("domain") or "")).hostname or ""
    domain = domain.casefold().removeprefix("www.").strip(".")
    if domain:
        aliases.add("domain:" + domain)
    else:
        name = " ".join(str(row.get("company_name") or "").casefold().split())
        if name:
            aliases.add("name:" + name)
    return aliases


def _review_reason(row):
    missing = " ".join(str(x) for x in row.get("prelock_missing_evidence", []))
    reason = str(row.get("prelock_icp_reason") or "") + " " + missing
    folded = reason.casefold()
    if "location" in folded:
        return "location_count_missing"
    if "ownership" in folded or "independent" in folded:
        return "ownership_missing"
    if "telegram" in folded:
        return "telegram_route_uncertain"
    if "chat" in folded or "route" in folded:
        return "contact_route_uncertain"
    if "decision" in folded or "team" in folded:
        return "decision_maker_missing"
    if "buyer" in folded or "query" in folded or "competitor" in folded:
        return "buyer_intent_missing"
    if "website" in folded or "official_website" in folded:
        return "website_unresolved" if not row.get("website_url") else "website_fetch_failed"
    return "other_evidence_missing"


def _merge_cache_files(paths, target):
    """Merge only validated JSONL cache entries; source caches are read-only."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    for path in sorted(set(map(Path, paths))):
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
    source_yield_report=None, batch_size=100, workers=24, max_pages=5,
    reserve_pool_target=42, seed=DEFAULT_SEED,
):
    root, run_dir = Path(root), Path(run_dir)
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
    cursors = Counter()

    selection = {"rows": [], "summary": {}, "channel_assignment": {}}

    def sample_ready(rows):
        qualified = [r for r in rows if r.get("prelock_status") == "PRELOCK_PASS"
                     and r.get("buyer_grade") not in RATING_CONFIG["formal_exclude_grades"]]
        if len(rows) < reserve_pool_target:
            return False
        chosen, summary = stratified_sample(
            qualified, limit=30, seed=seed, prefer_whatsapp=True, telegram_cap=6,
        )
        if len(chosen) != 30:
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

    def discover_batch(*, required_slots, preferred_sources, stopped_sources, batch_size):
        stopped = set(stopped_sources)
        available = {name: rows for name, rows in grouped.items()
                     if name not in stopped and cursors[name] < len(rows)}
        if not available:
            return {"source_name": "all_sources", "records": [], "all_sources_exhausted": True}
        short = required_slots.get("vertical_shortfall", {})
        priority_names = [n for n in preferred_sources if n in available]
        priority_names += sorted(n for n in available if n not in priority_names)
        needed = {vertical for vertical, count in short.items() if count > 0}
        # If a channel is still short, keep testing all formal verticals for
        # route opportunities; the RAW source usually cannot disclose channel
        # type until its official site is screened.
        if any(int(value) > 0 for value in required_slots.get("channel_shortfall", {}).values()):
            needed.update(FORMAL_30_QUOTAS)
        for name in priority_names:
            rows = available[name]
            relevant = [r for r in rows[cursors[name]:]
                        if classify_vertical(r) in needed] if needed else []
            if not relevant and not needed:
                relevant = rows[cursors[name]:]
            if not relevant:
                continue
            selected = relevant[:batch_size]
            if not selected:
                continue
            ids = {sampling_record_key(r) for r in selected}
            # Preserve source order for deterministic resumption while taking only this batch.
            remaining = [r for r in rows[cursors[name]:] if sampling_record_key(r) not in ids]
            rows[cursors[name]:] = remaining
            return {"source_name": name, "records": selected,
                    "all_sources_exhausted": not any(
                        other not in stopped and cursors[other] < len(grouped[other])
                        for other in grouped)}
        return {"source_name": "all_sources", "records": [], "all_sources_exhausted": True}

    def screen_and_preflight(rows, _slots):
        resolved = resolve_website_pool(
            rows, cache_path=website_cache, resolver_fn=resolve_website,
            workers=min(workers, 24),
        )
        pools = screen_raw_pool(
            resolved, cache_path=contact_cache, workers=workers, max_pages=max_pages,
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

    def repair_review(row, _action):
        # Re-evaluate cached/source-backed evidence only. Any new assertion still
        # needs a public evidence URL before preflight can promote the candidate.
        return rate_candidate(preflight_record(row))

    result = run_expansion_loop(
        state_path=state_path, required_slots_path=required_path, source_yield_path=yield_path,
        discover_batch=discover_batch, screen_and_preflight=screen_and_preflight,
        repair_review=repair_review, sample_ready=sample_ready,
        reserve_pool_target=reserve_pool_target, batch_size=batch_size,
        max_review_attempts=MAX_REVIEW_ATTEMPTS,
    )
    result["excluded_history"] = len(excluded)
    result["pending_raw_remaining"] = sum(max(0, len(rows) - cursors[name]) for name, rows in grouped.items())
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
        "fresh_raw_scanned": result.get("fresh_raw_scanned"),
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
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--pages", type=int, default=5)
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
    )
    print(json.dumps({
        "terminal_status": result.get("terminal_status"),
        "status": result.get("status"),
        "fresh_raw_scanned": result.get("fresh_raw_scanned"),
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
