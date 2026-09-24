"""Cached public-page enrichment of an already frozen off-search pool. No auto qualification."""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs

from workflow1_company_screening import TextAndLinksParser, fetch_html
from workflow1_daily import normalize_domain
from prospect_os.sampling import DEFAULT_SEED, sampling_record_key, stratified_sample
from prospect_os.sample_lock import DEFAULT_LOCK, align_to_lock, freeze_sample, load_lock, verify_final_ids
from prospect_os.history_exclusion import exclude_history

CACHE = Path('runs/buyer-sprint/pages')


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
              history_sources=(), excluded_path=None):
    output, summary_path, lock_path = Path(output), Path(summary_path), Path(lock_path)
    excluded_path = Path(excluded_path) if excluded_path else output.with_name('excluded-history.json')
    if lock_path.exists():
        lock = load_lock(lock_path)
        if lock['seed'] != seed or lock['limit'] != limit:
            raise ValueError('existing sample lock has different seed/limit; use a new run directory')
        targets = [sample['record'] for sample in lock['samples']]
        summary = lock.get('sampling_summary', {})
    else:
        eligible, excluded = exclude_history(raw, history_sources)
        targets, summary = stratified_sample(eligible, limit=limit, seed=seed)
        summary.update(raw_pool=len(raw), history_excluded=len(excluded),
                       eligible_after_history_filter=len(eligible), sampled=len(targets))
        excluded_path.parent.mkdir(parents=True, exist_ok=True)
        excluded_path.write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding='utf-8')
        if not targets:
            raise ValueError('no eligible companies after history exclusion; sample lock not created')
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
                      history_sources=[('history_used',p) for p in args.history_used]
                                    +[('previous_contacted',p) for p in args.previous_contacted]
                                    +[('previous_sample_lock',p) for p in args.previous_sample_lock],
                      excluded_path=args.excluded_history)
    print(json.dumps({'raw':len(raw),'selected':len(final),'enriched':len(final),
                      'sampling_summary':str(summary_path),'sample_lock_verified':True}))

if __name__=='__main__':main()
