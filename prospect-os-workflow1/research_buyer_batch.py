"""Cached public-page enrichment of an already frozen off-search pool. No auto qualification."""
import argparse
import hashlib
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs

from workflow1_company_screening import TextAndLinksParser, fetch_html
from workflow1_daily import normalize_domain

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
        row['research_status']='website_unresolved';return row
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
    return row


def main():
    a=argparse.ArgumentParser();a.add_argument('--limit',type=int,default=60);args=a.parse_args()
    raw=json.loads(Path('runs/buyer-sprint/discovery/raw.json').read_text())
    pool=[r for r in raw if r.get('directory_team_range') in ('2 - 9','10 - 49')]
    random.Random(20260907).shuffle(pool)
    # Include every small-company block encountered, in a fixed shuffled order, not directory rank.
    targets=pool[:args.limit];output=Path('runs/buyer-sprint/enriched.json')
    previous=json.loads(output.read_text()) if output.exists() else []
    done={r['directory_id']:r for r in previous}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(enrich,r):r for r in targets if r['directory_id'] not in done}
        for f in as_completed(fs):
            r=f.result();done[r['directory_id']]=r
            output.write_text(json.dumps(list(done.values()),ensure_ascii=False,indent=2))
            print(json.dumps({'done':len(done),'company':r['company_name'],'status':r['research_status'],'contact_candidates':len(r.get('contact_candidates',[]))}),flush=True)
    print(json.dumps({'raw':len(raw),'small_directory_candidates':len(pool),'enriched':len(done)}))

if __name__=='__main__':main()
