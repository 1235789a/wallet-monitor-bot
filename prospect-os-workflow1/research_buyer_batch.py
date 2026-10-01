"""Cached public-page enrichment of an already frozen off-search pool. No auto qualification."""
import argparse
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs

from workflow1_company_screening import TextAndLinksParser, fetch_html
from workflow1_daily import normalize_domain
from prospect_os.sampling import (DEFAULT_SEED, FORMAL_30_QUOTAS, sampling_record_key,
                                  stratified_sample)
from prospect_os.sample_lock import DEFAULT_LOCK, align_to_lock, freeze_sample, load_lock, verify_final_ids
from prospect_os.history_exclusion import exclude_history
from prospect_os.contact_pools import screen_raw_pool
from prospect_os.website_resolution import resolve_website, resolve_website_pool
from prospect_os.prelock_preflight import preflight_record
from prospect_os.source_yield import build_source_yield
from prospect_os.expansion import run_expansion_loop
from prospect_os.buyer_rating import (RATING_CONFIG, rate_candidate, rating_summary)

CACHE = Path('runs/buyer-sprint/pages')

def run_expansion_until_terminal(**pipeline_callbacks):
    """Continue prelock batches until ready, source exhaustion, or a true blocker.

    The callbacks reuse the current discovery, history, website/contact screening,
    preflight, and review implementations. Sample selection and lock enforcement
    remain in their existing functions and are called only after the reserve gate.
    """
    return run_expansion_loop(**pipeline_callbacks)


def page(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:20] + '.json')
    if p.exists():
        return json.loads(p.read_text())
    result = {'requested_url': url, 'checked_at': datetime.now(timezone.utc).isoformat()}
    try:
        body, final, _ = fetch_html(url, timeout=12, max_bytes=4_000_000)
        parser = TextAndLinksParser(); parser.feed(body)
        text = ' '.join(parser.text_parts)
        links = list(dict.fromkeys(urljoin(final, u) for u in parser.links))
        result.update(status='ok', url=final, text=text, links=links,
                      jsonld=re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', body, re.S),
                      dates=list(dict.fromkeys(re.findall(r'20(?:25|26)-\d{2}-\d{2}',body))),
                      meta_robots=re.findall(r'<meta[^>]*name=["\']robots["\'][^>]*>',body,re.I),
                      sha256=hashlib.sha256(body.encode()).hexdigest())
        # Save exact inspected HTML for claims that cannot be proved from prose alone.
        p.with_suffix('.html').write_text(body)
    except Exception as e:
        result.update(status='fetch_failed',error=str(e))
    p.write_text(json.dumps(result,ensure_ascii=False))
    result['artifact']=str(p)
    return result


def assign_contact_quota(rows, *, seed, required=None):
    """Keep a company's original routes and assign exact formal channels when possible."""
    required = required or RATING_CONFIG['formal_channels']
    required_wa, required_tg = required['whatsapp'], required['telegram']
    eligible = []
    for row in rows:
        channels = row.get('available_contact_channels') or [row.get('prelock_channel')]
        channels = [ch for ch in ('whatsapp', 'telegram') if ch in channels]
        eligible.append((dict(row), channels))
    tg_only = [item for item in eligible if item[1] == ['telegram']]
    dual = [item for item in eligible if 'telegram' in item[1] and 'whatsapp' in item[1]]
    wa_only = [item for item in eligible if item[1] == ['whatsapp']]
    if len(tg_only) + len(dual) < required_tg or len(wa_only) + len(dual) < required_wa:
        return [], {'feasible': False, 'available_whatsapp': len(wa_only) + len(dual),
                    'available_telegram': len(tg_only) + len(dual),
                    'selected': {'whatsapp': 0, 'telegram': 0}}
    # Telegram is assigned to TG-only contacts first. A dual-route company is
    # explicitly switched to Telegram only for the remaining exact quota.
    rank = lambda pair: (-(pair[0].get('buyer_priority_score') or 0),
                         hashlib.sha256((str(seed) + '|contact-quota|' + str(
                             pair[0].get('identity_key') or pair[0].get('source_id')
                             or pair[0].get('company_name') or '')).encode()).hexdigest())
    tg_only.sort(key=rank)
    dual.sort(key=rank)
    wa_only.sort(key=rank)
    selected_tg = (tg_only + dual)[:required_tg]
    selected = []
    for row, channels in eligible:
        channel = 'telegram' if any(row is x[0] for x in selected_tg) else 'whatsapp'
        if channel not in channels:
            return [], {'feasible': False, 'available_whatsapp': len(wa_only) + len(dual),
                        'available_telegram': len(tg_only) + len(dual),
                        'selected': {'whatsapp': 0, 'telegram': 0}}
        row['selected_contact_channel'] = channel
        # Keep the historical route field aligned for the existing lock schema.
        row['prelock_channel'] = channel
        selected.append(row)
    counts = Counter(row['selected_contact_channel'] for row in selected)
    feasible = counts['whatsapp'] == required_wa and counts['telegram'] == required_tg
    return selected if feasible else [], {'feasible': feasible,
        'available_whatsapp': len(wa_only) + len(dual),
        'available_telegram': len(tg_only) + len(dual),
        'selected': {'whatsapp': counts['whatsapp'], 'telegram': counts['telegram']}}


