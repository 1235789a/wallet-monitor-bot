#!/usr/bin/env python3
"""Recheck an archived WA batch as continuation only; never count new or authorize sending."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.cross_channel_dedupe import CrossChannelDedupeEngine, normalize_company_name
from prospect_os.daily27_models import CandidateRecord
from prospect_os.wa_website_preflight import preflight_website


def review_existing(payload, sources, company_names=(), *, max_records=10, fetch=False):
    if payload.get("schema") != "multihub-history-index-v1" or not sources or not 1 <= max_records <= (10 if fetch else 1000):
        raise ValueError("Supply a private index and exact archived source URLs; live fetch max 10, local review max 1000")
    names = {normalize_company_name(n) for n in company_names}
    selected = [r for r in payload["records"] if r.get("source_url") in sources and r.get("record_kind") == "RESEARCH_PRESENTED" and r.get("source_tag") == "DAILY_PRESENTED"]
    if set(sources) - {r["source_url"] for r in selected}:
        raise ValueError("One or more archive sources not present in history")
    targets = [r for r in selected if not names or normalize_company_name(r.get("company_name", "")) in names]
    if names - {normalize_company_name(r["company_name"]) for r in targets}:
        raise ValueError("Requested identity not found in the named archive")
    # Compare against all *other* historical archives; this exact batch is a
    # continuation, not a new candidate. Keep the production snapshot unchanged.
    reduced = {**payload, "records": [r for r in payload["records"] if not (r.get("source_url") in sources and r.get("record_kind") == "RESEARCH_PRESENTED")],
               "coverage": {**payload["coverage"], "DAILY_PRESENTED": {**payload["coverage"]["DAILY_PRESENTED"], "status": "PARTIAL"}}}
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "comparison.json"
        p.write_text(json.dumps(reduced), encoding="utf-8")
        engine = CrossChannelDedupeEngine()
        engine.load_verified_history_index(p)
    seen, out = set(), []
    for r in targets[:max_records]:
        pid = r.get("original_prospect_id") or "ARCHIVE-" + hashlib.sha256((r["source_url"] + "#" + r["source_locator"]).encode()).hexdigest()[:20]
        domain = r.get("canonical_domain", "")
        official = "https://" + domain if domain else ""
        rec = CandidateRecord(pid, r["company_name"], r["source_url"], official_url=official, channel="WA", contact_url=r.get("contact_url", ""))
        engine.check_candidate(rec, seen)
        item = {"original_prospect_id": pid, "company_name": r["company_name"], "archive_source": r["source_url"],
                "archive_locator": r["source_locator"], "website_hint": official, "comparison_status": rec.history_status,
                "matched_history_sources": rec.matched_history_sources, "continuation_only": True, "send_ready": False,
                "wa_preflight_status": "NOT_TESTED" if official else "HOLD_NO_WEBSITE_HINT"}
        if fetch and official and rec.stage != "HISTORY_LOCK":
            result = preflight_website({"original_prospect_id": pid, "company_name": r["company_name"], "website_url": official}, render=False)
            item["wa_preflight_status"] = result["wa_preflight_status"]
            item["wa_routes"] = result["wa_routes"]
            item["website_errors"] = result["contact_enrichment_errors"]
        out.append(item)
    return {"mode": "CONTINUATION_RESEARCH_ONLY", "records": out, "requested": len(targets), "new_leads": 0, "send_ready": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history-index", required=True, type=Path)
    p.add_argument("--source-url", required=True, action="append")
    p.add_argument("--company", action="append", default=[])
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--fetch-website", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = review_existing(json.loads(a.history_index.read_text()), set(a.source_url), a.company, max_records=a.limit, fetch=a.fetch_website)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "reviewed": len(report["records"]), "new_leads": 0, "send_ready": 0}))


if __name__ == "__main__": main()
