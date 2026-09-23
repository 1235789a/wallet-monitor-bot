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
from prospect_os.sample_lock import DEFAULT_LOCK, align_to_lock, freeze_sample, verify_final_ids

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


def main():
    a=argparse.ArgumentParser();a.add_argument('--limit',type=int,default=30)
    a.add_argument('--source',type=Path,default=Path('runs/buyer-sprint/discovery/raw.json'))
    a.add_argument('--output',type=Path,default=Path('runs/buyer-sprint/enriched.json'))
    a.add_argument('--sampling-summary',type=Path)
    a.add_argument('--sample-lock',type=Path,default=DEFAULT_LOCK)
    a.add_argument('--seed',type=int,default=DEFAULT_SEED)
    args=a.parse_args()
    raw=json.loads(args.source.read_text())
    targets, summary = stratified_sample(raw, limit=args.limit, seed=args.seed)
    lock=freeze_sample(args.sample_lock, targets, seed=args.seed, limit=args.limit)
    targets=align_to_lock(targets, lock)
    output=args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    summary_path=args.sampling_summary or output.with_name('sampling-summary.json')
    summary_path.parent.mkdir(parents=True,exist_ok=True)
    summary.update(sample_lock_verified=True, sample_lock=str(args.sample_lock))
    previous=json.loads(output.read_text()) if output.exists() else []
    previous=align_to_lock(previous,lock,rejected_path=output.with_name('rejected-not-in-sample-lock.json')) if previous else []
    target_keys={sampling_record_key(r) for r in targets}
    # Reject any old unstratified output instead of silently filtering drift.
    # Resume cached enrichment only for identities in this lock.
    done={sampling_record_key(r):r for r in previous if sampling_record_key(r) in target_keys and r.get('research_status')}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(enrich,r):r for r in targets if sampling_record_key(r) not in done}
        for f in as_completed(fs):
            try:
                r=f.result()
            except Exception as exc:
                r={**fs[f], 'research_status':'research_failed',
                   'status':{'research_failed':True,'contact_missing':True},
                   'research_error':str(exc)}
            r['sample_lock_verified']=True;done[sampling_record_key(r)]=r
            output.write_text(json.dumps([done[sampling_record_key(t)] for t in targets if sampling_record_key(t) in done],ensure_ascii=False,indent=2))
            print(json.dumps({'done':len(done),'company':r['company_name'],'status':r['research_status'],'contact_candidates':len(r.get('contact_candidates',[]))}),flush=True)
    final=align_to_lock(list(done.values()),lock)
    verify_final_ids(final,lock)
    output.write_text(json.dumps(final,ensure_ascii=False,indent=2))
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'raw':len(raw),'selected':len(targets),'enriched':len(done),'sampling_summary':str(summary_path)}))

if __name__=='__main__':main()