def enrich(row):
    row=dict(row)
    if not row.get('website_url') and row.get('profile_url'):
        profile=page(row['profile_url']);row['profile_audit']=profile
        for link in profile.get('links',[]):
            target=parse_qs(urlsplit(link).query).get('u',[''])[0]
            if target.startswith('http') and not normalize_domain(target).endswith('clutch.co'):
                row['website_url']=target.split('?')[0];break
    if not row.get('website_url'):
        row['research_status']='website_unresolved'
        row['status']={'research_failed':True,'contact_missing':True}
        return row
    home=page(row['website_url']); pages=[home]
    if home['status']=='ok':
        links=[u for u in home['links'] if normalize_domain(u)==normalize_domain(home['url'])]
        chosen=[]
        for terms in [('contact', 'about', 'team'), ('blockchain','web3','token','exchange','service'), ('blog','insight','news')]:
            match=next((u for u in links if any(t in urlsplit(u).path.lower() for t in terms) and u not in chosen),None)
            if match: chosen.append(match)
        for u in chosen: pages.append(page(u))
        # One dated article for activity; do not infer recency from sitemap/footer dates.
        blog=next((p for p in pages if any(t in urlsplit(p.get('url','')).path.lower() for t in ('blog','insight','news'))),None)
        if blog:
            article=next((u for u in blog.get('links',[]) if normalize_domain(u)==normalize_domain(home['url']) and u not in chosen and len(urlsplit(u).path.strip('/').split('/'))>=2 and any(t in urlsplit(u).path.lower() for t in ('blog','insight','news'))),None)
            if article: pages.append(page(article))
    row['pages']=pages;row['research_status']='pages_collected' if home['status']=='ok' else 'website_fetch_failed'
    row['contact_candidates']=[{'value':u,'source_url':p.get('url')} for p in pages for u in p.get('links',[]) if u.startswith('mailto:') or any(h in u for h in ('wa.me/','api.whatsapp.com/','t.me/','linkedin.com/in/'))]
    row['status']={'research_failed':home['status']!='ok',
                   'contact_missing':not bool(row['contact_candidates'])}
    return row


