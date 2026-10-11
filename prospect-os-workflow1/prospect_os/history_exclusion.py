"""Exclude previously used businesses before stratified RAW sampling."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from prospect_os.sample_lock import load_lock


def _domain(value):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        parsed = urlsplit(value if '://' in value else '//' + value)
        return (parsed.hostname or '').casefold().strip('.').removeprefix('www.')
    except ValueError:
        return ''


def _name_hash(value):
    name = unicodedata.normalize('NFKC', str(value or '')).casefold()
    name = ' '.join(re.findall(r'\w+', name, flags=re.UNICODE))
    return hashlib.sha256(name.encode('utf-8')).hexdigest() if name else ''


def _keys(row):
    return {
        'identity_key': str(row.get('identity_key') or '').strip().casefold(),
        'source_id': str(row.get('source_id') or '').strip().casefold(),
        'normalized_domain': _domain(row.get('website_url') or row.get('domain') or row.get('canonical_domain') or row.get('website')),
        'company_name_hash': str(row.get('company_name_hash') or '').strip().casefold()
                             or _name_hash(row.get('company_name') or row.get('name')),
    }


def _records(path, category):
    if category == 'previous_sample_lock':
        return [item['record'] for item in load_lock(path)['samples']]
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(payload, dict):
        for key in ('records', 'companies', 'history', 'contacted'):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError(f'history source must contain a JSON array: {path}')
    rows = []
    for row in payload:
        if isinstance(row, str):
            row = {'company_name': row}
        if not isinstance(row, dict):
            raise ValueError(f'invalid history record in {path}')
        rows.append(row.get('company') if isinstance(row.get('company'), dict) else row)
    return rows


def exclude_history(raw, sources):
    """Return (eligible, audit rows), with the matching historical file recorded."""
    index = {field: {} for field in ('identity_key', 'source_id', 'normalized_domain', 'company_name_hash')}
    for category, path in sources:
        for record in _records(path, category):
            for field, key in _keys(record).items():
                if key:
                    index[field].setdefault(key, f'{category}:{path}')
    eligible, excluded = [], []
    for row in raw:
        keys = _keys(row)
        match = next(((field, index[field][keys[field]]) for field in index
                      if keys[field] and keys[field] in index[field]), None)
        if match:
            excluded.append({'company_name': row.get('company_name'),
                             'identity_key': row.get('identity_key'),
                             'exclusion_reason': match[0],
                             'matched_history_source': match[1]})
        else:
            eligible.append(row)
    return eligible, excluded
