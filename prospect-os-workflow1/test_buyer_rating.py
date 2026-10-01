import unittest

from prospect_os.buyer_rating import rate_candidate, rating_summary
from research_buyer_batch import assign_contact_quota


class BuyerRatingTests(unittest.TestCase):
    def test_positive_score_requires_traceable_evidence_and_does_not_change_gate(self):
        row = {
            'prelock_status': 'PRELOCK_REVIEW',
            'rating_assessment': {
                'buyer_intent': {'score': 23, 'reason': 'High intent query tested', 'evidence': [{
                    'url': 'https://example.com/research', 'checked_at': '2026-09-29T00:00:00Z',
                    'label': 'observed', 'claim': 'Buyer query shows a purchase scenario.'}]},
                'geo_opportunity': {'score': 18, 'reason': 'Competitors visible', 'evidence': [{
                    'url': 'https://example.com/search-check', 'checked_at': '2026-09-29T00:00:00Z',
                    'label': 'observed', 'claim': 'Competitors are visible for tested query.'}]},
                'decision_maker_reachability': {'score': 17, 'evidence': [{
                    'url': 'https://example.com/contact', 'checked_at': '2026-09-29T00:00:00Z',
                    'label': 'observed', 'claim': 'Official direct company WhatsApp route.'}]},
            },
        }
        rated = rate_candidate(row)
        self.assertEqual(rated['buyer_priority_score'], 58)
        self.assertEqual(rated['buyer_grade'], 'B')
        self.assertEqual(rated['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(rated['rating_version'], 'buyer-rating-v1')

    def test_unbacked_scores_are_zero_and_grade_c(self):
        rated = rate_candidate({'prelock_status': 'PRELOCK_PASS', 'rating_assessment': {
            'buyer_intent': {'score': 25, 'reason': 'Claim with no evidence'}
        }})
        self.assertEqual(rated['buyer_priority_score'], 0)
        self.assertEqual(rated['buyer_grade'], 'C')
        self.assertEqual(rated['rating_breakdown']['buyer_intent'], 0)

    def test_summary_reports_exact_channel_and_vertical_shortfalls(self):
        rows = [rate_candidate({'prelock_status': 'PRELOCK_PASS', 'prelock_channel': 'whatsapp',
                                'available_contact_channels': ['whatsapp'], 'vertical': 'web3'})]
        summary = rating_summary(rows, vertical_quotas={
            'web3': 8, 'ai': 7, 'vape': 5, 'wine': 5, 'adult': 5})
        self.assertEqual(summary['needed_whatsapp'], 24)
        self.assertEqual(summary['needed_telegram'], 6)
        self.assertEqual(summary['whatsapp_shortfall'], 24)
        self.assertEqual(summary['telegram_shortfall'], 6)
        self.assertEqual(summary['vertical_shortfall']['web3'], 8)
        self.assertEqual(sum(x['whatsapp'] for x in summary['required_slots'].values()), 24)
        self.assertEqual(sum(x['telegram'] for x in summary['required_slots'].values()), 6)
        self.assertEqual(summary['required_slots']['web3']['telegram'], 2)

    def test_dual_route_uses_telegram_only_to_fill_exact_quota(self):
        rows = ([{'company_name': f'tg-{i}', 'available_contact_channels': ['telegram'],
                  'contacts': [{'channel': 'telegram', 'value': f'https://t.me/u{i}'}]}
                 for i in range(5)]
                + [{'company_name': 'dual', 'available_contact_channels': ['whatsapp', 'telegram'],
                    'contacts': [{'channel': 'whatsapp', 'value': 'https://wa.me/12345678'},
                                 {'channel': 'telegram', 'value': 'https://t.me/dual'}]}]
                + [{'company_name': f'wa-{i}', 'available_contact_channels': ['whatsapp'],
                    'contacts': [{'channel': 'whatsapp', 'value': f'https://wa.me/1234567{i:02d}'}]}
                   for i in range(24)])
        selected, result = assign_contact_quota(rows, seed=20260907)
        self.assertTrue(result['feasible'])
        self.assertEqual(result['selected'], {'whatsapp': 24, 'telegram': 6})
        dual = next(row for row in selected if row['company_name'] == 'dual')
        self.assertEqual(dual['selected_contact_channel'], 'telegram')
        self.assertEqual(len(dual['contacts']), 2)  # preserve both source routes

    def test_summary_does_not_count_vertical_surplus_toward_formal_channel_quota(self):
        rows = ([{'prelock_status': 'PRELOCK_PASS', 'buyer_grade': 'B',
                  'buyer_priority_score': 60, 'sampling_vertical': 'ai',
                  'sampling_track': 'track_a', 'available_contact_channels': ['whatsapp']}
                 for _ in range(10)]
                + [{'prelock_status': 'PRELOCK_PASS', 'buyer_grade': 'B',
                    'buyer_priority_score': 60, 'sampling_vertical': 'web3',
                    'sampling_track': 'track_a', 'available_contact_channels': ['whatsapp']}
                   for _ in range(1)]
                + [{'prelock_status': 'PRELOCK_PASS', 'buyer_grade': 'B',
                    'buyer_priority_score': 60, 'sampling_vertical': 'adult',
                    'sampling_track': 'track_b', 'available_contact_channels': ['whatsapp']}
                   for _ in range(2)])
        summary = rating_summary(rows, vertical_quotas={
            'web3': 8, 'ai': 7, 'vape': 5, 'wine': 5, 'adult': 5})
        self.assertEqual(summary['currently_fillable_formal_slots'],
                         {'total': 10, 'whatsapp': 10, 'telegram': 0})
        self.assertEqual(summary['whatsapp_shortfall'], 14)
        self.assertEqual(summary['telegram_shortfall'], 6)
        self.assertEqual(summary['vertical_shortfall']['ai'], 0)
        self.assertEqual(summary['vertical_shortfall']['vape'], 5)


if __name__ == '__main__':
    unittest.main()