def run_batch(raw, *, limit, seed, output, summary_path, lock_path, enrich_fn=enrich,
              history_sources=(), excluded_path=None, pool_mode='contact_first',
              screen_fn=None, min_whatsapp=24, telegram_cap=6, refresh_screen=False,
              allow_shortfall_lock=False, prelock_workers=32, prelock_pages=5,
              retry_prelock_failures=False, reserve_pool_target=42,
              website_resolver_fn=resolve_website,
              preflight_fn=preflight_record):
    output, summary_path, lock_path = Path(output), Path(summary_path), Path(lock_path)
    if min_whatsapp < 0 or telegram_cap < 0:
        raise ValueError('contact targets must be nonnegative')
    if limit == 30 and (min_whatsapp != 24 or telegram_cap != 6):
        raise ValueError('formal 30-company production quota is fixed at exactly 24 WhatsApp and 6 Telegram')
    if limit == 30 and reserve_pool_target < 30:
        raise ValueError('formal reserve pool target cannot be below the 30-company sample size')
    excluded_path = Path(excluded_path) if excluded_path else output.with_name('excluded-history.json')
    if lock_path.exists():
        lock = load_lock(lock_path)
        if lock['seed'] != seed or lock['limit'] != limit:
            raise ValueError('existing sample lock has different seed/limit; use a new run directory')
        targets = [sample['record'] for sample in lock['samples']]
        summary = lock.get('sampling_summary', {})
    else:
        eligible, excluded = exclude_history(raw, history_sources)
        pool_summary = {}
        if pool_mode == 'contact_first':
            # Resolve only from explicit company links on URLs already present
            # in RAW, after history exclusion and before contact screening.
            resolved_eligible = resolve_website_pool(
                eligible, cache_path=output.with_name('website-resolution.jsonl'),
                resolver_fn=website_resolver_fn,
                workers=min(prelock_workers, 24))
            pools = screen_raw_pool(resolved_eligible, cache_path=output.with_name('prelock-screen.jsonl'),
                                    screen_fn=screen_fn, refresh=refresh_screen,
                                    workers=prelock_workers, max_pages=prelock_pages,
                                    retry_failed=retry_prelock_failures)
            preflight_rows = [rate_candidate(preflight_fn(row))
                              for key in ('chat', 'review') for row in pools[key]]
            pools['chat'] = [row for row in preflight_rows if row.get('prelock_pool') == 'chat']
            pools['review'] = [row for row in preflight_rows if row.get('prelock_pool') == 'review']
            pools['prelock_pass'] = [row for row in preflight_rows if row.get('prelock_status') == 'PRELOCK_PASS']
            pools['prelock_review'] = [row for row in preflight_rows if row.get('prelock_status') == 'PRELOCK_REVIEW']
            pools['prelock_reject'] = [row for row in preflight_rows if row.get('prelock_status') == 'PRELOCK_REJECT']
            for name, rows in pools.items():
                file_name = {'prelock_pass': 'prelock-icp-pass',
                             'prelock_review': 'prelock-icp-review',
                             'prelock_reject': 'prelock-icp-reject'}.get(name, f'prelock-{name}')
                output.with_name(f'{file_name}.json').parent.mkdir(parents=True, exist_ok=True)
                output.with_name(f'{file_name}.json').write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
            screened_rows = [row for name, rows in pools.items()
                             if name not in {'prelock_pass', 'prelock_review', 'prelock_reject'}
                             for row in rows]
            yield_report = build_source_yield(raw, excluded, screened_rows)
            output.with_name('source-yield.json').write_text(
                json.dumps(yield_report, ensure_ascii=False, indent=2), encoding='utf-8')
            eligible_for_sample = pools['prelock_pass']
            if limit == 30:
                eligible_for_sample = [row for row in eligible_for_sample
                                       if row.get('buyer_grade') not in RATING_CONFIG['formal_exclude_grades']]
            rating_report = rating_summary(preflight_rows, needed_total=limit,
                                           vertical_quotas=FORMAL_30_QUOTAS if limit == 30 else {})
            rating_report['eligible_for_formal_sample'] = len(eligible_for_sample)
            output.with_name('prelock-rating-summary.json').write_text(
                json.dumps(rating_report, ensure_ascii=False, indent=2), encoding='utf-8')
            pool_summary = {'pool_counts': {name: len(rows) for name, rows in pools.items()},
                            'email_pool_requires_explicit_quality_review': True,
                            'reserve_pool_target': reserve_pool_target if limit == 30 else None,
                            'reserve_pool_pass_count': len(pools['prelock_pass']),
                            'reserve_pool_shortfall': max(0, reserve_pool_target - len(pools['prelock_pass'])) if limit == 30 else 0,
                            'whatsapp_target': min(min_whatsapp, limit),
                            'telegram_cap': telegram_cap,
                            'required_contact_channels': ({'whatsapp': 24, 'telegram': 6} if limit == 30 else None),
                            'prelock_pass_count': len(pools['prelock_pass']),
                            'prelock_review_count': len(pools['prelock_review']),
                            'prelock_reject_count': len(pools['prelock_reject'])}
            targets, summary = stratified_sample(eligible_for_sample, limit=limit, seed=seed,
                                                  prefer_whatsapp=True, telegram_cap=telegram_cap)
            channel_assignment = None
            if limit == 30:
                targets, channel_assignment = assign_contact_quota(
                    targets, seed=seed, required=RATING_CONFIG['formal_channels'])
                pool_summary['contact_quota_assignment'] = channel_assignment
            wa_count = sum(row.get('prelock_channel') == 'whatsapp' for row in targets)
            tg_count = sum(row.get('prelock_channel') == 'telegram' for row in targets)
            pool_summary['whatsapp_selected'] = wa_count
            pool_summary['whatsapp_shortfall'] = max(0, min(min_whatsapp, limit) - wa_count)
            pool_summary['telegram_selected'] = tg_count
            pool_summary['track_counts'] = summary.get('track_counts', {})
            pool_summary['vertical_counts'] = summary.get('selected_by_vertical', {})
            pool_summary['required_by_vertical'] = (
                FORMAL_30_QUOTAS if limit == 30 else {})
            vertical_counts = summary.get('selected_by_vertical', {})
            formal_vertical_mix = {vertical: vertical_counts.get(vertical, 0)
                                   for vertical in FORMAL_30_QUOTAS}
            pool_summary['sample_lock_feasible'] = bool(
                len(targets) == limit
                and wa_count == 24
                and tg_count == 6
                and summary.get('track_counts') == {'track_a': 15, 'track_b': 15}
                and formal_vertical_mix == FORMAL_30_QUOTAS
                and vertical_counts.get('secondary_other', 0) == 0
                and len(pools['prelock_pass']) >= reserve_pool_target
                and all(row.get('prelock_status') == 'PRELOCK_PASS' for row in targets)) if limit == 30 else bool(
                    len(targets) == limit and wa_count >= min_whatsapp and tg_count <= telegram_cap
                )
            pool_summary['quality_reviewed_selected'] = sum(
                row.get('prelock_quality_reviewed') is True for row in targets)
            pool_summary['outreach_ready'] = False
        elif pool_mode == 'legacy':
            targets, summary = stratified_sample(eligible, limit=limit, seed=seed)
        else:
            raise ValueError(f'unknown pool mode: {pool_mode}')
        summary.update(pool_summary)
        summary.update(raw_pool=len(raw), history_excluded=len(excluded),
                       eligible_after_history_filter=len(eligible), sampled=len(targets))
        excluded_path.parent.mkdir(parents=True, exist_ok=True)
        excluded_path.write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding='utf-8')
        if pool_mode == 'contact_first' and not allow_shortfall_lock and not pool_summary.get('sample_lock_feasible', False):
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            raise ValueError(
                f'prelock sample infeasible: {len(targets)}/{limit} PRELOCK_PASS; '
                f'{pool_summary.get("whatsapp_selected", 0)}/{pool_summary.get("whatsapp_target", 0)} '
                f'WhatsApp, {pool_summary.get("telegram_selected", 0)}/{telegram_cap} Telegram; '
                f'reserve={pool_summary.get("reserve_pool_pass_count", 0)}/{reserve_pool_target}; '
                f'tracks={pool_summary.get("track_counts")}, verticals={pool_summary.get("vertical_counts")}; '
                'no Sample Lock created')
        if not targets:
            raise ValueError('no eligible companies with chat routes after history exclusion and contact screening; sample lock not created')
        lock = freeze_sample(lock_path, targets, seed=seed, limit=limit, summary=summary)
    targets = align_to_lock(targets, lock)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.update(sample_lock_verified=True, sample_lock=str(lock_path))
    previous = json.loads(output.read_text()) if output.exists() else []
    previous = align_to_lock(previous, lock,
                             rejected_path=output.with_name('rejected-not-in-sample-lock.json')) if previous else []
    done = {sampling_record_key(r): r for r in previous if r.get('research_status')}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs = {ex.submit(enrich_fn, r): r for r in targets if sampling_record_key(r) not in done}
        for f in as_completed(fs):
            original = fs[f]
            try:
                r = f.result()
            except Exception as exc:
                r = {**original, 'research_status': 'research_failed',
                     'status': {'research_failed': True, 'contact_missing': True},
                     'research_error': str(exc)}
            # Check each returned identity before it enters the cache, including
            # a renamed company with an otherwise unchanged directory ID.
            align_to_lock([r], {'samples': [item for item in lock['samples']
                                              if item['id'] == sampling_record_key(original)],
                                'sample_ids': [sampling_record_key(original)]},
                          rejected_path=output.with_name('rejected-not-in-sample-lock.json'))
            r['sample_lock_verified'] = True
            done[sampling_record_key(original)] = r
            print(json.dumps({'done': len(done), 'company': r['company_name'],
                              'status': r['research_status'],
                              'contact_candidates': len(r.get('contact_candidates', []))}), flush=True)
    final = align_to_lock(list(done.values()), lock,
                          rejected_path=output.with_name('rejected-not-in-sample-lock.json'))
    verify_final_ids(final, lock)
    output.write_text(json.dumps(final, ensure_ascii=False, indent=2))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return final, summary


