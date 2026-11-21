"""Preflight an authorized FB public evidence source BEFORE company research.

This is a source capability check, not an ICP or send gate. It does no login,
scraping, messaging or source discovery; the runner supplies actual observations.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .daily27_models import ActivityProof
from .fb_activity_gate import FB_HOSTS, check_activity_proof

MIN_PROBES = 10
MIN_VERIFIED = 2


def _profile_key(value: str) -> str:
    try:
        u = urlparse(value)
        if u.scheme != "https" or u.hostname not in FB_HOSTS:
            return ""
        path = u.path.strip("/").casefold()
        if path == "profile.php":
            return parse_qs(u.query).get("id", [""])[0]
        if not path or "/" in path or path in {
            "groups", "pages", "posts", "reel", "reels", "watch", "share",
            "login", "marketplace", "search", "events", "people", "home.php",
        }:
            return ""
        return path
    except (TypeError, ValueError):
        return ""


def probe_source(rows: list[dict], *, as_of: date) -> dict:
    """Count only independently identified, actual reviewed personal posts.

    Unique probe IDs are mandatory. A verified result only permits further
    research. No candidate becomes READY, and the existing dual-proof gate
    remains authoritative.
    """
    seen: set[str] = set()
    verified_profiles: set[str] = set()
    output = []
    for row in rows:
        pid = row.get("probe_id")
        if not isinstance(pid, str) or not pid.strip() or pid in seen:
            raise ValueError("probe_id must be nonempty and unique")
        seen.add(pid)
        profile = _profile_key(row.get("profile_url") or "")
        issues = []
        if not profile:
            issues.append("PROFILE_NOT_VERIFIED")
        source = urlparse(str(row.get("identity_source_url") or ""))
        if source.scheme != "https" or not source.hostname or source.hostname in FB_HOSTS:
            issues.append("INDEPENDENT_IDENTITY_SOURCE_MISSING")
        if not row.get("decision_maker_confirmed") is True:
            issues.append("DECISION_MAKER_UNCONFIRMED")
        if row.get("access_status") != "PUBLIC_CONTENT_OBSERVED":
            issues.append("PUBLIC_CONTENT_NOT_OBSERVED")
        try:
            proof = ActivityProof(**(row.get("fb_activity_proof") or {}))
            issues.extend(check_activity_proof(proof, as_of=as_of, kind="FB_POST"))
        except (TypeError, ValueError):
            issues.append("INVALID_ACTIVITY_PROOF")
        if profile in verified_profiles:
            issues.append("DUPLICATE_PERSON")
        if not issues:
            verified_profiles.add(profile)
        output.append({"probe_id": pid, "status": "VERIFIED_PROBE" if not issues else "HOLD",
                       "issues": issues})
    n = len(seen)
    passed = len(verified_profiles)
    if passed >= MIN_VERIFIED:
        verdict = "CONTINUE_RESEARCH"
    elif n >= MIN_PROBES:
        verdict = "SWITCH_SOURCE_OR_HOLD"
    else:
        verdict = "CONTINUE_PROBING"
    return {"verdict": verdict, "probes": n, "verified_unique_people": passed,
            "ready": 0, "verified_probe_ids": [r["probe_id"] for r in output
                                               if r["status"] == "VERIFIED_PROBE"],
            "rows": output,
            "note": "Source capability only; existing ICP, history, dual-proof, and send gates remain mandatory."}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = ap.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("probes"), list):
        raise ValueError("manifest requires a probes array")
    print(json.dumps(probe_source(data["probes"], as_of=args.as_of), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
