"""Cheap, source-first contact screening before a new sample is frozen."""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .contact_enrichment import enrich_record, fetch_html
from .sampling import (ADULT_RETAIL, AI_B2B, ALCOHOL_BAR, SECONDARY, VAPE_TOBACCO,
                       WEB3, classify_vertical, eligible_raw_record, sampling_record_key)
from .source_pool import canonical_domain, public_http_url


PEER_AGENCY_PATTERNS = (
    ("seo_geo_aeo_provider", re.compile(r"\b(?:seo|aeo|geo)\s+(?:agency|agencies|consultant|consultancy|services?|optimization|optimisation)\b|\b(?:seo|aeo|geo)\s+(?:and|&)\s+(?:seo|aeo|geo)\b", re.I)),
    ("digital_marketing_agency", re.compile(r"\b(?:digital|content|growth|performance|inbound)\s+marketing\s+(?:agency|agencies|consultant|consultancy|services?)\b|\bmarketing\s+agency\b", re.I)),
    ("web_design_development_provider", re.compile(r"\b(?:web|website)\s+(?:design|development)\s+(?:agency|agencies|studio|company|services?)\b|\bweb\s+design\s+and\s+development\b", re.I)),
    ("branding_ppc_provider", re.compile(r"\b(?:branding|brand strategy|ppc|pay.per.click|advertising)\s+(?:agency|agencies|consultant|consultancy|services?)\b", re.I)),
    ("consulting_outsourcing_provider", re.compile(r"\b(?:consulting|consultancy|outsourcing|outsource)\s+(?:firm|company|agency|services?)\b", re.I)),
)
NON_OWNED_LANDING_HOSTS = {
    'linktr.ee', 'beacons.ai', 'bio.site', 'linkin.bio', 'taplink.cc',
    'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com', 'search.brave.com',
    'facebook.com', 'instagram.com', 'linkedin.com', 'x.com', 'twitter.com',
    'youtube.com', 'tiktok.com',
}
SEARCH_ENGINE_BRANDS = {'google', 'bing', 'yahoo', 'duckduckgo'}


def _non_owned_host(host):
    return (any(host == domain or host.endswith('.' + domain) for domain in NON_OWNED_LANDING_HOSTS)
            or any(label in SEARCH_ENGINE_BRANDS for label in host.split('.')))


def _company_website(url):
    if not public_http_url(str(url or '')):
        return False
    host = (urlsplit(str(url)).hostname or '').casefold().removeprefix('www.')
    return not _non_owned_host(host)


def peer_agency_reason(row):
    """Hard-exclude clear GEO/SEO/marketing/build/consulting peers before sampling."""
    fields = ("company_name", "industry_hint", "directory_text", "description",
              "company_description", "business_type", "services", "service_description")
    text = " ".join(str(row.get(key) or "") for key in fields)
    for reason, pattern in PEER_AGENCY_PATTERNS:
        if pattern.search(text):
            return reason
    return ""


def _usable_contact(contact, channel, website):
    evidence = contact.get('evidence') or {}
    url = str(contact.get('value') or '')
    source = str(evidence.get('source_url') or '')
    website_host = (urlsplit(str(website or '')).hostname or '').casefold().removeprefix('www.')
    if _non_owned_host(website_host):
        return False
    if (contact.get('channel') != channel or not public_http_url(source)
            or (urlsplit(source).hostname or '').casefold().removeprefix('www.') != website_host):
        return False
    host = (urlsplit(url).hostname or '').casefold().removeprefix('www.')
    if channel == 'whatsapp':
        if host not in {'wa.me', 'api.whatsapp.com', 'web.whatsapp.com', 'whatsapp.com'}:
            return False
        parsed = urlsplit(url)
        if host == 'wa.me':
            path = parsed.path.strip('/')
            if path.casefold().startswith('message/'):
                return len(path.split('/', 1)[1]) >= 6
            digits = re.sub(r'\D', '', path)
        else:
            digits = re.sub(r'\D', '', (parse_qs(parsed.query).get('phone') or [''])[0])
        return 7 <= len(digits) <= 15
    if channel == 'telegram':
        path = urlsplit(url).path.casefold().strip('/')
        return (host in {'t.me', 'telegram.me'}
                and contact.get('route_type') == 'direct_chat'
                and not path.startswith(('share/', 'joinchat/', '+', 's/', 'c/', 'addlist/'))
                and contact.get('route_type') not in {'bot', 'group_or_channel', 'share'})
    return channel == 'email' and '@' in url


def classify_pool(row):
    """Never promote an email or an unverified phone to a chat route."""
    if row.get('contact_enrichment_status') != 'completed':
        return 'review'
    review = row.get('prelock_quality_review') or {}
    if review.get('reviewed') is True and review.get('rating') == 'reject':
        return 'review', 'quality_rejected'
    contacts = row.get('contacts') or []
    website = row.get('website_url')
    if any(_usable_contact(c, 'whatsapp', website) for c in contacts):
        return 'chat', 'whatsapp'
    if any(_usable_contact(c, 'telegram', website) for c in contacts):
        return 'chat', 'telegram'
    if any(_usable_contact(c, 'email', website) for c in contacts):
        if (review.get('reviewed') is True and review.get('rating') == 'high'
                and review.get('claim') and public_http_url(review.get('source_url', ''))):
            return 'email', 'email'
        return 'email_review', 'email'
    return 'review', 'no_usable_route'


