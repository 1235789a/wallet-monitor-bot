"""Resolve a company website only from explicit links in its existing RAW provenance."""

from __future__ import annotations

import html
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from pathlib import Path

from .contact_enrichment import fetch_html, robots_allows
from .source_pool import canonical_domain, public_http_url


SEARCH_HOSTS = {"google.com", "bing.com", "yahoo.com", "duckduckgo.com", "search.brave.com"}
SEARCH_ENGINE_BRANDS = {"google", "bing", "yahoo", "duckduckgo"}
NON_WEBSITE_HOSTS = {
    "linktr.ee", "beacons.ai", "bio.site", "linkin.bio", "taplink.cc",
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "wikipedia.org",
}
WEBSITE_LABEL = re.compile(
    r"\b(website|visit\s+(?:our\s+)?website|official\s+site|visit\s+site|"
    r"site\s+oficial|visite\s+(?:nosso\s+)?site|visitar\s+(?:o\s+)?site|"
    r"website|sítio|site|página oficial|pagina oficial|sitio web|web oficial)\b", re.I,
)
SOURCE_FIELDS = ("discovery_source_url", "profile_url", "source_record_url",
                 "directory_company_url", "directory_url", "source_page_url")
PROFILE_FIELDS = ("profile_url", "directory_company_url")
SOURCE_WEBSITE_FIELDS = ("website_url", "website", "official_website", "official_site",
                         "company_website", "company_url", "homepage")
WEBSITE_FIELD_SOURCE_FIELDS = ("website_source_url", "source_record_url", "discovery_source_url",
                               "source_page_url", "source_dataset_url", "directory_company_url",
                               "directory_url", "profile_url")
REDIRECT_KEYS = ("url", "u", "target", "website", "site", "redirect")


def _host(url: str) -> str:
    return canonical_domain(url)


def _search_host(host: str) -> bool:
    labels = host.split(".")
    return (any(host == domain or host.endswith("." + domain) for domain in SEARCH_HOSTS)
            or any(label in SEARCH_ENGINE_BRANDS for label in labels))


class _OutboundLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href = ""
        self.anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            values = dict(attrs)
            self.href = str(values.get("href") or "").strip()
            self.anchor = [str(values.get("aria-label") or ""), str(values.get("title") or "")]

    def handle_data(self, data: str) -> None:
        if self.href:
            self.anchor.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.anchor)))
            self.href, self.anchor = "", []


def _company_link(source_url: str, href: str, label: str) -> str:
    target = urljoin(source_url, html.unescape(href.strip()))
    parsed = urlsplit(target)
    label = html.unescape(label or "").strip()
    # Some curated partner/directories label the official outbound link only
    # with the visible domain. Accept that label only when it matches the href.
    label_host = ""
    if re.fullmatch(r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?", label):
        label_host = _host(label if urlsplit(label).scheme else "https://" + label)
    explicit_website_anchor = bool(WEBSITE_LABEL.search(label)) or bool(
        label_host and label_host == _host(target))
    if not explicit_website_anchor:
        return ""
    if _search_host(_host(target)):
        return ""
    query = parse_qs(parsed.query)
    for key in REDIRECT_KEYS:
        for value in query.get(key, []):
            decoded = unquote(value)
            if public_http_url(decoded) and not _search_host(_host(decoded)):
                target = decoded
                break
        if target != urljoin(source_url, html.unescape(href.strip())):
            break
    if not public_http_url(target):
        return ""
    host = _host(target)
    if not host or _search_host(host) or any(host == d or host.endswith("." + d) for d in NON_WEBSITE_HOSTS):
        return ""
    if host == _host(source_url):
        return ""
    return target.split("#", 1)[0]


def _company_name_matches(name: str, label: str, target: str) -> bool:
    expected = re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold()).strip()
    observed = re.sub(r"[^a-z0-9]+", " ", f"{label} {urlsplit(target).hostname or ''}".casefold()).strip()
    tokens = [token for token in expected.split() if len(token) > 2]
    return bool(tokens and sum(token in observed for token in tokens) >= len(tokens))


