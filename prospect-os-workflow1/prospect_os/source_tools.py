"""Focused public-source extraction for Prospect OS.

The daily runner remains the source of truth for scoring and database writes.
This module adds a conservative, read-only evidence pass: it fetches only the
URLs already supplied by a researcher, extracts main text with Trafilatura,
and records what could (or could not) be verified.  It never turns a failed
fetch into a positive fact and never contacts a prospect.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import trafilatura
except ImportError as exc:  # pragma: no cover - exercised only on a missing optional install
    trafilatura = None  # type: ignore[assignment]
    _TRAFILATURA_IMPORT_ERROR = str(exc)
else:
    _TRAFILATURA_IMPORT_ERROR = ""


USER_AGENT = "ProspectOS-source-audit/1.0 (+read-only evidence check)"
TIMEOUT_SECONDS = 15
MAX_BYTES = 3_000_000


@dataclass
class PageAudit:
    url: str
    status: str
    http_status: int | None
    content_type: str
    title: str
    text_chars: int
    snippet: str
    contains_company_tokens: bool
    contains_contact_token: bool
    error: str = ""


def _tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", value.casefold()) if len(x) >= 4}


def fetch_page(url: str, company_name: str, contact_url: str = "") -> PageAudit:
    if trafilatura is None:
        return PageAudit(
            url=url,
            status="not_installed",
            http_status=None,
            content_type="",
            title="",
            text_chars=0,
            snippet="",
            contains_company_tokens=False,
            contains_contact_token=False,
            error=_TRAFILATURA_IMPORT_ERROR,
        )
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BYTES)
            status_code = getattr(response, "status", None)
            content_type = response.headers.get_content_type() if response.headers else ""
            encoding = response.headers.get_content_charset() if response.headers else None
        html = body.decode(encoding or "utf-8", errors="replace")
        text = trafilatura.extract(html, include_links=True, include_tables=False) or ""
        metadata = trafilatura.extract_metadata(html)
        title = (metadata.title if metadata and metadata.title else "").strip()
        clean_text = re.sub(r"\s+", " ", text).strip()
        company_tokens = _tokens(company_name)
        haystack = f"{title} {clean_text}".casefold()
        return PageAudit(
            url=url,
            status="ok" if clean_text else "empty",
            http_status=status_code,
            content_type=content_type,
            title=title,
            text_chars=len(clean_text),
            snippet=clean_text[:500],
            contains_company_tokens=bool(company_tokens) and sum(token in haystack for token in company_tokens) >= 1,
            contains_contact_token=any(
                token.casefold() in haystack
                for token in (contact_url, "whatsapp", "telegram", "t.me", "wa.me")
                if token
            ),
        )
    except HTTPError as exc:
        return PageAudit(url, "http_error", exc.code, "", "", 0, "", False, False, str(exc))
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return PageAudit(url, "fetch_error", None, "", "", 0, "", False, False, str(exc))


def audit_candidate_rows(rows: list[dict[str, Any]], pause_seconds: float = 0.25) -> dict[str, Any]:
    """Audit only the supplied source URLs; de-duplication stays in workflow1_daily."""
    audited_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pages: list[dict[str, Any]] = []
    for row in rows:
        company = str(row.get("company_name", "")).strip()
        contact_url = str(row.get("contact_clickable_url", "")).strip()
        urls = list(dict.fromkeys(
            [
                str(row.get("website_url", "")).strip(),
                str(row.get("discovery_source_url", "")).strip(),
                str(row.get("contact_source_url", "")).strip(),
            ]
            + [str(x).strip() for x in row.get("source_urls", [])]
        ))
        for url in urls:
            if not url:
                continue
            pages.append(asdict(fetch_page(url, company, contact_url)))
            time.sleep(pause_seconds)
    ok = sum(page["status"] == "ok" for page in pages)
    return {
        "audited_at": audited_at,
        "tool": "trafilatura",
        "read_only": True,
        "pages": pages,
        "summary": {
            "pages": len(pages),
            "ok": ok,
            "failed_or_empty": len(pages) - ok,
            "company_token_matches": sum(page["contains_company_tokens"] for page in pages),
            "contact_token_matches": sum(page["contains_contact_token"] for page in pages),
        },
    }


def audit_json(source_path: Path, output_path: Path) -> dict[str, Any]:
    rows = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("source JSON must be an array")
    result = audit_candidate_rows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

