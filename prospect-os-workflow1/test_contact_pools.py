import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prospect_os.sampling import WEB3, AI_B2B, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL
from prospect_os.contact_pools import classify_pool, peer_agency_reason, screen_raw_pool
from prospect_os.website_resolution import resolve_website, resolve_website_pool
from prospect_os.source_yield import build_source_yield
from prospect_os.prelock_preflight import preflight_record
from research_buyer_batch import run_batch


class ContactPoolTests(unittest.TestCase):
    @staticmethod
    def evidence(row, *, reject=False):
        track_b = row.get('industry_hint') in {'vape', 'wine', 'adult retail shop'}
        query = {'query': 'best blockchain implementation company' if not track_b else 'best local vape shop',
                 'tested': True, 'buyer_intent': True,
                 'competitor_evidence': 'Observed relevant competitor or substitute',
                 'evidence_urls': [row['website_url'] + '/market']}
        dims = {'buyer_intent': 15, 'geo_opportunity': 10,
                'decision_maker_reachability': 12, 'business_quality': 10,
                'active_customer_acquisition': 6, 'competitive_pressure': 3,
                'evidence_completeness': 4}
        rating_assessment = {name: {'score': score, 'reason': f'Fixture evidence for {name}',
            'evidence': [{'url': row['website_url'] + '/market',
                'checked_at': '2026-09-29T00:00:00Z', 'label': 'observed',
                'claim': f'Fixture supports {name}'}]} for name, score in dims.items()}
        return {'business_real': not reject, 'active_business': True, 'vertical_match': True,
                'business_evidence_url': row['website_url'] + '/about',
                'evidence_urls': [row['website_url'] + '/about'],
                **({'ownership_evidence_url': row['website_url'] + '/about',
                    'location_evidence_url': row['website_url'] + '/locations'} if track_b else
                   {'b2b_evidence_url': row['website_url'] + '/about',
                    'team_evidence_url': row['website_url'] + '/team',
                    'service_evidence_url': row['website_url'] + '/services'}),
                'buyer_queries': [query], 'rating_assessment': rating_assessment,
                **({'chain': False, 'locations': 1, 'ownership_type': 'independent'} if track_b else
                   {'is_b2b': True, 'not_enterprise': True,
                    'small_team_evidence': 'Founder and small team listed', 'purchasable_service': True})}

    def test_peer_agencies_are_excluded_without_excluding_software_products(self):
        self.assertEqual(peer_agency_reason({
            'company_name': 'Bright Reach',
            'directory_text': 'A digital marketing agency specializing in paid ads.',
        }), 'digital_marketing_agency')
        self.assertEqual(peer_agency_reason({
            'company_name': 'Bright Reach SaaS',
            'directory_text': 'A subscription software product for finance teams.',
        }), '')

    def test_channels_need_official_link_evidence_and_email_needs_quality_review(self):
        basic = {'contact_enrichment_status': 'completed',
                 'website_url': 'https://business.example'}
        email = {'channel': 'email', 'value': 'sales@example.com',
                 'evidence': {'source_url': 'https://business.example/contact'}}
        self.assertEqual(classify_pool({**basic, 'contacts': [email]})[0], 'email_review')
        self.assertEqual(classify_pool({**basic, 'contacts': [email],
            'prelock_quality_review': {'reviewed': True, 'rating': 'high',
                'claim': 'Active commercial business', 'source_url': 'https://business.example/about'}})[0], 'email')
        self.assertEqual(classify_pool({**basic, 'contacts': [
            {'channel': 'phone', 'value': '+12345678', 'evidence': email['evidence']}]})[0], 'review')
        self.assertEqual(classify_pool({**basic, 'contacts': [
            {'channel': 'telegram', 'value': 'https://t.me/example', 'route_type': 'group_or_channel',
             'evidence': email['evidence']}]})[0], 'review')
        self.assertEqual(classify_pool({**basic, 'contacts': [
            {'channel': 'whatsapp', 'value': 'https://wa.me?text=hello',
             'evidence': email['evidence']}]})[0], 'review')
        self.assertEqual(classify_pool({**basic, 'contacts': [
            {'channel': 'telegram', 'value': 'https://telegram.me/share/url?url=https://business.example',
             'route_type': 'group_or_channel', 'evidence': email['evidence']}]})[0], 'review')

    def test_raw_pool_screened_before_lock_and_email_kept_separate(self):
        labels = {WEB3: 'blockchain', AI_B2B: 'software', VAPE_TOBACCO: 'vape',
                  ALCOHOL_BAR: 'wine', ADULT_RETAIL: 'adult retail shop'}
        rows = []
        for vertical, label in labels.items():
            for i in range(12):
                row = {'source_id': f'{vertical}:{i}', 'company_name': f'{vertical} {i}',
                       'website_url': f'https://{vertical}-{i}.example', 'industry_hint': label,
                       'city_hint': f'{vertical}-city-{i}', 'source_name': f'source-{i%5}'}
                if i == 10:
                    row['prelock_quality_review'] = {'reviewed': True, 'rating': 'high',
                        'claim': 'Verified active company', 'source_url': row['website_url']}
                rows.append(row)
        def screen(row):
            i = int(row['source_id'].split(':')[-1])
            channel = 'whatsapp' if i < 5 else 'telegram' if i < 9 else 'email' if i < 11 else 'phone'
            value = ('https://wa.me/123456789' if channel == 'whatsapp' else
                     'https://t.me/company' if channel == 'telegram' else
                     'hello@company.example' if channel == 'email' else '+12345678')
            return {**row, 'contact_enrichment_status': 'completed', 'pages_checked': [row['website_url']],
                'prelock_assessment': self.evidence(row), 'contacts': [{
                'channel': channel, 'value': value,
                'route_type': 'direct_chat' if channel == 'telegram' else 'business_chat',
                'evidence': {'source_url': row['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            options = dict(limit=30, seed=3, output=root/'enriched.json',
                           summary_path=root/'summary.json', lock_path=root/'sampled-lock.json')
            enriched, summary = run_batch(rows, **options, screen_fn=screen,
                enrich_fn=lambda row: {**row, 'research_status': 'pages_collected'})
            self.assertEqual(summary['raw_pool'], 60)
            self.assertEqual(summary['pool_counts'], {'chat': 45, 'email': 5,
                'email_review': 5, 'review': 5, 'peer_excluded': 0,
                'prelock_pass': 45, 'prelock_review': 0, 'prelock_reject': 5})
            self.assertEqual(len(enriched), 30)
            self.assertEqual(summary['whatsapp_selected'], 24)
            self.assertEqual(summary['selected_by_contact_channel'], {'whatsapp': 24, 'telegram': 6})
            self.assertFalse(summary['outreach_ready'])
            self.assertEqual(len(json.loads((root/'prelock-email.json').read_text())), 5)
            self.assertEqual(len(json.loads((root/'prelock-email_review.json').read_text())), 5)
            self.assertTrue(all(r['prelock_pool'] == 'chat' for r in enriched))
            self.assertEqual(summary['prelock_pass_count'], 45)
            self.assertEqual(summary['reserve_pool_pass_count'], 45)
            self.assertTrue(summary['sample_lock_feasible'])
            self.assertEqual(summary['track_counts'], {'track_a': 15, 'track_b': 15})
            self.assertTrue((root/'source-yield.json').exists())
            again, _ = run_batch(rows[:1], **options,
                screen_fn=lambda _: self.fail('existing lock must not rescreen'),
                website_resolver_fn=lambda _: self.fail('existing lock must not resolve websites'),
                enrich_fn=lambda _: self.fail('already enriched row must not change'))
            self.assertEqual(again, enriched)

    def test_shortfall_writes_pools_without_freezing_an_unusable_cohort(self):
        rows = [{'source_id': f'web3:{i}', 'company_name': f'Company {i}',
                 'website_url': f'https://company-{i}.example', 'industry_hint': 'blockchain',
                 'city_hint': f'city-{i}'} for i in range(10)]
        def screen(row):
            i = int(row['source_id'].split(':')[-1])
            return {**row, 'contact_enrichment_status': 'completed', 'pages_checked': [row['website_url']],
                'prelock_assessment': self.evidence(row), 'contacts': [{
                'channel': 'whatsapp' if i < 2 else 'email',
                'value': 'https://wa.me/12345678' if i < 2 else 'info@company.example',
                'evidence': {'source_url': row['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'prelock sample infeasible'):
                run_batch(rows, limit=5, seed=1, output=root/'enriched.json',
                          summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                          screen_fn=screen, min_whatsapp=4)
            self.assertFalse((root/'sampled-lock.json').exists())
            self.assertEqual(json.loads((root/'summary.json').read_text())['whatsapp_shortfall'], 2)
            self.assertEqual(len(json.loads((root/'prelock-email_review.json').read_text())), 8)

    def test_formal_thirty_does_not_lock_before_reserve_reaches_42(self):
        labels = [(WEB3, 'blockchain', 8), (AI_B2B, 'software', 7),
                  (VAPE_TOBACCO, 'vape', 5), (ALCOHOL_BAR, 'wine', 5),
                  (ADULT_RETAIL, 'adult retail shop', 5)]
        rows = []
        for vertical, label, count in labels:
            for i in range(count):
                row = {'source_id': f'{vertical}:{i}', 'identity_key': f'{vertical}:{i}',
                       'company_name': f'{vertical} candidate {i}',
                       'website_url': f'https://{vertical}-{i}.example',
                       'industry_hint': label, 'city_hint': f'{vertical}-city-{i}',
                       'source_name': f'source-{vertical}-{i}'}
                rows.append(row)

        def screen(row):
            route = 'telegram' if row['source_id'].startswith(WEB3) and row['source_id'].endswith(tuple(f':{i}' for i in range(6))) else 'whatsapp'
            return {**row, 'contact_enrichment_status': 'completed',
                    'pages_checked': [row['website_url']],
                    'prelock_assessment': self.evidence(row),
                    'contacts': [{'channel': route,
                        'value': 'https://t.me/directuser' if route == 'telegram' else 'https://wa.me/12345678',
                        'route_type': 'direct_chat' if route == 'telegram' else 'business_chat',
                        'evidence': {'source_url': row['website_url']}}]}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'reserve=30/42'):
                run_batch(rows, limit=30, seed=20260907, output=root/'enriched.json',
                          summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                          screen_fn=screen)
            summary = json.loads((root/'summary.json').read_text())
            self.assertEqual(summary['reserve_pool_shortfall'], 12)
            self.assertFalse((root/'sampled-lock.json').exists())

    def test_directory_outbound_link_resolves_official_website(self):
        row = {'company_name': 'Small Vape', 'profile_url': 'https://directory.example/listing/1'}
        resolved = resolve_website(row, respect_robots=False,
            fetcher=lambda url: ('<a href="https://smallvape.example/">Visit Website</a>', url))
        self.assertEqual(resolved['website_url'], 'https://smallvape.example/')
        self.assertEqual(resolved['website_discovery_method'], 'directory_outbound_link')
        self.assertEqual(resolved['website_source_url'], row['profile_url'])
        self.assertEqual(resolved['website_resolution_status'], 'resolved')
        self.assertTrue(resolved['website_resolved_at'])

    def test_search_engine_outbound_link_is_not_a_website(self):
        for host in ('www.google.com', 'www.google.co.uk', 'www.bing.com'):
            requested = []
            row = {'company_name': 'Small Vape', 'profile_url': 'https://directory.example/listing/1'}
            resolved = resolve_website(row, respect_robots=False, fetcher=lambda url: (
                requested.append(url) or f'<a href="https://{host}/search?q=small+vape">Official Site</a>', url))
            self.assertEqual(resolved['website_resolution_status'], 'unresolved')
            self.assertEqual(resolved['website_absence_status'], 'unknown')
            self.assertEqual(requested, [row['profile_url']])

    def test_source_record_website_field_is_used_without_external_search(self):
        row = {'company_name': 'Company', 'discovery_source_url': 'https://directory.example/list',
               'raw_source_record': {'website': 'https://company.example/'} }
        resolved = resolve_website(row, respect_robots=False,
            fetcher=lambda _: self.fail('source record already contains the explicit website field'))
        self.assertEqual(resolved['website_url'], 'https://company.example/')
        self.assertEqual(resolved['website_discovery_method'], 'source_record_website_field')
        self.assertEqual(resolved['website_source_url'], row['discovery_source_url'])

    def test_directory_anchor_showing_domain_can_resolve_website(self):
        row = {'company_name': 'Company', 'profile_url': 'https://directory.example/list'}
        resolved = resolve_website(row, respect_robots=False,
            fetcher=lambda url: ('<a href="https://company.example/">www.company.example</a>', url))
        self.assertEqual(resolved['website_url'], 'https://company.example/')
        self.assertEqual(resolved['website_discovery_method'], 'directory_outbound_link')

    def test_website_resolution_cache_avoids_revisiting_source_pages(self):
        row = {'source_id': 'directory:1', 'company_name': 'Company',
               'discovery_source_url': 'https://directory.example/list'}
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / 'website-resolution.jsonl'
            first = resolve_website_pool([row], cache_path=cache, workers=1,
                resolver_fn=lambda item: {**item, 'website_resolution_status': 'unresolved',
                    'website_absence_status': 'unknown', 'website_resolution_errors': []})
            second = resolve_website_pool([row], cache_path=cache, workers=1,
                resolver_fn=lambda _: self.fail('cached source page must not be fetched again'))
            self.assertEqual(first, second)

    def test_website_resolution_cache_keeps_new_source_metadata(self):
        base = {'source_id': 'directory:2', 'company_name': 'Company',
                'discovery_source_url': 'https://directory.example/list'}
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / 'website-resolution.jsonl'
            resolve_website_pool([base], cache_path=cache, workers=1,
                resolver_fn=lambda item: {**item, 'website_resolution_status': 'unresolved',
                    'website_absence_status': 'unknown', 'website_resolution_errors': []})
            current = {**base, 'source_name': 'Current Directory', 'country': 'Brazil',
                       'sampling_vertical': 'alcohol_wine_bar'}
            reused = resolve_website_pool([current], cache_path=cache, workers=1,
                resolver_fn=lambda _: self.fail('cached source page must not be fetched again'))[0]
        self.assertEqual(reused['website_resolution_status'], 'unresolved')
        self.assertEqual(reused['source_name'], 'Current Directory')
        self.assertEqual(reused['country'], 'Brazil')
        self.assertEqual(reused['sampling_vertical'], 'alcohol_wine_bar')

    def test_legacy_completed_contact_cache_is_reused_after_resolver_annotation(self):
        row = {'source_id': 'directory:1', 'company_name': 'Company',
               'website_url': 'https://company.example/', 'industry_hint': 'wine',
               'website_resolution_status': 'already_present',
               'source_name': 'Current Directory', 'country': 'Brazil'}
        old_row = {k: v for k, v in row.items() if k != 'website_resolution_status'}
        cached = {**old_row, 'contact_enrichment_status': 'completed',
                  'pages_checked': ['https://company.example/'], 'contacts': []}
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / 'prelock-screen.jsonl'
            cache.write_text(json.dumps({'key': 'legacy-key', 'row': cached}) + '\n')
            pools = screen_raw_pool([row], cache_path=cache,
                screen_fn=lambda _: self.fail('completed legacy cache must be reused'), workers=1)
        self.assertEqual(len(pools['review']), 1)
        self.assertEqual(pools['review'][0]['contact_enrichment_status'], 'completed')
        self.assertEqual(pools['review'][0]['source_name'], 'Current Directory')
        self.assertEqual(pools['review'][0]['country'], 'Brazil')

    def test_source_yield_counts_verified_chat_and_history(self):
        raw = [{'source_name': 'directory', 'source_dataset_url': 'https://directory.example/data',
                'country': 'PT', 'vertical': 'vape', 'website_url': 'https://vape.example'},
               {'source_name': 'directory', 'source_dataset_url': 'https://directory.example/data',
                'country': 'PT', 'vertical': 'vape'}]
        screened = [{'source_name': 'directory', 'source_dataset_url': 'https://directory.example/data',
            'country': 'PT', 'vertical': 'vape', 'website_url': 'https://vape.example',
            'website_resolution_status': 'already_present', 'contact_enrichment_status': 'completed',
            'prelock_pool': 'chat', 'prelock_status': 'PRELOCK_PASS',
            'contacts': [{'channel': 'whatsapp', 'value': 'https://wa.me/35112345678',
                'evidence': {'source_url': 'https://vape.example/contact'}}]},
            {'source_name': 'directory', 'source_dataset_url': 'https://directory.example/data',
             'country': 'PT', 'vertical': 'vape', 'website_resolution_status': 'unresolved',
             'contact_enrichment_status': 'prelock_ineligible', 'prelock_pool': 'review',
             'prelock_status': 'PRELOCK_REVIEW'}]
        result = build_source_yield(raw, [{'source_name': 'directory', 'source_dataset_url': 'https://directory.example/data',
            'country': 'PT', 'sampling_vertical': 'vape'}], screened)['groups'][0]
        self.assertEqual(result['raw_count'], 2)
        self.assertEqual(result['history_excluded'], 1)
        self.assertEqual(result['whatsapp_found'], 1)
        self.assertEqual(result['whatsapp_yield_rate'], 0.5)
        self.assertEqual(result['chat_yield_rate'], 0.5)
        self.assertEqual(result['website_fetch_success'], 1)
        self.assertEqual(result['website_unresolved'], 1)
        self.assertEqual(result['review_count'], 1)
        self.assertEqual(result['prelock_pass_count'], 1)
        self.assertEqual(result['prelock_review_count'], 1)
        self.assertEqual(result['prelock_pass_rate'], 0.5)

    def test_source_yield_uses_country_snapshot_provenance(self):
        result = build_source_yield([{'source_type': 'openwinemap_osm',
            'source_dataset_url': 'https://example.org/data/countries/PT.geojson',
            'sampling_vertical': 'alcohol_wine_bar'}], [], [])['groups'][0]
        self.assertEqual(result['country'], 'PT')

    def test_preflight_drafts_queries_but_never_treats_them_as_tested(self):
        row = {'company_name': 'Example Vape', 'industry_hint': 'vape', 'city_hint': 'Lisbon',
               'website_url': 'https://vape.example', 'contact_enrichment_status': 'completed',
               'pages_checked': ['https://vape.example'], 'contacts': [{
                   'channel': 'whatsapp', 'value': 'https://wa.me/35112345678',
                   'evidence': {'source_url': 'https://vape.example'}}]}
        result = preflight_record(row)
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(len(result['prelock_buyer_queries']), 2)
        self.assertTrue(all(q['status'] == 'suggested_only' and q['tested'] is False
                            for q in result['prelock_buyer_queries']))

    def test_fetch_failure_without_chat_stays_prelock_review(self):
        row = {'company_name': 'Unknown Vape', 'industry_hint': 'vape',
               'website_url': 'https://unknown.example', 'contact_enrichment_status': 'fetch_failed',
               'contacts': []}
        result = preflight_record(row)
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(result['prelock_reject_reasons'], [])
        self.assertIn('direct_chat_route_not_yet_verified', result['prelock_missing_evidence'])

    def test_age_gate_only_site_stays_prelock_review(self):
        row = {'company_name': 'Age Gate Retailer', 'industry_hint': 'tobacco',
               'website_url': 'https://retailer.example', 'contact_enrichment_status': 'completed',
               'pages_checked': ['https://retailer.example'], 'prelock_access_limited': True,
               'contacts': []}
        result = preflight_record(row)
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(result['prelock_reject_reasons'], [])

    def test_unclassified_industry_stays_review_instead_of_false_reject(self):
        row = {'company_name': 'Small Tech Provider', 'industry_hint': 'Mining',
               'website_url': 'https://provider.example', 'contact_enrichment_status': 'completed',
               'pages_checked': ['https://provider.example'], 'contacts': [{
                   'channel': 'whatsapp', 'value': 'https://wa.me/35112345678',
                   'evidence': {'source_url': 'https://provider.example'}}],
               'prelock_assessment': {'business_real': True, 'active_business': True,
                                      'vertical_match': True, 'business_evidence_url': 'https://provider.example'}}
        result = preflight_record(row)
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(result['prelock_reject_reasons'], [])
        self.assertIn('formal_track_assignment_evidence', result['prelock_missing_evidence'])

    def test_prelock_reject_never_reaches_sampler(self):
        row = {'source_id': 'vape:bad', 'company_name': 'Inactive Vape',
               'website_url': 'https://inactive.example', 'industry_hint': 'vape'}
        def screen(item):
            return {**item, 'contact_enrichment_status': 'completed', 'pages_checked': [item['website_url']],
                'prelock_assessment': self.evidence(item, reject=True), 'contacts': [{
                    'channel': 'whatsapp', 'value': 'https://wa.me/12345678', 'route_type': 'business_chat',
                    'evidence': {'source_url': item['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            from prospect_os.sampling import stratified_sample as real_sampler
            def checked_sampler(records, **kwargs):
                self.assertEqual(records, [])
                return real_sampler(records, **kwargs)
            with patch('research_buyer_batch.stratified_sample', side_effect=checked_sampler):
                with self.assertRaisesRegex(ValueError, 'prelock sample infeasible'):
                    run_batch([row], limit=1, seed=1, output=root/'enriched.json',
                        summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                        screen_fn=screen, min_whatsapp=0)
            self.assertFalse((root/'sampled-lock.json').exists())
            self.assertEqual(json.loads((root/'prelock-icp-reject.json').read_text())[0]['prelock_status'], 'PRELOCK_REJECT')

    def test_only_prelock_pass_enters_sample_lock(self):
        rows_in = [
            {'source_id': 'web3:pass', 'company_name': 'Small B2B',
             'website_url': 'https://b2b.example', 'industry_hint': 'blockchain', 'city_hint': 'city-a'},
            {'source_id': 'adult:pass', 'company_name': 'Independent Adult Shop',
             'website_url': 'https://adult.example', 'industry_hint': 'adult retail shop', 'city_hint': 'city-b'},
        ]
        def screen(item):
            return {**item, 'contact_enrichment_status': 'completed', 'pages_checked': [item['website_url']],
                'prelock_assessment': self.evidence(item), 'contacts': [{
                    'channel': 'whatsapp', 'value': 'https://wa.me/12345678', 'route_type': 'business_chat',
                    'evidence': {'source_url': item['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows, summary = run_batch(rows_in, limit=2, seed=1, output=root/'enriched.json',
                summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                screen_fn=screen, min_whatsapp=2, enrich_fn=lambda r: {**r, 'research_status': 'pages_collected'})
            self.assertEqual(summary['prelock_pass_count'], 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['prelock_status'], 'PRELOCK_PASS')


if __name__ == '__main__':
    unittest.main()
