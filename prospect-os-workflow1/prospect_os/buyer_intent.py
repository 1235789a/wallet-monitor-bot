"""Incremental buyer-intent mode for Workflow 1; evidence scores are not probabilities."""
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from workflow1_daily import (DISCOVERY_CHANNELS, normalize_domain,
                             normalize_company_name, ensure_v2_schema, public_url)

WEIGHTS = {'acquisition_investment': 25, 'buyer_value': 15, 'visibility_gap': 25,
           'decision_access': 15, 'delivery_fit': 10, 'recent_activity': 8, 'usdt': 2}
STAGES = 'RAW QUALIFIED P0 AUDITED CONTACTED REPLIED INTERESTED OFFERED PAID DELIVERED CASE_STUDY RECURRING LOST'.split()
LOST_REASONS = {'No Reply', 'Wrong Contact', 'No Need', 'No Budget', "Doesn't Understand GEO",
                'No Trust', 'Price', 'Already Has Provider', 'Timing', 'Other'}
B2B_ICP = {'web3_agency', 'blockchain_agency', 'exchange_development', 'token_development',
           'defi_development', 'web3_saas', 'ai_software_agency', 'b2b_digital_service'}
LOCAL_ICP = {'independent_tobacco', 'independent_vape', 'independent_alcohol',
             'independent_bar', 'independent_adult_retail'}
