import json
import tempfile
import unittest
from pathlib import Path

from prospect_os.buyer_intent import execute
from prospect_os.sample_lock import align_to_lock, freeze_sample, load_lock, verify_final_ids
from prospect_os.sampling import AI_B2B, WEB3, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL, stratified_sample
from research_buyer_batch import run_batch


class SampleLockTests(unittest.TestCase):
    def pool(self):
        labels = {WEB3: 'blockchain', AI_B2B: 'software', VAPE_TOBACCO: 'vape',
                  ALCOHOL_BAR: 'wine', ADULT_RETAIL: 'adult retail shop'}
        return [{'source_id': f'{vertical}:{i}', 'identity_key': f'{vertical}:{i}',
                 'company_name': f'{vertical} company {i}', 'industry_hint': label,
                 'website_url': f'https://company-{vertical}-{i}.example',
                 'city_hint': f'city-{i}', 'source_dataset_url': f'https://source-{i % 5}.example'}
                for vertical, label in labels.items() for i in range(35)]

    def test_sample_lock_prevents_company_drift(self):
        sampled, summary = stratified_sample(self.pool(), limit=30, seed=1234)
        self.assertEqual(len(sampled), 30)
        self.assertEqual(summary['track_counts'], {'track_a': 15, 'track_b': 15})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root / 'sampled-lock.json'
            lock = freeze_sample(lock_path, sampled, seed=1234, limit=30)
            self.assertEqual(len(load_lock(lock_path)['sample_ids']), 30)
            extras = [{'source_id': f'extra:{i}', 'company_name': f'New company {i}'}
                      for i in range(10)]
            source = root / 'researched.json'
            source.write_text(json.dumps(sampled + extras))
            output = root / 'sales'
            with self.assertRaisesRegex(ValueError, 'downstream introduced unsampled companies'):
                execute(source, '2026-09-23', root / 'db.sqlite', output,
                        sample_lock=lock_path)
            rejected = json.loads((output / 'rejected-not-in-sample-lock.json').read_text())
            self.assertEqual(len(rejected), 10)
            self.assertTrue(all(r['status']['rejected_reason'] == 'not_in_sample_lock' for r in rejected))
            self.assertFalse((output / 'top20.json').exists())
            self.assertFalse((output / 'decisions.json').exists())
            self.assertFalse((root / 'db.sqlite').exists())

    def test_failed_or_missing_company_is_retained_without_backfill(self):
        sampled, _ = stratified_sample(self.pool(), limit=30)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock = freeze_sample(root / 'sampled-lock.json', sampled, seed=20260907, limit=30)
            rows = align_to_lock(sampled[:-1], lock)
            self.assertEqual(len(rows), 30)
            self.assertEqual(rows[-1]['status'], {'research_failed': True, 'contact_missing': True})
            self.assertTrue(all(r['sample_lock_verified'] for r in rows))
            verify_final_ids(rows, lock)
            with self.assertRaisesRegex(ValueError, 'existing sample lock differs'):
                freeze_sample(root / 'sampled-lock.json', list(reversed(sampled)), seed=20260907, limit=30)

    def test_rerun_uses_frozen_raw_snapshot_and_keeps_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            options = dict(limit=30, seed=1234, output=root/'enriched.json',
                           summary_path=root/'sampling-summary.json',
                           lock_path=root/'sampled-lock.json')
            original, first = run_batch(self.pool(), **options,
                enrich_fn=lambda r: {**r, 'research_status': 'website_fetch_failed',
                                     'status': {'research_failed': True, 'contact_missing': True}})
            self.assertEqual(len(original), 30)
            self.assertTrue(first['sample_lock_verified'])
            # An entirely different discovery pool cannot alter this run.
            again, second = run_batch(self.pool()[-2:], **options,
                enrich_fn=lambda r: self.fail('already researched rows must be reused'))
            self.assertEqual(again, original)
            self.assertEqual(first, second)
            self.assertTrue(all(r['status']['research_failed'] for r in again))

    def test_enrichment_cannot_swap_a_company(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root/'enriched.json'
            with self.assertRaisesRegex(ValueError, 'downstream introduced unsampled companies'):
                run_batch(self.pool(), limit=30, seed=1234, output=output,
                          summary_path=root/'summary.json', lock_path=root/'sampled-lock.json',
                          enrich_fn=lambda r: {**r, 'company_name': 'Swapped',
                                               'research_status': 'pages_collected'})
            self.assertFalse(output.exists())
            rejected = json.loads((root/'rejected-not-in-sample-lock.json').read_text())
            self.assertEqual(rejected[0]['status']['rejected_reason'], 'not_in_sample_lock')


if __name__ == '__main__':
    unittest.main()
