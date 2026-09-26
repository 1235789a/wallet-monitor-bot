import json
import tempfile
import unittest
from pathlib import Path

from prospect_os.sampling import WEB3, AI_B2B, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL
from prospect_os.contact_pools import classify_pool
from research_buyer_batch import run_batch


class ContactPoolTests(unittest.TestCase):
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

    def test_raw_pool_screened_before_lock_and_email_kept_separate(self):
        labels = {WEB3: 'blockchain', AI_B2B: 'software', VAPE_TOBACCO: 'vape',
                  ALCOHOL_BAR: 'wine', ADULT_RETAIL: 'adult retail shop'}
        rows = []
        for vertical, label in labels.items():
            for i in range(11):
                row = {'source_id': f'{vertical}:{i}', 'company_name': f'{vertical} {i}',
                       'website_url': f'https://{vertical}-{i}.example', 'industry_hint': label,
                       'city_hint': f'{vertical}-city-{i}', 'source_name': f'source-{i%5}'}
                if i == 8:
                    row['prelock_quality_review'] = {'reviewed': True, 'rating': 'high',
                        'claim': 'Verified active company', 'source_url': row['website_url']}
                rows.append(row)
        def screen(row):
            i = int(row['source_id'].split(':')[-1])
            channel = 'whatsapp' if i < 5 else 'telegram' if i < 8 else 'email' if i < 10 else 'phone'
            value = ('https://wa.me/123456789' if channel == 'whatsapp' else
                     'https://t.me/company' if channel == 'telegram' else
                     'hello@company.example' if channel == 'email' else '+12345678')
            return {**row, 'contact_enrichment_status': 'completed', 'contacts': [{
                'channel': channel, 'value': value, 'route_type': 'business_chat',
                'evidence': {'source_url': row['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            options = dict(limit=30, seed=3, output=root/'enriched.json',
                           summary_path=root/'summary.json', lock_path=root/'sampled-lock.json')
            enriched, summary = run_batch(rows, **options, screen_fn=screen,
                enrich_fn=lambda row: {**row, 'research_status': 'pages_collected'})
            self.assertEqual(summary['raw_pool'], 55)
            self.assertEqual(summary['pool_counts'], {'chat': 40, 'email': 5,
                                                      'email_review': 5, 'review': 5})
            self.assertEqual(len(enriched), 30)
            self.assertEqual(summary['whatsapp_selected'], 25)
            self.assertEqual(summary['selected_by_contact_channel'], {'whatsapp': 25, 'telegram': 5})
            self.assertFalse(summary['outreach_ready'])
            self.assertEqual(len(json.loads((root/'prelock-email.json').read_text())), 5)
            self.assertEqual(len(json.loads((root/'prelock-email_review.json').read_text())), 5)
            self.assertTrue(all(r['prelock_pool'] == 'chat' for r in enriched))
            again, _ = run_batch(rows[:1], **options,
                screen_fn=lambda _: self.fail('existing lock must not rescreen'),
                enrich_fn=lambda _: self.fail('already enriched row must not change'))
            self.assertEqual(again, enriched)

    def test_shortfall_writes_pools_without_freezing_an_unusable_cohort(self):
        rows = [{'source_id': f'web3:{i}', 'company_name': f'Company {i}',
                 'website_url': f'https://company-{i}.example', 'industry_hint': 'blockchain',
                 'city_hint': f'city-{i}'} for i in range(10)]
        def screen(row):
            i = int(row['source_id'].split(':')[-1])
            return {**row, 'contact_enrichment_status': 'completed', 'contacts': [{
                'channel': 'whatsapp' if i < 2 else 'email',
                'value': 'https://wa.me/12345678' if i < 2 else 'info@company.example',
                'evidence': {'source_url': row['website_url']}}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'contact pool shortfall'):
                run_batch(rows, limit=5, seed=1, output=root/'enriched.json',
                          summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                          screen_fn=screen, min_whatsapp=4)
            self.assertFalse((root/'sampled-lock.json').exists())
            self.assertEqual(json.loads((root/'summary.json').read_text())['whatsapp_shortfall'], 2)
            self.assertEqual(len(json.loads((root/'prelock-email_review.json').read_text())), 8)


if __name__ == '__main__':
    unittest.main()