def resolve_website(
    row: dict[str, Any], *,
    fetcher: Callable[[str], tuple[str, str]] = fetch_html,
    respect_robots: bool = True,
) -> dict[str, Any]:
    """Use only explicit outbound links on URLs already present in this RAW row."""
    result = dict(row)
    if public_http_url(str(row.get("website_url") or "")):
        if result.get("website_resolution_status") not in {"resolved", "already_present"}:
            result["website_resolution_status"] = "already_present"
        if not result.get("website_discovery_method"):
            direct_sources = (row.get("raw_source_record") or {}, row.get("source_tags") or {})
            direct_match = any(str(source.get(field) or "").strip() == str(row.get("website_url") or "").strip()
                               for source in direct_sources if isinstance(source, dict)
                               for field in SOURCE_WEBSITE_FIELDS)
            result["website_discovery_method"] = "source_record_website_field" if direct_match else "raw_website_field"
        if not result.get("website_source_url"):
            result["website_source_url"] = next((str(row.get(field) or "").strip()
                for field in WEBSITE_FIELD_SOURCE_FIELDS
                if public_http_url(str(row.get(field) or "").strip())), "")
        result.setdefault("website_resolved_at", datetime.now(UTC).isoformat(timespec="seconds"))
        return result

    # A website field copied directly from the already captured source record
    # is first-party provenance; it needs no search or source-page request.
    raw_record = row.get("raw_source_record") if isinstance(row.get("raw_source_record"), dict) else {}
    properties = raw_record.get("properties") if isinstance(raw_record.get("properties"), dict) else {}
    raw_tags = raw_record.get("tags") if isinstance(raw_record.get("tags"), dict) else {}
    property_tags = properties.get("tags") if isinstance(properties.get("tags"), dict) else {}
    source_tags = row.get("source_tags") if isinstance(row.get("source_tags"), dict) else {}
    for source_record in (row, source_tags, raw_record, raw_tags, properties, property_tags):
        for field in SOURCE_WEBSITE_FIELDS:
            candidate = str(source_record.get(field) or "").strip()
            if not public_http_url(candidate) or _search_host(_host(candidate)):
                continue
            candidate_host = _host(candidate)
            if any(candidate_host == d or candidate_host.endswith("." + d) for d in NON_WEBSITE_HOSTS):
                continue
            source_url = next((str(row.get(name) or "").strip() for name in WEBSITE_FIELD_SOURCE_FIELDS
                               if public_http_url(str(row.get(name) or "").strip())), "")
            result.update(website_url=candidate, website_discovery_method="source_record_website_field",
                          website_source_url=source_url, website_resolution_status="resolved",
                          website_resolved_at=datetime.now(UTC).isoformat(timespec="seconds"),
                          website_inferred=False)
            return result

    seen: set[str] = set()
    errors: list[dict[str, str]] = []
    sources: list[str] = []
    profile_sources: set[str] = set()
    for field in SOURCE_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and public_http_url(value.strip()) and value.strip() not in sources:
            sources.append(value.strip())
            if field in PROFILE_FIELDS:
                profile_sources.add(value.strip())
    record_url = str(row.get("source_record_url") or "").strip()
    dataset_url = str(row.get("source_dataset_url") or "").strip()
    if record_url and record_url != dataset_url and public_http_url(record_url):
        profile_sources.add(record_url)
    discovery_url = str(row.get("discovery_source_url") or "").strip()
    if discovery_url and discovery_url == record_url:
        profile_sources.add(discovery_url)
    if isinstance(row.get("raw_source_record"), dict):
        for key in SOURCE_FIELDS:
            value = row["raw_source_record"].get(key)
            if isinstance(value, str) and public_http_url(value.strip()) and value.strip() not in sources:
                sources.append(value.strip())
                if key in PROFILE_FIELDS:
                    profile_sources.add(value.strip())

    sources.sort(key=lambda value: (0 if value in profile_sources else 1, len(value)))

    resolved = ""
    resolved_from = ""
    for source_url in sources:
        if source_url in seen or _search_host(_host(source_url)):
            continue
        seen.add(source_url)
        if respect_robots and not robots_allows(source_url):
            errors.append({"source_url": source_url, "error": "robots_disallowed"})
            continue
        try:
            body, final_url = fetcher(source_url)
            # Never accept a source-page redirect into a search engine or a
            # different host that was not present in the RAW provenance.
            if (not public_http_url(final_url) or _search_host(_host(final_url))
                    or _host(final_url) != _host(source_url)):
                continue
            parser = _OutboundLinks()
            parser.feed(body)
            for href, label in parser.links:
                candidate = _company_link(final_url, href, label)
                if candidate and (source_url in profile_sources
                                  or _company_name_matches(str(row.get("company_name") or ""), label, candidate)):
                    resolved, resolved_from = candidate, final_url
                    break
            if resolved:
                break
        except Exception as exc:  # source page failures are unknown, not proof of absence
            errors.append({"source_url": source_url, "error": str(exc)})

    if resolved:
        result.update(website_url=resolved,
                      website_discovery_method="directory_outbound_link",
                      website_source_url=resolved_from,
                      website_resolution_status="resolved",
                      website_resolved_at=datetime.now(UTC).isoformat(timespec="seconds"),
                      website_inferred=False)
    else:
        result.update(website_resolution_status="unresolved",
                      website_absence_status="unknown",
                      website_resolution_errors=errors,
                      website_inferred=False)
    return result


