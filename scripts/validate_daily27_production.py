#!/usr/bin/env python3
"""Production-only validator; legacy PR #11 validator remains untouched."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs
TARGETS = {"WA":15, "TG":2, "FB":10}
REQUIRED_HISTORY = {"103_MASTER", "112_MASTER", "CENTRAL_HISTORY", "FB_PRESENTED", "DAILY_PRESENTED"}

def https(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname)

def is_valid_wa_url(url: str) -> bool:
    if not https(url):
        return False
    p = urlparse(url)
    host = (p.hostname or "").casefold()
    if host not in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
        return False
    if "wa.me/message/" in url.casefold():
        return True
    raw = parse_qs(p.query).get("phone", [p.path.strip("/")])[0]
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7 or set(digits) == {"0"} or digits.endswith("0000000000"):
        return False
    return True


def is_valid_tg_url(url: str, reject_bots: bool = True) -> bool:
    if not https(url):
        return False
    if not re.fullmatch(r"https://(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})/?", url):
        return False
    handle = url.rstrip("/").split("/")[-1].casefold()
    if reject_bots and (handle.endswith("_bot") or handle.endswith("bot")):
        return False
    return True



def validate_production_pack(report: dict[str, Any], check_png_files: bool = True) -> dict[str, Any]:
    """Strict production validator for Daily 27 pipeline output (Requirements 1-12)."""
    errors: list[str] = []
    warnings: list[str] = []

    if report.get("auto_send_enabled") is not False:
        errors.append("auto_send_enabled must be strictly False")

    if report.get("target_total") != 27:
        errors.append(f"target_total must be 27, got {report.get('target_total')}")

    targets = report.get("targets_by_channel", {})
    for ch, expected in TARGETS.items():
        if targets.get(ch) != expected:
            errors.append(f"targets_by_channel[{ch}] must be {expected}, got {targets.get(ch)}")

    # Verify four required funnel metrics exist
    fm = report.get("funnel_metrics", {})
    for req_metric in ("research_completed", "image_completed", "contact_qualified", "strict_send_ready"):
        if req_metric not in fm:
            errors.append(f"Missing required funnel metric: {req_metric}")

    primary_records = report.get("primary_slot_records", [])
    retail_records = report.get("regulated_retail_research_records", [])
    partner_records = report.get("partner_candidate_records", [])

    seen_ids: set[str] = set()
    seen_domains: set[str] = set()

    for idx, rec in enumerate(primary_records):
        pid = rec.get("original_prospect_id")
        cname = rec.get("company_name")
        dom = (rec.get("canonical_domain") or "").casefold()
        ch = rec.get("channel")
        label = f"primary[{idx}]({pid or cname})"

        if not pid:
            errors.append(f"{label}: missing original_prospect_id")
        elif pid in seen_ids:
            errors.append(f"{label}: duplicate original_prospect_id {pid}")
        else:
            seen_ids.add(pid)

        if not dom or not https(rec.get("official_url")):
            errors.append(f"{label}: missing canonical_domain or official_url")
        elif dom in seen_domains:
            errors.append(f"{label}: company domain {dom} occupies more than 1 primary seat")
        else:
            seen_domains.add(dom)

        if not https(rec.get("discovery_source_url")):
            errors.append(f"{label}: missing HTTPS independent discovery_source_url")

        # Retail research and GEO/SEO partners must never be in primary sendable seats
        if rec.get("is_retail_research") or rec.get("segment") == "REGULATED_RETAIL_RESEARCH":
            errors.append(f"{label}: regulated retail RESEARCH_ONLY record cannot occupy a primary B2B seat")
        if rec.get("segment") == "PARTNER_CANDIDATE":
            errors.append(f"{label}: GEO/SEO peer PARTNER_CANDIDATE cannot occupy a primary B2B buyer seat")

        # Exclusion checks
        excl = rec.get("exclusion_checks", {})
        for req_hist in REQUIRED_HISTORY:
            if not excl.get(req_hist):
                errors.append(f"{label}: missing historical dedupe check {req_hist}")

        # Strict channel route checks
        curl = rec.get("contact_url", "")
        if ch == "TG" and curl:
            if not is_valid_tg_url(curl, reject_bots=True):
                errors.append(f"{label}: invalid or Bot Telegram URL {curl}")
        if ch == "WA" and curl:
            if not is_valid_wa_url(curl):
                errors.append(f"{label}: invalid or placeholder WhatsApp URL {curl}")

        # Image & SHA256 pairing check
        if rec.get("image_completed"):
            png_path = rec.get("png_path", "")
            png_sha = rec.get("png_sha256", "")
            dims = rec.get("png_dimensions", "")
            if dims != "1080x1350":
                errors.append(f"{label}: PNG dimensions must be 1080x1350, got {dims}")
            if not png_sha or len(png_sha) != 64:
                errors.append(f"{label}: invalid or missing png_sha256")
            if check_png_files and png_path:
                p = Path(png_path)
                if not p.exists():
                    errors.append(f"{label}: PNG file does not exist at {png_path}")
                else:
                    actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                    if actual_sha != png_sha:
                        errors.append(f"{label}: PNG sha256 mismatch (expected {png_sha}, got {actual_sha})")

        # Evidence vs AI test honesty gate (Requirement 8)
        ai_test = rec.get("ai_test") or {}
        card_type = rec.get("evidence_card_type")
        if card_type == "AI_LIVE_TEST_CARD":
            if not (
                ai_test.get("tested")
                and ai_test.get("platform")
                and ai_test.get("tested_at_utc")
                and ai_test.get("exact_prompt")
                and ai_test.get("verbatim_answer")
                and ai_test.get("raw_screenshot_path")
            ):
                errors.append(f"{label}: AI_LIVE_TEST_CARD missing required prompt/model/time/answer/screenshot")

        # Send-ready strict gate (Requirement 8 & 10)
        if rec.get("send_ready"):
            if not rec.get("contact_qualified") or not rec.get("recipient_verified"):
                errors.append(f"{label}: marked send_ready=True without verified contact & human recipient")
            if rec.get("outreach_qa_status") != "PASS" or not rec.get("first_contact_draft"):
                errors.append(f"{label}: marked send_ready=True without outreach_qa_status==PASS")
            if not rec.get("image_completed"):
                errors.append(f"{label}: marked send_ready=True without completed 1080x1350 PNG")
            if card_type == "STUDY_FACT_CARD":
                errors.append(f"{label}: STUDY_FACT_CARD (untested AI) cannot be marked strict send_ready=True")
            if ch == "FB" and rec.get("fb_route_type") == "COMPANY_PAGE":
                errors.append(f"{label}: Facebook COMPANY_PAGE cannot be marked send_ready=True")

    # Check regulated retail records are strictly RESEARCH_ONLY and not send_ready
    for idx, r in enumerate(retail_records):
        if r.get("send_ready") or r.get("auto_send_enabled"):
            errors.append(f"retail[{idx}]: regulated retail experiment cannot be send_ready or auto_send_enabled")
        if r.get("stage") != "RESEARCH_ONLY":
            errors.append(f"retail[{idx}]: regulated retail stage must be RESEARCH_ONLY, got {r.get('stage')}")

    # Record shortfalls as transparent warnings (not hidden or faked)
    shortfalls = fm.get("by_channel_shortfall_for_verified_route", {})
    for ch, gap in shortfalls.items():
        if gap > 0:
            warnings.append(f"Channel {ch} has a verified-route shortfall of {gap} against target {TARGETS[ch]}")

    return {
        "structural_and_integrity_valid": len(errors) == 0,
        "quota_fully_met_27_send_ready": fm.get("strict_send_ready", 0) == 27,
        "errors": errors,
        "warnings": warnings,
        "funnel_metrics": fm,
    }