PRIMARY = B2B_ICP | LOCAL_ICP
TOUCHPOINTS = {'AUDIT_SENT', 'AUDIT_VIEWED', 'SALES_CONVERSATION', 'REFERRAL'}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def evidence_ok(e):
    if not (isinstance(e, dict) and e.get('label') in {'observed', 'self_reported'}
            and bool(e.get('claim')) and public_url(e.get('source_url', ''))):
        return False
    try:
        datetime.fromisoformat(e.get('checked_at', '').replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False
    return True


def contact_key(c):
    channel, value = c.get('channel', ''), c.get('value', '').strip()
    if channel == 'email' and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        return channel + ':' + value.casefold()
    if channel in {'whatsapp', 'telegram', 'founder_social'} and public_url(value):
        h = normalize_domain(value)
        if channel == 'whatsapp' and h not in {'wa.me', 'api.whatsapp.com', 'web.whatsapp.com'}:
            return ''
        if channel == 'telegram' and h not in {'t.me', 'telegram.me'}:
            return ''
        if channel == 'telegram' and c.get('route_type') not in {'person', 'business_chat', 'phone_chat'}:
            return ''  # Broadcast channels are not decision-maker chats.
        if channel == 'founder_social' and h not in {
                'linkedin.com', 'x.com', 'twitter.com', 'facebook.com', 'instagram.com'}:
            return ''
        return channel + ':' + value.casefold().rstrip('/')
    return ''


def audit_queries(row):
    queries = row.get('buyer_queries', [])
    valid = []
    for q in queries:
        text = q.get('query', '').strip()
        if (q.get('reviewed') is True and q.get('service_relevance') and
                q.get('buyer_intent') is True and text and
                normalize_company_name(row['company_name']) not in normalize_company_name(text)):
            valid.append(text)
    return list(dict.fromkeys(valid))


def validate_visibility(v, queries):
    if v.get('query') not in queries or not v.get('tested_at') or not v.get('artifact'):
        return False
    platform = v.get('platform')
    if platform not in {'web_search_tool', 'google', 'chatgpt', 'gemini', 'perplexity'}:
        return False
    if platform != 'web_search_tool' and v.get('method') != 'direct_platform_test':
        return False
    return (v.get('status') == 'tested' and isinstance(v.get('returned_urls'), list)
            and bool(v['returned_urls']) and v.get('prospect_presence') in {'present', 'not_in_returned_results'}
            and bool(v.get('competitors')) and bool(v.get('scope')))


def qualify(row, today):
    missing, hard = [], []
    if row.get('discovery_channel') not in DISCOVERY_CHANNELS:
        hard.append('off_search_provenance_missing')
    if not public_url(row.get('discovery_source_url', '')) or normalize_domain(row.get('discovery_source_url', '')) == normalize_domain(row.get('website_url', '')):
        hard.append('independent_discovery_source_missing')
    if row.get('icp') not in PRIMARY:
        missing.append('secondary_pool_or_unverified_icp')
    for field in ('company_verified', 'small_team_verified', 'non_chain_verified'):
        if not evidence_ok(row.get(field)):
            missing.append(field)
    if row.get('chain') is True or row.get('do_not_contact') is True:
        hard.append('chain_or_dnc')
    if row.get('icp') in LOCAL_ICP:
        location_count = row.get('location_count')
        if not evidence_ok(row.get('location_count_verified')):
            missing.append('verified_location_count')
        if not isinstance(location_count, int) or location_count < 1:
            missing.append('valid_location_count')
        elif location_count > 2:
            hard.append('local_business_has_more_than_two_locations')
    contacts = [c for c in row.get('contacts', []) if contact_key(c) and evidence_ok(c.get('evidence'))]
    if not contacts:
        missing.append('official_contact_source')
    # Public publication of a contact is not registration, deliverability or reply verification.
    queries = audit_queries(row)
    if not 5 <= len(queries) <= 10:
        missing.append('five_to_ten_reviewed_buyer_queries')
    visibility = [v for v in row.get('visibility', []) if validate_visibility(v, queries)]
    tested_queries = {v['query'] for v in visibility}
    if len(tested_queries) < 5:
        missing.append('tested_buyer_query_competitor_gap')
    gaps = [g for g in row.get('gaps', []) if evidence_ok(g)]
    if len(gaps) < 3:
        missing.append('three_evidenced_gaps')
    activity = row.get('recent_activity', {})
    try:
        age = (today - date.fromisoformat(activity.get('occurred_at', '')[:10])).days
    except ValueError:
        age = 999
    if not evidence_ok(activity) or not 0 <= age <= 30:
        missing.append('dated_activity_within_30_days')
    scores = {}
    for key, maximum in WEIGHTS.items():
        signal = row.get('signals', {}).get(key, {})
        level = signal.get('level', 0)
        scores[key] = round(maximum * level / 2) if level in (1, 2) and evidence_ok(signal) else 0
    if len(tested_queries) < 5:
        scores['visibility_gap'] = 0
    if not contacts:
        scores['decision_access'] = 0
    if 'dated_activity_within_30_days' in missing:
        scores['recent_activity'] = 0
    if scores['acquisition_investment'] == 0:
        missing.append('buying_pain_evidence')
    if not row.get('outreach') or not row.get('recommended_first_fix'):
        missing.append('outreach_readiness')
    total = sum(scores.values())
    status = 'QUARANTINED' if hard else ('P0' if not missing and total >= 70 else 'REVIEW_REQUIRED')
    return {**row, 'qualification': status, 'score': total, 'score_breakdown': scores,
            'missing': missing, 'hard_failures': hard,
            'reply_probability': None, 'audit_acceptance_probability': None, 'purchase_probability': None,
            'probability_status': 'insufficient_sales_outcomes',
            'real_reply': 'not_tested', 'purchase_intent': 'unconfirmed',
            'tested_query_count': len(tested_queries)}


def ensure_buyer_schema(conn):
    ensure_v2_schema(conn)
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS buyer_assessments (
        domain TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS buyer_events (
        event_id TEXT PRIMARY KEY, domain TEXT NOT NULL, stage TEXT NOT NULL,
        occurred_at TEXT NOT NULL, evidence_ref TEXT NOT NULL, details TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS buyer_touchpoints (
        event_id TEXT PRIMARY KEY, domain TEXT NOT NULL, event_kind TEXT NOT NULL,
        occurred_at TEXT NOT NULL, evidence_ref TEXT NOT NULL, details TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS buyer_payments (
        invoice_id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, domain TEXT NOT NULL,
        amount REAL NOT NULL, currency TEXT NOT NULL, evidence_ref TEXT NOT NULL);
    ''')


def record_event(conn, event):
    stage = event.get('stage')
    if stage not in STAGES or not event.get('event_id') or not event.get('evidence_ref') or not event.get('occurred_at'):
        raise ValueError('event requires valid stage, stable ID, timestamp and evidence reference')
    try:
        datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('event timestamp must be ISO-8601') from exc
    if stage == 'LOST' and event.get('lost_reason') not in LOST_REASONS:
        raise ValueError('LOST requires controlled lost_reason')
    if stage == 'PAID' and not (event.get('payment_verified') is True and event.get('invoice_id') and event.get('amount', 0) > 0 and event.get('currency')):
        raise ValueError('PAID requires verified, attributed invoice/payment amount and currency')
    domain = normalize_domain(event['website_url'])
    if not conn.execute('SELECT 1 FROM buyer_assessments WHERE domain=?', (domain,)).fetchone():
        raise ValueError('unknown prospect')
    prior = {r[0] for r in conn.execute('SELECT stage FROM buyer_events WHERE domain=?', (domain,))}
    requirements = {'QUALIFIED': {'RAW'}, 'P0': {'QUALIFIED'}, 'AUDITED': {'P0'},
                    'CONTACTED': {'P0'}, 'REPLIED': {'CONTACTED'}, 'INTERESTED': {'REPLIED'},
                    'OFFERED': {'INTERESTED'}, 'PAID': {'OFFERED'}, 'DELIVERED': {'PAID'},
                    'CASE_STUDY': {'DELIVERED'}, 'RECURRING': {'DELIVERED'}}
    if not requirements.get(stage, set()).issubset(prior):
        raise ValueError('missing preceding funnel evidence')
    if stage == 'AUDITED':
        payload = json.loads(conn.execute('SELECT payload FROM buyer_assessments WHERE domain=?', (domain,)).fetchone()[0])
        if payload.get('tested_query_count', 0) < 5:
            raise ValueError('AUDITED requires at least five actually tested buyer queries')
    serialized = json.dumps(event, sort_keys=True)
    existing = conn.execute('SELECT domain,stage,details FROM buyer_events WHERE event_id=?',
                            (event['event_id'],)).fetchone()
    if existing and existing != (domain, stage, serialized):
        raise ValueError('event_id already exists with different evidence')
    if not existing:
        conn.execute('INSERT INTO buyer_events VALUES(?,?,?,?,?,?)',
                     (event['event_id'], domain, stage, event['occurred_at'],
                      event['evidence_ref'], serialized))
    if stage == 'PAID':
        payment = (event['event_id'], domain, float(event['amount']),
                   event['currency'], event['evidence_ref'])
        prior_payment = conn.execute(
            'SELECT event_id,domain,amount,currency,evidence_ref FROM buyer_payments WHERE invoice_id=?',
            (str(event['invoice_id']),)).fetchone()
        if prior_payment and prior_payment != payment:
            raise sqlite3.IntegrityError('invoice_id already attributed to another payment event')
        if not prior_payment:
            conn.execute('INSERT INTO buyer_payments VALUES(?,?,?,?,?,?)',
                         (str(event['invoice_id']),) + payment)


def record_touchpoint(conn, event):
    if event.get('event_kind') not in TOUCHPOINTS:
        raise ValueError('invalid buyer touchpoint')
    domain = normalize_domain(event.get('website_url', ''))
    if not conn.execute('SELECT 1 FROM buyer_assessments WHERE domain=?', (domain,)).fetchone():
        raise ValueError('unknown prospect')
    if not event.get('event_id') or not event.get('occurred_at') or not event.get('evidence_ref'):
        raise ValueError('touchpoint requires ID, timestamp and evidence reference')
    datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
    serialized = json.dumps(event, sort_keys=True)
    existing = conn.execute('SELECT domain,event_kind,details FROM buyer_touchpoints WHERE event_id=?',
                            (event['event_id'],)).fetchone()
    if existing and existing != (domain, event['event_kind'], serialized):
        raise ValueError('event_id already exists with different evidence')
    if not existing:
        conn.execute('INSERT INTO buyer_touchpoints VALUES(?,?,?,?,?,?)',
                     (event['event_id'], domain, event['event_kind'], event['occurred_at'],
                      event['evidence_ref'], serialized))


def funnel_report(conn):
    counts = dict(conn.execute('SELECT stage,COUNT(DISTINCT domain) FROM buyer_events GROUP BY stage'))
    losses = Counter()
    revenue = Counter()
    for stage, details in conn.execute("SELECT stage,details FROM buyer_events WHERE stage IN ('PAID','LOST')"):
        e = json.loads(details)
        if stage == 'LOST': losses[e['lost_reason']] += 1
        else: revenue[e['currency']] += e['amount']
    touches = dict(conn.execute('SELECT event_kind,COUNT(DISTINCT domain) FROM buyer_touchpoints GROUP BY event_kind'))
    rates = {}
    for name, d, n in [
            ('reply', counts.get('CONTACTED', 0), counts.get('REPLIED', 0)),
            ('audit_view', touches.get('AUDIT_SENT', 0), touches.get('AUDIT_VIEWED', 0)),
            ('sales_conversation', counts.get('REPLIED', 0), touches.get('SALES_CONVERSATION', 0)),
            ('purchase', counts.get('OFFERED', 0), counts.get('PAID', 0))]:
        rates[name] = {'denominator': d, 'numerator': n, 'observed_rate': n / d if d else None,
                       'predictive_probability': None, 'note': 'Cohort rates only; no calibrated individual probability'}
    return {'stage_counts': {s: counts.get(s, 0) for s in STAGES}, 'lost_reasons': dict(losses),
            'touchpoint_counts': {s: touches.get(s, 0) for s in sorted(TOUCHPOINTS)},
            'revenue_by_currency': dict(revenue), 'rates': rates,
            'targets_14_days': {'RAW': 350, 'P0': 30, 'AUDITED': 15, 'INTERESTED': 8, 'PAID': 3},
            'goal_rmb_5_months': 100000}


def execute(source, day, db_path, output_dir, history_path=None, commit=False):
    rows = json.loads(Path(source).read_text())
    today = date.fromisoformat(day)
    history = json.loads(Path(history_path).read_text()) if history_path else []
    if commit:
        conn = sqlite3.connect(db_path)
    else:
        conn = sqlite3.connect(':memory:')
        if Path(db_path).exists():
            source_conn = sqlite3.connect(db_path)
            source_conn.backup(conn)
            source_conn.close()
    ensure_buyer_schema(conn)
    old_domains = {r[0] for r in conn.execute('SELECT canonical_domain FROM companies')}
    old_domains.update(r[0] for r in conn.execute('SELECT domain FROM buyer_assessments'))
    old_contacts = {f'{r[0]}:{r[1]}'.casefold() for r in conn.execute('SELECT channel,normalized_value FROM contacts')}
    for r in history:
        old_domains.add(normalize_domain(r.get('website_url', '')))
        old_contacts.update(contact_key(c) for c in r.get('contacts', []) if contact_key(c))
    seen, seen_contacts, decisions = set(), set(), []
    for r in rows:
        d = normalize_domain(r.get('website_url', ''))
        keys = {contact_key(c) for c in r.get('contacts', []) if contact_key(c)}
        result = qualify(r, today)
        if (d and (d in seen or d in old_domains)) or keys & (seen_contacts | old_contacts):
            result.update(qualification='DUPLICATE', missing=['domain_or_contact_duplicate'])
        if d: seen.add(d)
        seen_contacts.update(keys)
        decisions.append(result)
        if commit and d and result['qualification'] != 'DUPLICATE':
            conn.execute('INSERT INTO buyer_assessments VALUES(?,?,?) ON CONFLICT(domain) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at', (d,json.dumps(result),utcnow()))
            for stage in ['RAW'] + (['QUALIFIED', 'P0'] if result['qualification']=='P0' else []):
                record_event(conn, {'event_id':f'{d}:{stage}', 'website_url':r['website_url'], 'stage':stage,
                                   'occurred_at':utcnow(), 'evidence_ref':str(source)})
    conn.commit()
    ranked = sorted((r for r in decisions if r['qualification']=='P0'),
                    key=lambda x:(-x['score'],x['company_name']))
    b2b = [r for r in ranked if r.get('icp') in B2B_ICP][:10]
    local = [r for r in ranked if r.get('icp') in LOCAL_ICP][:10]
    selected = b2b + local
    raw_ids = {r.get('directory_id') or r.get('source_id') or
               (r.get('company_name','').casefold(), r.get('discovery_source_url','')) for r in rows}
    summary = {'raw_records_supplied':len(rows), 'unique_website_domains':len(seen),
               'decisions':dict(Counter(r['qualification'] for r in decisions)),
               'missing_reasons':dict(Counter(k for r in decisions for k in r['missing'])),
               'selected':len(selected), 'selected_mix':{'b2b':len(b2b),'local':len(local)},
               'shortfall':max(0,20-len(selected)),
               'raw_pool_minimum_met':len(raw_ids)>=350,
               'history_coverage':'supplied_export_and_local_db' if history_path else 'local_db_only_incomplete',
               'outreach_sent':False, 'funnel':funnel_report(conn)}
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    for name,data in [('decisions',decisions),('top20',selected),('top5',selected[:5]),('summary',summary)]:
        (output_dir/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    conn.close()
    return summary