def _resolution_key(row: dict[str, Any]) -> str:
    values = [str(row.get(field) or "") for field in (
        "source_id", "identity_key", "company_name", "discovery_source_url", "profile_url",
        "source_record_url", "directory_company_url", "directory_url", "source_page_url",
        "website_url",
    )]
    if isinstance(row.get("raw_source_record"), dict):
        values.append(json.dumps(row["raw_source_record"], sort_keys=True, ensure_ascii=False))
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def resolve_website_pool(rows: list[dict[str, Any]], *, cache_path: Path,
                         resolver_fn: Callable[[dict[str, Any]], dict[str, Any]] = resolve_website,
                         workers: int = 12) -> list[dict[str, Any]]:
    """Resolve missing websites incrementally and persist successes/failures.

    Existing website records are annotated locally; only uncached RAW source
    pages are fetched. Cached unresolved records remain unresolved until an
    explicit new run requests their retry.
    """
    cache_path = Path(cache_path)
    cache: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            cache[entry["key"]] = entry["row"]
    keyed = [(_resolution_key(row), row) for row in rows]
    pending: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    for key, row in keyed:
        if public_http_url(str(row.get("website_url") or "")):
            results[key] = resolver_fn(row)
        elif key in cache:
            # Reuse the previous URL-resolution result without losing metadata
            # added to the current RAW row (source name, country, vertical,
            # and provenance). Cached resolution fields remain authoritative.
            cached_row = cache[key]
            merged = dict(row)
            for field in ("website_url", "website_discovery_method", "website_source_url",
                          "website_resolution_status", "website_resolved_at",
                          "website_absence_status", "website_resolution_errors",
                          "website_inferred"):
                if field in cached_row:
                    merged[field] = cached_row[field]
            results[key] = merged
        else:
            pending.setdefault(key, row)
    if pending:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 24))) as executor:
            futures = {executor.submit(resolver_fn, row): key for key, row in pending.items()}
            with cache_path.open("a", encoding="utf-8") as stream:
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {**pending[key], "website_resolution_status": "unresolved",
                                  "website_absence_status": "unknown",
                                  "website_resolution_errors": [{"error": str(exc)}]}
                    results[key] = result
                    cache[key] = result
                    stream.write(json.dumps({"key": key, "row": result}, ensure_ascii=False) + "\n")
                    stream.flush()
    return [results[key] for key, _ in keyed]