def main():
    a=argparse.ArgumentParser();a.add_argument('--limit',type=int,default=30)
    a.add_argument('--source',type=Path,default=Path('runs/buyer-sprint/discovery/raw.json'))
    a.add_argument('--output',type=Path,default=Path('runs/buyer-sprint/enriched.json'))
    a.add_argument('--sampling-summary',type=Path)
    a.add_argument('--sample-lock',type=Path,default=DEFAULT_LOCK)
    a.add_argument('--seed',type=int,default=DEFAULT_SEED)
    a.add_argument('--pool-mode',choices=('contact_first','legacy'),default='contact_first')
    a.add_argument('--min-whatsapp',type=int,default=24)
    a.add_argument('--telegram-cap',type=int,default=6)
    a.add_argument('--reserve-pool-target',type=int,default=42,
                   help='Formal 30-company runs require this many PRELOCK_PASS records before locking')
    a.add_argument('--refresh-prelock',action='store_true',
                   help='Compatibility flag: retry cached fetch failures only; completed screens remain reused')
    a.add_argument('--retry-prelock-failures',action='store_true',
                   help='Retry only cached fetch failures; completed website screens remain reused')
    a.add_argument('--allow-shortfall-lock',action='store_true',
                   help='Exploratory run only: freeze fewer chat/WhatsApp records than requested')
    a.add_argument('--prelock-workers',type=int,default=32,
                   help='Concurrent, robots-aware website checks for the RAW pool (max 32)')
    a.add_argument('--prelock-pages',type=int,default=5,
                   help='Maximum same-site pages per company; scanning stops early after a valid direct chat route')
    a.add_argument('--history-used',type=Path,action='append',default=[],
                   help='JSON used-company list; repeat for multiple exports')
    a.add_argument('--previous-contacted',type=Path,action='append',default=[],
                   help='JSON previously contacted company records')
    a.add_argument('--previous-sample-lock',type=Path,action='append',default=[],
                   help='Prior sampled-lock.json; repeat for each earlier run')
    a.add_argument('--excluded-history',type=Path,
                   help='Audit log; defaults to excluded-history.json next to enriched.json')
    args=a.parse_args()
    raw=json.loads(args.source.read_text())
    output=args.output
    summary_path=args.sampling_summary or output.with_name('sampling-summary.json')
    final,_=run_batch(raw,limit=args.limit,seed=args.seed,output=output,
                      summary_path=summary_path,lock_path=args.sample_lock,
                      pool_mode=args.pool_mode,min_whatsapp=args.min_whatsapp,
                      telegram_cap=args.telegram_cap,refresh_screen=args.refresh_prelock,
                      allow_shortfall_lock=args.allow_shortfall_lock,
                      prelock_workers=args.prelock_workers,
                      prelock_pages=args.prelock_pages,
                      retry_prelock_failures=args.retry_prelock_failures,
                      reserve_pool_target=args.reserve_pool_target,
                      history_sources=[('history_used',p) for p in args.history_used]
                                    +[('previous_contacted',p) for p in args.previous_contacted]
                                    +[('previous_sample_lock',p) for p in args.previous_sample_lock],
                      excluded_path=args.excluded_history)
    print(json.dumps({'raw':len(raw),'selected':len(final),'enriched':len(final),
                      'sampling_summary':str(summary_path),'sample_lock_verified':True}))

if __name__=='__main__':main()
