"""Conservative, date-checked cross-platform activity evidence gate for Facebook prospects (no scraping/login).

The verifier checks that a researcher preserved a dated public post, accurate local
capture bytes, and a recent recorded review. It cannot independently determine
the truth of source page pixels, author identity, or Messenger availability.
Those require authorized manual/public-source review; missing proof is HOLD.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .daily27_models import ActivityProof, CandidateRecord

MAX_ACTIVITY_DAYS = 30
MAX_EVIDENCE_REVIEW_DAYS = 3
ALLOWED_CAPTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FB_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"}


def _parse_date(value: str) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_checked_at(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() != timedelta(0):
            return None
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _fb_post_permalink(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in FB_HOSTS:
        return False
    path = parsed.path.rstrip("/").lower()
    query = parse_qs(parsed.query)
    if path in {"/story.php", "/permalink.php"}:
        return bool(query.get("story_fbid") and (query.get("id") or path == "/story.php"))
    if path in {"/photo.php", "/photo"}:
        return bool(query.get("fbid"))
    if re.fullmatch(r"/(?:[^/]+/)?(?:posts|videos|reel|reels)/[0-9a-z_-]+", path):
        return True
    if re.fullmatch(r"/share/(?:p|r|v)/[0-9a-z_-]+", path):
        return True
    return False


def _personal_post_platform(url: str) -> str:
    """Allow exact public post permalinks, never profiles, feeds or search pages."""
    if _fb_post_permalink(url):
        return "FB"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return ""
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}:
        if re.fullmatch(r"/[A-Za-z0-9_]{1,15}/status/[0-9]+", path):
            return "X"
    if host in {"linkedin.com", "www.linkedin.com"}:
        if re.fullmatch(r"/posts/[^/]+[-_]activity-[0-9]+(?:-[A-Za-z0-9_-]+)?", path) or re.fullmatch(r"/feed/update/urn:li:(?:activity|share|ugcPost):[0-9]+", path):
            return "LINKEDIN"
    if host in {"instagram.com", "www.instagram.com"}:
        if re.fullmatch(r"/(?:p|reel)/[A-Za-z0-9_-]+", path):
            return "INSTAGRAM"
    return ""


def _specific_business_source(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host in {"google.com", "www.google.com", "bing.com"}:
        return False
    if host in FB_HOSTS:
        return _fb_post_permalink(url)
    # Reject an evergreen homepage, top-level news/blog index, and query-only search.
    path = parsed.path.rstrip("/")
    if path.lower() in {"", "/", "/blog", "/news", "/updates", "/about", "/team"}:
        return False
    return len(path.strip("/")) >= 8


def _capture_matches(proof: ActivityProof) -> bool:
    path = Path(proof.capture_path)
    if (not proof.capture_path or path.suffix.lower() not in ALLOWED_CAPTURE_SUFFIXES
            or not SHA256_RE.fullmatch(proof.capture_sha256 or "")):
        return False
    try:
        if not path.is_file() or path.is_symlink() or not 100 <= path.stat().st_size <= 20_000_000:
            return False
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest.casefold() == proof.capture_sha256.casefold()
    except (OSError, ValueError):
        return False


def check_activity_proof(proof: ActivityProof, *, as_of: date, kind: str,
                         max_activity_days: int = MAX_ACTIVITY_DAYS, require_capture: bool = True) -> list[str]:
    """Return precise HOLD codes; never trust a legacy PASS/VERIFIED label."""
    code = "FB_POST" if kind == "FB_POST" else "BUSINESS"
    prefix = f"HOLD_{code}_ACTIVITY"
    issues: list[str] = []
    published = _parse_date(proof.activity_date)
    checked = _parse_checked_at(proof.checked_at_utc)
    if not published:
        issues.append(f"{prefix}_DATE_MISSING_OR_INVALID")
    else:
        days = (as_of - published).days
        if days < 0:
            issues.append(f"{prefix}_FUTURE_DATE")
        elif days > max_activity_days:
            issues.append(f"{prefix}_STALE_{days}D")
    if not checked:
        issues.append(f"{prefix}_REVIEW_TIME_MISSING_OR_NOT_UTC")
    else:
        # Read-back verification must be recent; older snapshots need re-checking.
        age = (as_of - checked.date()).days
        if age < 0 or age > MAX_EVIDENCE_REVIEW_DAYS or checked > datetime.now(timezone.utc) + timedelta(minutes=5):
            issues.append(f"{prefix}_REVIEW_EXPIRED_OR_FUTURE")
        if published and published > checked.date():
            issues.append(f"{prefix}_POST_NEWER_THAN_REVIEW")
    if not proof.subject_confirmed or proof.subject_type != ("CONTACT_PERSON" if kind == "FB_POST" else "COMPANY"):
        issues.append(f"{prefix}_SUBJECT_UNVERIFIED")
    if not proof.excerpt or len(proof.excerpt.strip()) < 16:
        issues.append(f"{prefix}_EXCERPT_MISSING")
    if not proof.source_url or not (_personal_post_platform(proof.source_url) if kind == "FB_POST" else _specific_business_source(proof.source_url)):
        issues.append(f"{prefix}_NOT_A_SPECIFIC_PUBLIC_POST")
    if (require_capture or proof.capture_path or proof.capture_sha256) and not _capture_matches(proof):
        issues.append(f"{prefix}_ORIGINAL_CAPTURE_MISSING_OR_HASH_MISMATCH")
    return issues


def verify_facebook_activity(rec: CandidateRecord, as_of: date) -> bool:
    """Both business activity AND a dated, attributed personal cross-platform post are needed."""
    rec.fb_activity_verified = False
    issues = check_activity_proof(rec.business_activity_proof, as_of=as_of, kind="BUSINESS")
    issues += check_activity_proof(rec.fb_activity_proof, as_of=as_of, kind="FB_POST")
    if not rec.recipient_verified or rec.fb_route_type != "PERSON":
        issues.append("HOLD_FB_ACTIVITY_NO_VERIFIED_PERSONAL_RECIPIENT")
    if issues:
        rec.recent_30d_activity_status = "HOLD_FB_ACTIVITY_UNVERIFIED"
        for reason in issues:
            if reason not in rec.hold_or_reject_reasons:
                rec.hold_or_reject_reasons.append(reason)
        return False
    platform = _personal_post_platform(rec.fb_activity_proof.source_url)
    rec.recent_30d_activity_status = ("VERIFIED_FB_PUBLIC_POST_WITH_CAPTURE_30D" if platform == "FB"
                                     else f"VERIFIED_{platform}_PERSONAL_POST_WITH_CAPTURE_30D")
    rec.fb_activity_verified = True
    return True


def apply_fb_activity_manifest(records: list[CandidateRecord], path: Path) -> int:
    """Import reviewer-backed facts by immutable original ID, without granting PASS."""
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = obj.get("records") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Facebook activity manifest must have a records list")
    by_id = {r.original_prospect_id: r for r in records}
    seen: set[str] = set()
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Manifest record must be an object")
        pid = row.get("original_prospect_id")
        if not isinstance(pid, str) or pid in seen or pid not in by_id:
            raise ValueError(f"Unknown or duplicate original_prospect_id in FB activity manifest: {pid!r}")
        seen.add(pid)
        rec = by_id[pid]
        if rec.channel != "FB":
            raise ValueError(f"Activity manifest only supports FB candidates: {pid}")
        for field in ("business_activity_proof", "fb_activity_proof"):
            payload = row.get(field)
            if not isinstance(payload, dict):
                raise ValueError(f"Missing {field} for {pid}")
            setattr(rec, field, ActivityProof(**payload))
        # Do not import user-supplied statuses such as PASS or SEND_READY.
        rec.fb_activity_verified = False
        count += 1
    return count
