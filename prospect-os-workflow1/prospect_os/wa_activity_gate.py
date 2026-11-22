"""WhatsApp-only 60-day business activity; no last-seen or private-status gate."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from .daily27_models import ActivityProof, CandidateRecord
from .fb_activity_gate import check_activity_proof, _personal_post_platform

WA_ACTIVITY_DAYS = 60


def verify_wa_activity(rec: CandidateRecord, as_of: date) -> bool:
    issues = check_activity_proof(rec.business_activity_proof, as_of=as_of, kind="BUSINESS",
                                  max_activity_days=WA_ACTIVITY_DAYS, require_capture=False)
    host = (urlsplit(rec.business_activity_proof.source_url).hostname or "").removeprefix("www.").lower()
    if host in {"x.com", "twitter.com", "linkedin.com", "instagram.com"} and not _personal_post_platform(rec.business_activity_proof.source_url):
        issues.append("HOLD_BUSINESS_ACTIVITY_NOT_EXACT_SOCIAL_POST")
    rec.wa_activity_verified = not issues
    rec.wa_activity_status = "VERIFIED_BUSINESS_60D" if not issues else "HOLD_WA_ACTIVITY"
    for issue in issues:
        if issue not in rec.hold_or_reject_reasons:
            rec.hold_or_reject_reasons.append(issue)
    return rec.wa_activity_verified


def apply_wa_activity_manifest(records: list[CandidateRecord], path: Path) -> int:
    """Import dated reviewed company source facts by ID; never import PASS or permissions."""
    rows = json.loads(path.read_text(encoding="utf-8")).get("records")
    if not isinstance(rows, list):
        raise ValueError("WA activity manifest must have a records list")
    by_id = {r.original_prospect_id: r for r in records if r.channel == "WA"}
    seen = set()
    for row in rows:
        pid = row.get("original_prospect_id")
        if pid not in by_id or pid in seen:
            raise ValueError(f"Unknown or duplicate WA prospect ID: {pid!r}")
        seen.add(pid)
        by_id[pid].business_activity_proof = ActivityProof(**row["business_activity_proof"])
        by_id[pid].wa_activity_verified = False
    return len(seen)
