import unittest
from validate_daily_evidence import validate

class TestGuards(unittest.TestCase):
    def test_old_peiko_is_not_ready(self):
        item=dict(id="WA-001",company="Peiko",canonical_domain="peiko.space",channel="WA",
                  contact_url="https://wa.me/380937281606",
                  contact_route_source="https://peiko.space/contact-us",
                  buyer_job="custom software",observation="Listed under Call us",observation_scope="contact page",
                  evidence_url="https://peiko.space/contact-us",captured_at="2026-10-26",
                  history_status="NO_MATCH_IN_CHECKED_SOURCES",route_status="PHONE_ONLY_UNVERIFIED_WA",
                  recipient_status="UNKNOWN",image_url="",raw_capture_url="",message="Hi",message_status="PASS",
                  send_status="NOT_SENT",evidence_type="onsite_observation",image_status="PENDING",
                  checked_sources=["2026-10-25 reserve"])
        got=validate([item])
        self.assertEqual(got["accepted"],0)
        self.assertIn("route not verified",got["issues"][0]["reasons"])
        self.assertEqual(got["shortfall"]["WA"],12)

    def test_no_ai_claim_from_onsite(self):
        item=dict(id="WA-T",company="Example",canonical_domain="example.com",channel="WA",
                  contact_url="https://wa.me/123456789",contact_route_source="https://example.com/contact",
                  buyer_job="test",observation="test",observation_scope="test",evidence_url="https://example.com",
                  captured_at="2026-10-26",history_status="NO_MATCH_IN_CHECKED_SOURCES",
                  route_status="BUSINESS_ROUTE_VERIFIED",recipient_status="BUSINESS_RECIPIENT_VERIFIED",
                  image_url="https://example.com/e.png",raw_capture_url="https://example.com/raw",
                  message="Hello from MultiHub. I found this observation. Is this the correct contact?",
                  message_status="PASS",send_status="NOT_SENT",evidence_type="onsite_observation",
                  image_status="VERIFIED_PNG_RAW",checked_sources=["source"],ai_gap_claimed=True)
        got=validate([item])
        self.assertIn("AI gap claimed without real test",got["issues"][0]["reasons"])

if __name__=="__main__": unittest.main()
