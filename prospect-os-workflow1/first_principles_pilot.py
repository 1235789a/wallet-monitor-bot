"""Read-only 10 WhatsApp + 2 Telegram pilot for Growth Engine v2.1.

Run after gathering independently sourced real companies and supplying the
v2.1 evidence contract. Never sends outreach or changes source records.
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

TARGETS = {"whatsapp": 10, "telegram": 2}


def route(url):
    """Clickable official route, not a promise of reachable human or buyer intent."""
    p = urlsplit(str(url or ""))
    host = (p.hostname or "").lower()
    path = p.path.strip("/")
    if p.scheme != "https":
        return None
    if host == "wa.me" and (re.fullmatch(r"[1-9][0-9]{7,14}", path)
                            or re.fullmatch(r"message/[A-Za-z0-9]+", path)):
        return "whatsapp"
    if host == "api.whatsapp.com" and p.path.rstrip("/") == "/send":
        phone = parse_qs(p.query).get("phone", [""])[0]
        if re.fullmatch(r"[1-9][0-9]{7,14}", phone):
            return "whatsapp"
    if host in {"t.me", "telegram.me"} and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", path):
        if not path.lower().endswith("bot"):
            return "telegram"
    return None


def host(url):
    return (urlsplit(str(url or "")).hostname or "").lower().removeprefix("www.")


def pilot_report(audited):
    """v2.1 auditor's READY is authoritative; route candidates are not READY."""
    counted = Counter()
    chosen = []
    review = []
    seen = set()
    for row in audited.get("rows", []):
        channel = route(row.get("chat_url"))
        company = (row.get("company") or "").strip()
        official = row.get("website")
        source = row.get("source") or {}
        source_url = source.get("url", "")
        # A directory/source is independent of the company's own website.
        origin_ok = (host(source_url) and host(official) and
                     host(source_url) != host(official))
        # Caller must provide the exact official page where the link was seen.
        official_page = (row.get("contact") or {}).get("official_page", "")
        link_ok = bool(host(official_page) and host(official_page) == host(official) and channel)
        # Deduplicate by website, normalized name AND stable public chat identity.
        # Opaque WhatsApp message links may lack a phone: keep other keys.
        chat = urlsplit(str(row.get("chat_url") or ""))
        chatpath = chat.path.strip("/").lstrip("+")
        keys = {("domain", host(official)), ("name", company.casefold())}
        if channel == "whatsapp":
            number = chatpath if re.fullmatch(r"[1-9][0-9]{7,14}", chatpath) else parse_qs(chat.query).get("phone", [""])[0]
            if re.fullmatch(r"[1-9][0-9]{7,14}", number):
                keys.add(("whatsapp", number))
        if channel == "telegram":
            keys.add(("telegram", chatpath.casefold()))
        keys.discard(("domain", ""))
        keys.discard(("name", ""))
        if not keys or seen.intersection(keys):
            review.append({"company": company, "state": "DUPLICATE_OR_MISSING_ID"})
            continue
        seen.update(keys)
        if not origin_ok or not link_ok:
            review.append({"company": company, "state": "SOURCE_OR_ROUTE_HOLD"})
            continue
        stage = row.get("stage", "UNKNOWN")
        if stage != "READY_FOR_MANUAL_OUTREACH":
            reason = row.get("gate_reasons", [])
            review.append({"company": company, "channel": channel, "link": row.get("chat_url"),
                           "source_url": source_url, "official_page": official_page,
                           "state": "EVIDENCE_HOLD", "reasons": reason})
            continue
        if counted[channel] >= TARGETS[channel]:
            review.append({"company": company, "state": "QUOTA_OVERFLOW"})
            continue
        chosen.append({"company": company, "channel": channel,
                       "link": row.get("chat_url"), "source_url": source_url})
        counted[channel] += 1
    return {"target": TARGETS, "ready_count": dict(counted),
            "gaps": {k: v - counted[k] for k, v in TARGETS.items()},
            "ready": chosen, "review": review,
            "note": "No messages sent. Public chat URL does not prove purchase fit."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="private v2.1 payload JSON")
    parser.add_argument("output", help="new immutable private results JSON")
    args = parser.parse_args()
    source, destination = Path(args.input).resolve(), Path(args.output).resolve()
    if source == destination or destination.exists():
        raise SystemExit("Refusing to replace inputs or an existing run")
    from prospect_os.growth_engine_v21 import audit_run
    audited = audit_run(json.loads(source.read_text(encoding="utf-8")))
    result = pilot_report(audited)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ready": result["ready_count"], "gaps": result["gaps"]}))


if __name__ == "__main__":
    main()
