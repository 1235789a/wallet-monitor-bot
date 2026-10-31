#!/usr/bin/env python3
"""MultiHub daily 27: structural checks only, NOT evidence/identity verification."""
import json
import re
import sys
from datetime import date
from urllib.parse import urlparse

TARGETS = {"WA": 15, "TG": 2, "FB": 10}
RETAIL_TARGETS = {"wine": 1, "vape": 1, "adult": 1}
REQUIRED_HISTORY = {"103_MASTER", "112_MASTER", "CENTRAL_HISTORY", "FB_PRESENTED", "DAILY_PRESENTED"}

def https(url):
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname)

def verified_contact(r):
    url = r.get("contact_url")
    if not https(url) or not https(r.get("contact_route_source")):
        return False
    host = urlparse(url).hostname
    if r.get("channel") == "WA":
        return host in {"wa.me", "api.whatsapp.com"} and r.get("route_status") in {"BUSINESS_ROUTE_VERIFIED", "FOUNDER_DIRECT_VERIFIED"}
    if r.get("channel") == "TG":
        return bool(re.fullmatch(r"https://t\.me/[A-Za-z][A-Za-z0-9_]{4,31}/?", url)) and r.get("route_status") in {"BUSINESS_ROUTE_VERIFIED", "FOUNDER_DIRECT_VERIFIED"}
    if r.get("channel") == "FB":
        return host in {"facebook.com", "www.facebook.com", "m.facebook.com", "messenger.com"} and r.get("fb_route_type") == "VERIFIED_PERSON_BUSINESS_DM" and r.get("route_status") == "FB_DIRECT_BUSINESS_VERIFIED"
    return False

def recent_day(s, now):
    try:
        return 0 <= (now - date.fromisoformat(s[:10])).days <= 30
    except (ValueError, TypeError):
        return False

def validate(items, as_of=None):
    if not isinstance(items, list):
        raise ValueError("expected JSON array")
    today = as_of or date.today()
    keys = set()
    columns = ["discovered", "icp_pass", "asset_ready", "send_ready"]
    totals = {ch: {s: 0 for s in columns} for ch in TARGETS}
    retail = {v: {s: 0 for s in columns} for v in RETAIL_TARGETS}
    issues = []
    backup_fb = 0
    for i, r in enumerate(items):
        if not isinstance(r, dict):
            issues.append({"id": i, "icp": ["invalid record"], "asset": [], "send": []})
            continue
        ch, seg, vertical = r.get("channel"), r.get("segment"), r.get("retail_vertical")
        backup = r.get("slot") == "BACKUP"
        if backup:
            if ch == "FB":
                backup_fb += 1
            else:
                issues.append({"id": r.get("id", i), "icp": ["backup only allowed for FB"], "asset": [], "send": []})
                continue
        elif ch in totals:
            totals[ch]["discovered"] += 1
        if not backup and seg == "REGULATED_RETAIL_TEST" and vertical in retail:
            retail[vertical]["discovered"] += 1
        icp, asset, send = [], [], []
        domain = (r.get("canonical_domain") or "").strip().lower().removeprefix("www.")
        if not domain or domain in keys:
            icp.append("duplicate or missing company domain")
        if domain:
            keys.add(domain)
        if ch not in TARGETS:
            icp.append("invalid channel")
        if not r.get("company") or not https(r.get("website")) or r.get("identity_status") != "VERIFIED" or r.get("non_chain") is not True:
            icp.append("company identity/website/non-chain unverified")
        if not https(r.get("discovery_source")) or urlparse(r.get("discovery_source") or "").hostname == urlparse(r.get("website") or "").hostname:
            icp.append("independent discovery evidence not recorded")
        if not r.get("buyer_problem") or not r.get("buyer_job") or r.get("external_purchase_fit") != "EVIDENCED":
            icp.append("buyer problem or GEO purchase fit unverified")
        if not https(r.get("recent_activity_source")) or not recent_day(r.get("recent_activity_at"), today):
            icp.append("last 30 days activity not verified")
        if seg == "CORE_B2B":
            size = r.get("team_size")
            if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 50:
                icp.append("core team size unverified or over 50")
        elif seg == "REGULATED_RETAIL_TEST":
            if vertical not in RETAIL_TARGETS or ch != "WA" or r.get("independent_store") is not True:
                icp.append("invalid retail vertical/channel/independence")
        else:
            icp.append("invalid segment")
        if r.get("history_status") != "NO_MATCH_IN_CHECKED_SOURCES" or not REQUIRED_HISTORY.issubset(set(r.get("checked_sources") or [])):
            icp.append("Drive history coverage not complete")
        if r.get("presented_before") is not False or r.get("opted_out") is not False:
            icp.append("previously presented, opted out or unknown")
        asset_urls = ["evidence_url", "raw_capture_url", "image_url", "source_manifest_url"]
        if not all(https(r.get(f)) for f in asset_urls):
            asset.append("source/raw/PNG/manifest links absent")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", r.get("image_sha256") or ""):
            asset.append("PNG SHA-256 missing")
        if r.get("evidence_type") not in {"onsite_observation", "search_sample", "ai_answer_test"}:
            asset.append("evidence type invalid")
        if r.get("image_status") != "VERIFIED_PNG_RAW" or r.get("pairing_status") != "PASS":
            asset.append("PNG and original ID pairing QA not passed")
        if not r.get("message") or r.get("message_status") != "PASS":
            asset.append("message QA incomplete")
        if r.get("ai_gap_claimed") and (r.get("evidence_type") != "ai_answer_test" or not https(r.get("raw_ai_answer_url"))):
            asset.append("AI recommendation claim has no real raw answer")
        if not verified_contact(r) or r.get("recipient_status") not in {"BUSINESS_RECIPIENT_VERIFIED", "FOUNDER_VERIFIED"}:
            send.append("appropriate business contact not verified")
        if r.get("human_review_status") != "PASS" or r.get("contact_policy_status") != "PASS":
            send.append("human/channel policy QA missing")
        if seg == "REGULATED_RETAIL_TEST" and r.get("regulatory_compliance_status") != "PASS":
            send.append("regulated research only, compliance not approved")
        if r.get("send_status") != "NOT_SENT":
            send.append("not a new unsent lead")
        flags = {"icp_pass": not icp, "asset_ready": not asset, "send_ready": not icp and not asset and not send}
        if not backup:
            for flag, ok in flags.items():
                if ok and ch in totals:
                    totals[ch][flag] += 1
                if ok and seg == "REGULATED_RETAIL_TEST" and vertical in retail:
                    retail[vertical][flag] += 1
        if icp or asset or send:
            issues.append({"id": r.get("original_prospect_id", r.get("id", i)), "icp": icp, "asset": asset, "send": send, **flags})
    shortfall = {ch: max(0, target - totals[ch]["send_ready"]) for ch, target in TARGETS.items()}
    return {"targets": TARGETS, "retail_research_targets": RETAIL_TARGETS, "counts": totals, "retail": retail, "fb_backup_count": backup_fb, "fb_backup_limit_exceeded": backup_fb > 10, "shortfall_send_ready": shortfall, "issues": issues, "warning": "A PASS string or valid URL does not establish that an actual screenshot, human recipient, legal permission or historical readback was verified."}

def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/validate_daily_evidence.py batch.json", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        report = validate(json.load(f))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not any(report["shortfall_send_ready"].values()) and not report["fb_backup_limit_exceeded"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
