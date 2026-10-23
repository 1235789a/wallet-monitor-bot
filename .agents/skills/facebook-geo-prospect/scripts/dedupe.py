#!/usr/bin/env python3
"""Conservative cross-file FB prospect dedupe; never claims global history clearance.

Usage: python dedupe.py --candidates candidates.csv --history history.csv --history prior_fb_candidates.csv --output output.csv
"""
import argparse
import csv
import difflib
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, parse_qs

COMPANY = ('company','company_name','name','公司','企业','公司名称')
DOMAIN = ('website','domain','website_url','官网','网址','site')
FACEBOOK = ('fb_profile_url','facebook_page_url','facebook_person_url','facebook','fb_url','facebook_url','profile_url','fb_profile')


def field(row, names):
    lookup = {k.casefold().strip(): str(v or '').strip() for k,v in row.items() if k is not None}
    for n in names:
        v=lookup.get(n.casefold())
        if v:
            return v
    return ''


def namekey(s):
    return ''.join(c for c in unicodedata.normalize('NFKC',s).casefold() if c.isalnum())


def domain(s):
    s=s.strip()
    if not s: return ''
    if not re.match(r'^[a-z]+://',s,re.I): s='https://'+s
    host=(urlparse(s).hostname or '').casefold().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def fbkey(s):
    s=s.strip()
    if not s: return ''
    if not re.match(r'^[a-z]+://',s,re.I): s='https://'+s
    p=urlparse(s)
    host=(p.hostname or '').casefold()
    if host not in {'facebook.com','www.facebook.com','m.facebook.com','fb.com','www.fb.com'}: return ''
    path=p.path.strip('/').casefold()
    if path=='profile.php':
        ids=parse_qs(p.query).get('id',[])
        return 'id:'+ids[0] if ids else ''
    path=path.replace('pages/','',1) if path.startswith('pages/') else path
    if not path or path in ('share','groups','events','watch','marketplace'): return ''
    return path.rstrip('/')


def read_csv(path):
    with open(path,'r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def norm(row):
    fb=[fbkey(str(row.get(k,''))) for k in row if any(k.casefold()==v.casefold() for v in FACEBOOK)]
    return (namekey(field(row,COMPANY)),domain(field(row,DOMAIN)),set(x for x in fb if x))


def run(candidate_file, history_files, output):
    candidates=read_csv(candidate_file)
    histories=[]
    for hf in history_files:
        for i,r in enumerate(read_csv(hf),2): histories.append((str(hf),i,r,norm(r)))
    output_rows=[]
    for c in candidates:
        a,b,fc=norm(c)
        hits=[]; possible=[]
        for path,i,h,(x,y,fh) in histories:
            hits_on=[]
            if a and x and a==x: hits_on.append('company')
            if b and y and b==y: hits_on.append('website_host')
            if fc and fh and fc.intersection(fh): hits_on.append('fb_profile')
            if hits_on:
                hits.append((path,i,'+'.join(hits_on)))
            elif a and x and len(a)>5 and difflib.SequenceMatcher(None,a,x).ratio()>=0.91:
                possible.append((path,i,'similar_company'))
        if hits:
            status='MATCH_HISTORY'; why='; '.join(f'{p}:{i}:{why}' for p,i,why in hits[:5])
        elif possible:
            status='POSSIBLE_MATCH_REVIEW'; why='; '.join(f'{p}:{i}:{why}' for p,i,why in possible[:5])
        else:
            status='NO_HISTORY_MATCH_FOUND'; why=f'No match in {len(history_files)} supplied history files; NOT a global-clear/READY claim'
        output_rows.append({**c,'_dedupe_status':status,'_match_reason':why})
    keys=list(dict.fromkeys(k for r in output_rows for k in r)) if output_rows else ['_dedupe_status','_match_reason']
    with open(output,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(output_rows)
    print('rows:',len(output_rows),'matched:',sum(r['_dedupe_status']=='MATCH_HISTORY' for r in output_rows),'possible:',sum(r['_dedupe_status']=='POSSIBLE_MATCH_REVIEW' for r in output_rows),'no-match:',sum(r['_dedupe_status']=='NO_HISTORY_MATCH_FOUND' for r in output_rows))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--history',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.candidates,a.history,a.output)
