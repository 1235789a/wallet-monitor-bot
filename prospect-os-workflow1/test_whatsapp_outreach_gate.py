"""Regressions for service desks and generic WA leaking into sales output."""
import unittest
import tempfile

from prospect_os.contact_enrichment import enrich_record, extract_contacts
from prospect_os.contact_reachability import outreach_route, reachability, select_outreach_route
from prospect_os.contact_pools import _usable_contact
from prospect_os.prelock_preflight import preflight_record
from prospect_os.source_yield import build_source_yield
from prospect_os.review_repair import ReviewRepairer
from prospect_os.outreach_copy import build_generation_prompt, review_candidate, review_and_select, validate_legacy_first_message
from test_selection_repairs import company
from test_outreach_copy import sample_record, candidate


class WhatsAppOutreachGateTests(unittest.TestCase):
    def extracted(self, anchor, query=""):
        row = company(1)
        row['contacts'] = extract_contacts(row['website_url'],
            f'<a href="https://wa.me/123456789{query}">{anchor}</a>')['contacts']
        return row

    def test_live_customer_support_does_not_fill_formal_quota(self):
        row = self.extracted('Contact our human customer support')
        result = preflight_record(row)
        self.assertEqual(result['contact_reachability']['whatsapp'], 'human_direct')
        self.assertEqual(result['available_contact_channels'], [])
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertEqual(result['outreach_route_assessments'][0]['status'], 'blocked')
        source = build_source_yield([row], [], [result])['groups'][0]
        self.assertEqual(source['human_whatsapp_found'], 1)
        self.assertEqual(source['outreach_whatsapp_found'], 0)

    def test_human_product_sales_still_needs_business_recipient(self):
        result = preflight_record(self.extracted('Contact our human sales team'))
        self.assertEqual(result['prelock_status'], 'PRELOCK_REVIEW')
        self.assertIn('business_recipient_route_evidence', result['prelock_missing_evidence'])
        self.assertEqual(result['outreach_route_assessments'][0]['purpose'], 'sales')

    def test_activity_cannot_promote_an_unknown_route(self):
        row = self.extracted('WhatsApp')
        row['recent_activity'] = {'occurred_at': '2026-10-11', 'claim': 'New sale'}
        self.assertTrue(row['prelock_assessment']['active_business'])
        self.assertEqual(preflight_record(row)['available_contact_channels'], [])

    def test_founder_route_passes_without_claiming_confirmed_ownership(self):
        result = preflight_record(self.extracted('Message our founder'))
        self.assertEqual(result['prelock_status'], 'PRELOCK_PASS')
        self.assertEqual(result['available_contact_channels'], ['whatsapp'])
        self.assertFalse(result['decision_maker_reachability_confirmed'])

    def test_selected_route_is_founder_not_first_support_number(self):
        row = self.extracted('Contact our human customer support')
        row['contacts'] += extract_contacts(row['website_url'],
            '<a href="https://wa.me/987654321">Message our founder</a>')['contacts']
        result = preflight_record(row)
        self.assertEqual(result['prelock_status'], 'PRELOCK_PASS')
        self.assertEqual(select_outreach_route(result, 'whatsapp')['selected_contact_value'],
                         'https://wa.me/987654321')

    def test_prefill_templates_are_one_route_and_conflicting_uses_need_review(self):
        row = company(1)
        row['contacts'] = extract_contacts(row['website_url'],
            '<a href="https://wa.me/123456789?text=Hi">Message our founder</a>'
            '<a href="https://wa.me/123456789?text=Order%20tracking">Customer support</a>')['contacts']
        self.assertEqual(len(row['contacts']), 1)
        self.assertEqual(preflight_record(row)['available_contact_channels'], [])
        self.assertEqual(outreach_route(row['contacts'][0], row['website_url'])['reason'],
                         'conflicting_route_purposes')

    def test_another_numbers_evidence_cannot_verify_this_route(self):
        row = self.extracted('Message our founder')
        row['contacts'][0]['outreach_route']['evidence']['route'] = 'https://wa.me/987654321'
        self.assertEqual(outreach_route(row['contacts'][0], row['website_url'])['status'], 'review')

    def test_owned_reply_even_on_official_host_requires_human_review(self):
        row = company(1)
        c = row['contacts'][0]
        c['human_reachability']['evidence'].update(kind='owned_reply_export', route=c['value'], reviewed=False)
        self.assertEqual(reachability(c, row['website_url']), 'unknown')

    def test_demo_bot_is_blocked_without_misclassifying_entire_ai_company(self):
        row = self.extracted('Try our AI chatbot demo')
        self.assertEqual(outreach_route(row['contacts'][0], row['website_url'])['status'], 'blocked')
        row = self.extracted('WhatsApp')
        self.assertEqual(outreach_route(row['contacts'][0], row['website_url'])['status'], 'review')

    def test_contact_probe_keeps_both_links_and_finds_founder_within_two_reads(self):
        calls = []
        def fetch(url):
            calls.append(url)
            body = ('<a href="https://wa.me/123456789">Customer support</a><a href="/contact">Contact</a>'
                    if len(calls) == 1 else '<a href="https://wa.me/987654321">Message our founder</a>')
            return body, url
        result = enrich_record(company(1), max_pages=5, respect_robots=False,
                               delay_seconds=0, fetcher=fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result['contacts']), 2)
        self.assertEqual(select_outreach_route(result, 'whatsapp')['selected_contact_value'],
                         'https://wa.me/987654321')

    def test_review_fetches_missing_recipient_evidence_instead_of_replaying(self):
        row = company(1)
        row['contacts'][0].pop('outreach_route')
        before = preflight_record(row)
        self.assertEqual(before['prelock_status'], 'PRELOCK_REVIEW')
        calls = []
        def fetch(url):
            calls.append(url)
            body = ('<a href="/contact">Contact</a>' if url == row['website_url'] else
                    '<a href="https://wa.me/123456789">Message our founder</a>')
            return body, url
        with tempfile.TemporaryDirectory() as temp:
            repairer = ReviewRepairer(temp, fetcher=fetch, respect_robots=False,
                                      query_tester=lambda _: self.fail('Queries already verified'))
            result = repairer(before, 'business_recipient_missing')
            self.assertEqual(result['prelock_status'], 'PRELOCK_PASS')
            self.assertTrue(result['review_evidence_changed'])
            self.assertEqual(len(calls), 2)
            repairer(before, 'business_recipient_missing')
            self.assertEqual(len(calls), 2)

    def test_unknown_recipient_cannot_receive_search_pitch_with_perfect_copy_score(self):
        row = sample_record()
        row['contacts'] = []
        result = review_and_select(row, [candidate()])
        self.assertIsNone(result['outreach']['recommended_first_message'])
        self.assertIn('business_recipient_unverified_requires_recipient_check',
                      result['outreach']['message_quality']['issues'])
        self.assertEqual(build_generation_prompt(row)['context']['message_intent'], 'recipient_check')

    def test_unknown_route_can_receive_one_transparent_recipient_question_without_name(self):
        row = sample_record()
        row['contacts'] = []
        cta = 'Este é o número certo para falar com quem cuida de marketing ou novos clientes?'
        draft = candidate('Oi! Ajudo empresas a conseguir novos clientes pelas buscas online. Vi que a Acme AI cria agentes de IA para WhatsApp. '+cta,
                          message_intent='recipient_check', cta=cta)
        self.assertEqual(review_candidate(row, draft)['status'], 'PASS')
        self.assertEqual(review_and_select(row, [draft])['outreach']['message_intent'],
                         'recipient_check')

    def test_service_route_has_no_recommended_message_even_for_recipient_check(self):
        row = sample_record()
        row['contacts'][0]['outreach_route']['purpose'] = 'customer_service'
        self.assertFalse(build_generation_prompt(row)['context']['draft_allowed'])
        draft = candidate(message_intent='recipient_check')
        self.assertIn('customer_service_or_bot_route_not_for_outreach', review_candidate(row, draft)['issues'])

    def test_formal_selected_route_overrides_an_old_footer_route(self):
        row = sample_record()
        row.update(selected_contact_channel='whatsapp',
                   selected_contact_value=row['contacts'][0]['value'],
                   contact_url='https://wa.me/987654321')
        self.assertEqual(review_candidate(row, candidate())['status'], 'PASS')
        self.assertEqual(build_generation_prompt(row)['context']['direct_route'],
                         row['selected_contact_value'])

    def test_legacy_recipient_check_cannot_be_a_disguised_search_pitch(self):
        row = sample_record()
        row.update(contacts=[], message_intent='recipient_check')
        errors, _ = validate_legacy_first_message(row, candidate()['message'])
        self.assertIn('recipient_check_cannot_pitch_a_search_check', errors)

    def test_letters_or_share_links_are_not_whatsapp_numbers(self):
        for url in ('https://wa.me/example12345678', 'https://wa.me?text=Share', 'https://api.whatsapp.com/contact?phone=123456789', 'https://api.whatsapp.com/send?phone=wrong123456789'):
            c = {'channel': 'whatsapp', 'value': url, 'evidence': {'source_url': 'https://acme.example/'}}
            self.assertFalse(_usable_contact(c, 'whatsapp', 'https://acme.example/'))
            row = sample_record();row['contact_url'] = url
            self.assertTrue(any('explicit WhatsApp direct URL' in e for e in review_candidate(row, candidate())['issues']))


if __name__ == '__main__':
    unittest.main()
