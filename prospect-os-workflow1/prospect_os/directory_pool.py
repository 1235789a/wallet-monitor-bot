"""Off-search directory ingestion. Listings are discovery evidence, never P0 proof."""
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from workflow1_company_screening import TextAndLinksParser, fetch_html
from workflow1_daily import normalize_domain


def parse_clutch(body, source_url):
    rows = []
    for block in re.split(r'data-clutch-pid="', body)[1:]:
        name = re.search(r'data-title="([^"]+)"', block)
        if not name:
            continue
        parser = TextAndLinksParser()
        parser.feed(block)
        text = ' '.join(parser.text_parts)
        profile = next((u.split('#')[0] for u in parser.links if '/profile/' in u), '')
        if profile.startswith('/'):
            profile = 'https://clutch.co' + profile
        website = ''
        for link in parser.links:
            target = parse_qs(urlsplit(html.unescape(link)).query).get('u', [''])[0]
            if target.startswith('http') and not normalize_domain(target).endswith('clutch.co'):
                p = urlsplit(target)
                website = urlunsplit((p.scheme, p.netloc, p.path or '/', '', ''))
                break
        size = re.search(r'\b(\d[\d,]*)\s*-\s*(\d[\d,]*)\b', text)
        rows.append({'company_name': html.unescape(name.group(1)),
                     'directory_id': block.split('"', 1)[0],
                     'website_url': website, 'profile_url': profile,
                     'discovery_channel': 'industry_directory',
                     'discovery_source_url': source_url,
                     'directory_text': text[:18000],
                     'directory_team_range': size.group(0) if size else '',
                     'discovered_at': datetime.now(timezone.utc).isoformat(),
                     'discovery_bias': 'Directory membership and paid placement bias; not population-random'})
    return rows


def collect(urls, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records, pages = {}, []
    # Sequential within this host: avoid 48 concurrent requests to one directory.
    for url in urls:
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        cache = output_dir / (key + '.html')
        try:
            if cache.exists():
                body = cache.read_text()
            else:
                body, _, _ = fetch_html(url, timeout=25, max_bytes=8_000_000)
                cache.write_text(body)
            rows = parse_clutch(body, url)
            for row in rows:
                records.setdefault(row['directory_id'], row)
            pages.append({'url': url, 'records': len(rows), 'sha256': hashlib.sha256(body.encode()).hexdigest()})
        except Exception as exc:
            pages.append({'url': url, 'error': str(exc)})
        (output_dir / 'raw.json').write_text(json.dumps(list(records.values()), ensure_ascii=False, indent=2))
        (output_dir / 'manifest.json').write_text(json.dumps(pages, indent=2))
        print(json.dumps({'url': url, 'raw_unique_directory_ids': len(records), 'last_page': pages[-1]}), flush=True)
    return list(records.values())
