"""Cheap, source-first contact screening before a new sample is frozen."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

from .contact_enrichment import enrich_record
from .sampling import SECONDARY, classify_vertical, eligible_raw_record, sampling_record_key
from .source_pool import public_http_url


def _usable_contact(contact, channel, website):
    evidence = contact.get('evidence') or {}
    url = str(contact.get('value') or '')
    source = str(evidence.get('source_url') or '')
    if (contact.get('channel') != channel or not public_http_url(source)
            or (urlsplit(source).hostname or '').casefold().removeprefix('www.')
            != (urlsplit(str(website or '')).hostname or '').casefold().removeprefix('www.')):
        return False
    host = (urlsplit(url).hostname or '').casefold().removeprefix('www.')
    if channel == 'whatsapp':
        return host in {'wa.me', 'api.whatsapp.com', 'web.whatsapp.com', 'whatsapp.com'}
    if channel == 'telegram':
        return host in {'t.me', 'telegram.me'} and contact.get('route_type') not in {'bot', 'group_or_channel'}
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
        row.get('prelock_quality_review')], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def screen_raw_pool(rows, *, cache_path: Path, screen_fn=None, workers=8, refresh=False):
    """Resume website contact checks, then write mutually exclusive contact pools."""
    cache_path = Path(cache_path)
    screen_fn = screen_fn or (lambda row: enrich_record(row, max_pages=2, delay_seconds=0.25))
    cached = {}
    if cache_path.exists() and not refresh:
        for line in cache_path.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            cached[entry['key']] = entry['row']
    pools = {'chat': [], 'email': [], 'email_review': [], 'review': []}
    pending = {}
    for row in rows:
        key = _cache_key(row)
        if key not in cached:
            if (not eligible_raw_record(row) or classify_vertical(row) == SECONDARY
                    or not public_http_url(str(row.get('website_url') or ''))
                    or row.get('do_not_contact') is True or row.get('chain') is True):
                cached[key] = {**row, 'contact_enrichment_status': 'prelock_ineligible'}
            else:
                pending.setdefault(key, row)
    if pending:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if refresh:
            cache_path.unlink(missing_ok=True)
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
            futures = {executor.submit(screen_fn, row): key for key, row in pending.items()}
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
                    stream.write(json.dumps({'key': key, 'row': result}, ensure_ascii=False) + '\n')
                    stream.flush()
    for row in rows:
        screened = cached[_cache_key(row)]
        if sampling_record_key(screened) != sampling_record_key(row) or screened.get('company_name') != row.get('company_name'):
            raise ValueError('prelock cache changed company identity')
        outcome = classify_pool(screened)
        pool, route = outcome if isinstance(outcome, tuple) else (outcome, 'none')
        pools[pool].append({**screened, 'prelock_pool': pool, 'prelock_channel': route,
                            'prelock_quality_reviewed': quality_reviewed(screened),
                            'prelock_status': 'contact_candidate_not_sales_qualified'})
    return pools
