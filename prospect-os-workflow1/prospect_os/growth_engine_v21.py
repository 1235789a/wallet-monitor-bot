"""Opt-in v2.1 evidence gates. No network, messaging, publishing or legacy writes.

Evidence is supplied by a researcher, never invented by this module. Human
review of semantics remains necessary. UNKNOWN is not false and is not zero.
"""
from __future__ import annotations
import copy, hashlib, json, re, unicodedata
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from .source_pool import public_http_url

TARGETS = {'daily': {'whatsapp':12,'telegram':3},
           'four_day': {'whatsapp':48,'telegram':12},
           'reserve': {'whatsapp':16,'telegram':4},
           'total': {'whatsapp':64,'telegram':16}}
GRADES={'FACT','CUSTOMER_ASSERTED','WEB_OBSERVED','AI_OBSERVED','HYPOTHESIS','UNKNOWN'}
WEIGHTS={'icp_value':3,'buyer_search':2,'direct_role':2,'purchase_fit':2,'recent_activity':1}

def normalize_name(value):
    value=unicodedata.normalize('NFKD',str(value or '').casefold())
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in value if not unicodedata.combining(c))))

def domain(value):
    host=(urlsplit(str(value or '')).hostname or '').lower().removeprefix('www.')
    return host

def canonical_chat(value):
    p=urlsplit(str(value or '')); host=(p.hostname or '').lower(); path=p.path.strip('/')
    if p.scheme!='https':return None
    if host=='wa.me' and re.fullmatch(r'[1-9]\d{7,14}',path):return ('whatsapp',path)
    if host=='api.whatsapp.com' and p.path.rstrip('/')=='/send':
        phone=parse_qs(p.query).get('phone',[''])[0]
        if re.fullmatch(r'[1-9]\d{7,14}',phone):return ('whatsapp',phone)
    if host in {'t.me','telegram.me'} and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',path):
        if not path.casefold().endswith('bot'):return ('telegram',path.casefold())
    return None

def evidence_ok(e, grades=('FACT','WEB_OBSERVED','CUSTOMER_ASSERTED')):
    if not isinstance(e,dict) or e.get('grade') not in grades or not e.get('claim'):return False
    try:dt=datetime.fromisoformat(str(e.get('retrieved_at','')).replace('Z','+00:00'))
    except ValueError:return False
    return bool(dt.tzinfo and public_http_url(e.get('url','')) and e.get('evidence_id'))

def identity_keys(row):
    keys=set()
    for name in [row.get('company'),*(row.get('aliases') or [])]:
        if normalize_name(name):keys.add(('name',normalize_name(name)))
    for u in [row.get('website'),*(row.get('associated_domains') or [])]:
        if domain(u) and domain(u) not in {'wa.me','t.me','api.whatsapp.com'}:keys.add(('domain',domain(u)))
    for u in [row.get('chat_url'),*(row.get('other_chat_urls') or [])]:
        key=canonical_chat(u)
        if key:keys.add(key)
    # Explicit researcher-confirmed registrable domain, not a last-two-label guess.
    if row.get('registrable_domain'):keys.add(('registered_domain',row['registrable_domain'].casefold()))
    for a in row.get('verified_people_aliases') or []:keys.add(('person',normalize_name(a)))
    return keys

def history_match(row,history):
    matches=[]
    for old in history:
        fields=identity_keys(row)&identity_keys(old)
        if fields:matches.append({'entity_id':old.get('entity_id'), 'match_fields':sorted(fields),
                                  'source_url':old.get('history_source_url'), 'status':old.get('contact_status','UNKNOWN')})
    contacted={'SENT','REPLIED','DECLINED','DO_NOT_CONTACT','PAID','DELIVERED','TEST_PERMISSIONED'}
    if any(m['status'] in contacted for m in matches):return 'HISTORY_CONTACTED_EXCLUDE',matches
    if matches:return 'PRIOR_BATCH_REVIEW',matches
    return 'NO_HISTORY_MATCH_FOUND',[]

def industry_gate(dossier):
    ev=[e for e in dossier.get('sources',[]) if evidence_ok(e)]
    types={e.get('source_type') for e in ev if e.get('source_type')}
    score=dossier.get('score')
    return (isinstance(score,(int,float)) and not isinstance(score,bool) and 8<=score<=10
            and dossier.get('critical_facts_verified') is True and len({e['url'] for e in ev})>=4
            and len(types)>=2 and dossier.get('review_status')=='PASS')