def quality_reviewed(row):
    review = row.get('prelock_quality_review') or {}
    return (review.get('reviewed') is True and review.get('rating') == 'high'
            and bool(review.get('claim')) and public_http_url(review.get('source_url', '')))


def _cache_key(row):
    return hashlib.sha256(json.dumps([sampling_record_key(row), row.get('company_name'),
        row.get('website_url'), row.get('industry_hint'), row.get('raw_snapshot_sha256'),
        row.get('prelock_quality_review'), row.get('prelock_assessment'),
        row.get('website_resolution_status')], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _cache_identity(row):
    """Compatibility identity for prelock caches written before resolver fields existed."""
    return (sampling_record_key(row), str(row.get('company_name') or '').strip().casefold(),
            canonical_domain(str(row.get('website_url') or '')))


def screen_raw_pool(rows, *, cache_path: Path, screen_fn=None, workers=32, refresh=False,
                    max_pages=5, retry_failed=False):
    """Resume website contact checks, then write mutually exclusive contact pools."""
    cache_path = Path(cache_path)
    screen_fn = screen_fn or (lambda row: enrich_record(
        row, max_pages=max_pages, delay_seconds=0.25, robots_timeout=5,
        fetcher=lambda url: fetch_html(url, timeout=8, max_bytes=750_000)))
    cached = {}
    cached_by_identity = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            cached[entry['key']] = entry['row']
            cached_by_identity[_cache_identity(entry['row'])] = entry['row']
    pools = {'chat': [], 'email': [], 'email_review': [], 'review': [], 'peer_excluded': []}
    pending = {}
    for row in rows:
        key = _cache_key(row)
        previous = cached.get(key) or cached_by_identity.get(_cache_identity(row))
        if previous is not None and not ((retry_failed or refresh) and previous.get('contact_enrichment_status') == 'fetch_failed'):
            # Reuse expensive page/contact evidence but keep fields freshly
            # normalized from the current RAW source record.
            merged = dict(previous)
            merged.update(row)
            for field in ('contacts', 'pages_checked', 'contact_enrichment_status',
                          'contact_enrichment_error', 'prelock_error',
                          'prelock_quality_review', 'prelock_quality_reviewed_at'):
                if field in previous:
                    merged[field] = previous[field]
            cached[key] = merged
        elif previous is not None and retry_failed:
            pending.setdefault(key, row)
        else:
            peer_reason = peer_agency_reason(row)
            if peer_reason:
                cached[key] = {**row, 'contact_enrichment_status': 'peer_agency_excluded',
                               'peer_exclusion_reason': peer_reason}
            elif (not eligible_raw_record(row) or classify_vertical(row) == SECONDARY
                    or not _company_website(str(row.get('website_url') or ''))
                    or row.get('do_not_contact') is True or row.get('chain') is True):
                cached[key] = {**row, 'contact_enrichment_status': 'prelock_ineligible'}
            else:
                pending.setdefault(key, row)
    if pending:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        vertical_priority = {WEB3: 0, AI_B2B: 1, VAPE_TOBACCO: 2,
                             ADULT_RETAIL: 3, ALCOHOL_BAR: 4}
        ordered_pending = sorted(pending.items(), key=lambda pair: (
            vertical_priority.get(classify_vertical(pair[1]), 9), pair[0]))
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 32))) as executor:
            futures = {executor.submit(screen_fn, row): key for key, row in ordered_pending}
            with cache_path.open('a', encoding='utf-8') as stream:
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        result = future.result()
                        if sampling_record_key(result) != sampling_record_key(pending[key]):
                            raise ValueError('screening changed company identity')
                    except Exception as exc:
                        result = {**pending[key], 'contact_enrichment_status': 'fetch_failed',
                                  'prelock_error': str(exc)}
                    cached[key] = result
                    cached_by_identity[_cache_identity(result)] = result
                    stream.write(json.dumps({'key': key, 'row': result}, ensure_ascii=False) + '\n')
                    stream.flush()
    for row in rows:
        screened = cached[_cache_key(row)]
        if sampling_record_key(screened) != sampling_record_key(row) or screened.get('company_name') != row.get('company_name'):
            raise ValueError('prelock cache changed company identity')
        if screened.get('contact_enrichment_status') == 'peer_agency_excluded':
            pool, route = 'peer_excluded', screened.get('peer_exclusion_reason')
        else:
            outcome = classify_pool(screened)
            pool, route = outcome if isinstance(outcome, tuple) else (outcome, 'none')
        available_channels = [channel for channel in ('whatsapp', 'telegram')
                              if any(_usable_contact(c, channel, screened.get('website_url'))
                                     for c in (screened.get('contacts') or []))]
        pools[pool].append({**screened, 'prelock_pool': pool, 'prelock_channel': route,
                            'available_contact_channels': available_channels,
                            'prelock_quality_reviewed': quality_reviewed(screened),
                            'prelock_status': 'contact_candidate_not_sales_qualified'})
    return pools
