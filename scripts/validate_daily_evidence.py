#!/usr/bin/env python3
"""Validate source-backed MultiHub daily lead packs; does not scrape or message."""
import json, re, sys
from urllib.parse import urlparse

CHANNELS = {"WA", "TG"}
REQ = (
 "id", "company", "canonical_domain", "channel", "contact_url", "contact_route_source",
 "buyer_job", "observation", "observation_scope", "evidence_url", "captured_at",
 "history_status", "route_status", "recipient_status", "image_url", "raw_capture_url",
 "message", "message_status", "send_status",
)
PROVEN = {"NO_MATCH_IN_CHECKED_SOURCES"}
ROUTE = {"BUSINESS_ROUTE_VERIFIED", "FOUNDER_DIRECT_VERIFIED"}
RECIPIENT = {"BUSINESS_RECIPIENT_VERIFIED", "FOUNDER_VERIFIED"}
TEST_TYPES = {"onsite_observation", "search_sample", "ai_answer_test"}

def http(url):
    return isinstance(url,str) and urlparse(url).scheme=="https" and bool(urlparse(url).netloc)

def validate(items):
    if not isinstance(items,list): raise ValueError("root must be a JSON array")
    seen, valid, issues = set(), [], []
    for i, r in enumerate(items):
        label = r.get("id", "row:"+str(i)) if isinstance(r,dict) else "row:"+str(i)
        problems=[]
        if not isinstance(r,dict):
            issues.append((label,["record must be object"]));continue
        for k in REQ:
            if not r.get(k): problems.append("missing "+k)
        channel=r.get("channel")
        if channel not in CHANNELS: problems.append("invalid channel")
        key=(r.get("canonical_domain") or "").lower().removeprefix("www.").strip()
        if key in seen or not key: problems.append("duplicate/blank domain")
        seen.add(key)
        if r.get("history_status") not in PROVEN: problems.append("history not cleared")
        if r.get("route_status") not in ROUTE: problems.append("route not verified")
        if r.get("recipient_status") not in RECIPIENT: problems.append("recipient not verified")
        if r.get("message_status")!="PASS": problems.append("message QA failed")
        if r.get("send_status")!="NOT_SENT": problems.append("send_status must be NOT_SENT for daily drafts")
        if r.get("evidence_type") not in TEST_TYPES: problems.append("evidence type missing/invalid")
        if channel=="WA" and not (http(r.get("contact_url")) and re.search(r"https://(?:wa\.me/|api\.whatsapp\.com/send)",r["contact_url"])):
            problems.append("WA route must be HTTPS wa.me or api.whatsapp.com")
        if channel=="TG" and not (http(r.get("contact_url")) and re.match(r"https://t\.me/[A-Za-z0-9_]{5,}$",r["contact_url"])):
            problems.append("TG route must be direct HTTPS username")
        for url_key in ["contact_route_source","evidence_url","image_url","raw_capture_url"]:
            if not http(r.get(url_key)): problems.append("invalid "+url_key)
        text=(r.get("message") or "").lower()
        if r.get("ai_gap_claimed") and r.get("evidence_type")!="ai_answer_test":
            problems.append("AI gap claimed without real test")
        if r.get("image_status")!="VERIFIED_PNG_RAW": problems.append("image + raw not verified")
        if not r.get("checked_sources"): problems.append("no recorded dedupe coverage")
        if r.get("history_status")=="NO_MATCH_IN_CHECKED_SOURCES" and not r.get("checked_sources"): problems.append("dedupe coverage absent")
        if problems: issues.append((label,problems))
        else: valid.append(r)
    counts={c:sum(r.get("channel")==c for r in valid) for c in CHANNELS}
    return {"accepted":len(valid),"counts":counts,"targets":{"WA":12,"TG":2},
            "shortfall":{"WA":max(0,12-counts["WA"]),"TG":max(0,2-counts["TG"])},
            "rejected":len(issues),"issues":[{"id":k,"reasons":v} for k,v in issues]}

def main():
    if len(sys.argv)!=2: print("usage: validate_daily_evidence.py daily_batch.json",file=sys.stderr);return 2
    with open(sys.argv[1],encoding="utf-8") as f: obj=json.load(f)
    result=validate(obj)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if not result["shortfall"]["WA"] and not result["shortfall"]["TG"] and not result["rejected"] else 1

if __name__=="__main__": raise SystemExit(main())
