#!/usr/bin/env python3
"""Gemini WA-only public business route preflight, before expensive ICP research."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.wa_website_preflight import preflight_website
from prospect_os.wa_batch_intake import history_precheck, load_discovery, audit_legacy_csv, PARTIAL_PILOT_MAX
from prospect_os.daily27_models import CandidateRecord
from prospect_os.source_pool import canonical_domain
from prospect_os.cross_channel_dedupe import normalize_company_name, normalize_domain_key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="Strict multihub-wa-discovery-v1 JSON envelope")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--history-index", type=Path, help="Current private history data with per-source coverage")
    parser.add_argument("--check-history-only", action="store_true", help="Report missing history categories before discovery")
    parser.add_argument("--partial-pilot", action="store_true", help="At most 10 research-only probes if history incomplete")
    parser.add_argument("--audit-legacy-csv", type=Path, help="Check old CSV width only; never import it")
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--per-source", type=int, default=10, help="Bound cheap probes per independent source")
    args = parser.parse_args()
    if args.audit_legacy_csv:
        audit = audit_legacy_csv(args.audit_legacy_csv)
        print(json.dumps(audit, indent=2))
        return 0 if audit["valid"] else 2
    engine, history = history_precheck(args.history_index)
    if args.check_history_only:
        print(json.dumps(history, indent=2))
        return 0 if history["scale_allowed"] else 2
    if not args.input or not args.output:
        parser.error("input and output required for website preflight")
    if not history["scale_allowed"] and (not args.partial_pilot or not history["history_records"]):
        print(json.dumps({"status": "BLOCKED_BEFORE_DISCOVERY", "history": history, "probed": 0}, indent=2))
        return 2
    if args.per_source < 1 or args.per_source > 20:
        parser.error("--per-source must be between 1 and 20")
    try:
        rows = load_discovery(args.input)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "INVALID_DISCOVERY_INPUT", "error": str(exc), "probed": 0}))
        return 2
    if args.partial_pilot and len(rows) > PARTIAL_PILOT_MAX:
        print(json.dumps({"status": "PILOT_LIMIT_EXCEEDED", "max_rows": PARTIAL_PILOT_MAX, "probed": 0}))
        return 2
    probes, counts, output = Counter(), Counter(), []
    seen_raw, seen_verified = set(), set()
    for row in rows:
        pid, source_url = row["original_prospect_id"], row["discovery_source_url"]
        source = canonical_domain(source_url)
        def candidate():
            return CandidateRecord(pid, row["company_name"], source_url, official_url=row["website_url"], channel="WA")
        raw = engine.check_candidate(candidate(), seen_raw)
        known_checkpoint = (normalize_domain_key(row["website_url"]) in engine.in_progress_ids
                            or normalize_company_name(row["company_name"]) in engine.in_progress_ids)
        if raw.stage == "HISTORY_LOCK" or raw.is_in_progress_resume or known_checkpoint:
            output.append({**row, "wa_preflight_status": "SKIP_KNOWN_OR_REPEAT", "history_status": raw.history_status,
                           "send_ready": False})
            continue
        if probes[source] >= args.per_source:
            continue
        probes[source] += 1
        result = preflight_website(row, render=not args.static_only)
        verified = candidate()
        verified.all_public_links = [c["value"] for c in result["wa_routes"] if not c.get("route_verification_status")]
        reviewed = engine.check_candidate(verified, seen_verified)
        result["history_status"] = reviewed.history_status
        result["history_matches"] = reviewed.matched_history_sources
        result["research_status"] = "REQUIRES_ACTIVITY_ICP_RECIPIENT_REVIEW"
        counts[(source, result["wa_preflight_status"])] += 1
        output.append(result)
    args.output.write_text(json.dumps({"records": output, "history": history, "probed": sum(probes.values()), "source_metrics": [
        {"source": source, "status": status, "count": count, "probed": probes[source]}
        for (source, status), count in counts.items()], "send_ready": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