def qualify(row, history, dossier):
    out=copy.deepcopy(row);reasons=[]
    hs,matches=history_match(row,history);out.update(history_status=hs,history_matches=matches)
    if hs!='NO_HISTORY_MATCH_FOUND':reasons.append(hs)
    if row.get('history_coverage_reviewed') is not True:reasons.append('HISTORY_COVERAGE_PENDING')
    if row.get('regulated') is True:reasons.append('HOLD_REGULATED')
    if row.get('is_geo_vendor') is True or row.get('internal_diy_confirmed') is True:reasons.append('PARTNER_OR_DIY')
    src=row.get('source') or {}
    if not all(src.get(k) for k in ['source_id','record_id','snapshot_hash']):reasons.append('SOURCE_RECORD_MISSING')
    if not evidence_ok(src):reasons.append('SOURCE_EVIDENCE_MISSING')
    if domain(src.get('url'))==domain(row.get('website')):reasons.append('SOURCE_NOT_INDEPENDENT')
    if not evidence_ok(row.get('website_evidence')):reasons.append('WEBSITE_IDENTITY_PENDING')
    chat=canonical_chat(row.get('chat_url')); contact=row.get('contact') or {}
    if not chat or contact.get('channel')!=chat[0] or contact.get('route_type') not in {'PERSON','BUSINESS_HUMAN'}:
        reasons.append('CONTACT_NOT_DIRECT_HUMAN')
    if contact.get('attribution_verified') is not True or not evidence_ok(contact.get('evidence')):
        reasons.append('CONTACT_ATTRIBUTION_PENDING')
    if row.get('contact_conflict') is True:reasons.append('CONTACT_SOURCE_CONFLICT')
    if not industry_gate(dossier):reasons.append('INDUSTRY_RESEARCH_PENDING')
    if row.get('industry_id')!=dossier.get('industry_id'):reasons.append('INDUSTRY_MISMATCH')
    if row.get('business_class_verified')!=row.get('business_class_claimed'):reasons.append('INDUSTRY_MISREAD')
    if row.get('icp_review')!='PASS' or not evidence_ok(row.get('icp_evidence')):reasons.append('ICP_PENDING')
    fit=row.get('purchase_fit') or {}
    if fit.get('review')!='PASS' or not evidence_ok(fit.get('evidence')):reasons.append('PURCHASE_FIT_UNKNOWN')
    if fit.get('internal_capacity_reviewed') is not True:reasons.append('INTERNAL_CAPACITY_UNKNOWN')
    # A priority score never overrides hard failures. Missing evidence earns no points.
    scores=row.get('scores') or {};out['score']=sum(min(cap,max(0,float(scores[k].get('score',0))))
        for k,cap in WEIGHTS.items() if isinstance(scores.get(k),dict) and evidence_ok(scores[k].get('evidence')))
    qa=row.get('outreach_qa') or {};text=row.get('final_copy','')
    if not text.strip() or len(text.split())>75 or text.count('?')+text.count('？')>1:reasons.append('COPY_NOT_USABLE')
    if not (qa.get('status')=='PASS' and qa.get('blind_review_pass') is True and qa.get('facts_reviewed') is True):reasons.append('OUTREACH_QA_PENDING')
    if re.search(r'found a gap|competitors (?:appear|are)|ignores you|losing (?:customers|revenue)',text,re.I):
        if not any(test_complete(t) for t in row.get('ai_tests',[])):reasons.append('UNTESTED_NEGATIVE_CLAIM')
    if not row.get('client_context_id'):reasons.append('CLIENT_CONTEXT_PENDING')
    if row.get('contact_status') in {'SENT','REPLIED','DECLINED','PAID','DO_NOT_CONTACT'}:reasons.append('CONTACTED_NOT_NEW')
    out['gate_reasons']=list(dict.fromkeys(reasons));out['stage']='HOLD' if reasons else 'READY_FOR_MANUAL_OUTREACH'
    out['selected_channel']=chat[0] if chat else None
    return out

def test_complete(test):
    required=['query','platform','model','started_at','completed_at','language','region','raw_response','artifact_path','session_scope']
    return test.get('status')=='COMPLETE' and all(test.get(k) for k in required) and test.get('completion_verified') is True

def permit_content(permission, *, public=False, anonymized=False):
    if public:return permission.get('scope')=='PUBLIC_APPROVED' and bool(permission.get('approval_evidence'))
    if anonymized:return permission.get('scope') in {'ANONYMIZED','PUBLIC_APPROVED'} and permission.get('reidentification_review')=='PASS'
    return permission.get('scope') in {'PRIVATE','ANONYMIZED','PUBLIC_APPROVED'}

def stage_counts(rows):
    """Current-state inventory, not a cumulative funnel and not historical sends."""
    return dict(Counter(r.get('stage','UNKNOWN') for r in rows))

def source_yield(rows, *, elapsed_seconds=None):
    n=len(rows);keys={r.get('entity_id') for r in rows if r.get('entity_id')}
    ready=sum(r.get('stage')=='READY_FOR_MANUAL_OUTREACH' for r in rows)
    counts={'raw':n,'unique_ids':len(keys),'ready':ready}
    return {**counts,'ready_per_100_raw':100*ready/n if n else None,
            'research_minutes_per_ready':elapsed_seconds/60/ready if ready and elapsed_seconds is not None else None,
            'action':'PAUSE_EXPANSION_REVIEW_SOURCE' if n>=30 and ready==0 else 'SMALL_SAMPLE_REVIEW'}

def allocate(rows):
    """Output one entity once, enforce 4:1 quotas and second dedup before release."""
    result=[];seen=set();counts=Counter()
    for row in sorted(rows,key=lambda r:r.get('score',0),reverse=True):
        if row.get('stage')!='READY_FOR_MANUAL_OUTREACH':continue
        keys=identity_keys(row);ch=row.get('selected_channel')
        if not keys or keys&seen or ch not in TARGETS['total'] or counts[ch]>=TARGETS['total'][ch]:continue
        result.append(row);seen.update(keys);counts[ch]+=1
    return {'rows':result,'actual':dict(counts),'gaps':{ch:target-counts[ch] for ch,target in TARGETS['total'].items()},'targets':TARGETS}

def audit_run(payload):
    dossiers={d['industry_id']:d for d in payload.get('dossiers',[])}
    rows=[qualify(r,payload.get('history',[]),dossiers.get(r.get('industry_id'),{})) for r in payload.get('rows',[])]
    return {'schema_version':'2.1','run_id':payload['run_id'],'inventory':stage_counts(rows),
            'rows':rows,'release':allocate(rows),'note':'No messages sent or public content published.'}
