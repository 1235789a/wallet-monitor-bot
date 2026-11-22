#!/usr/bin/env python3
"""Offline fixtures only; no account checking or messages."""
import io
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.contact_enrichment import extract_contacts
from prospect_os.contact_pools import _usable_contact
from prospect_os.wa_website_preflight import preflight_website, valid_wa_candidate, decode_public_qr
from prospect_os.wa_activity_gate import verify_wa_activity
from prospect_os.daily27_models import CandidateRecord, ActivityProof

SITE = "https://example.org/"
LINK = "https://wa.me/442083661177"


class WAPreflightTests(unittest.TestCase):
    def test_generic_phone_not_whatsapp(self):
        contacts = extract_contacts(SITE, '<a href="tel:+442083661177">Phone</a>')["contacts"]
        self.assertFalse(any(c["channel"] == "whatsapp" for c in contacts))

    def test_official_label_generates_candidate_only(self):
        for html in ['<p>WhatsApp: +44 20 8366 1177</p>', '<a href="tel:+442083661177">WhatsApp</a>', '<div data-whatsapp-number="+442083661177"></div>']:
            with self.subTest(html=html):
                wa = [c for c in extract_contacts(SITE, html)["contacts"] if c["channel"] == "whatsapp"][0]
                self.assertEqual(wa["value"], LINK)
                self.assertEqual(wa["route_verification_status"], "OFFICIAL_LABEL_NUMBER_GENERATED_UNVERIFIED")
                self.assertFalse(_usable_contact(wa, "whatsapp", SITE))

    def test_direct_and_invalid_routes(self):
        self.assertTrue(valid_wa_candidate(LINK))
        self.assertTrue(valid_wa_candidate("https://api.whatsapp.com/send?phone=442083661177"))
        self.assertTrue(valid_wa_candidate("https://wa.me/message/ABCDEF12"))
        for bad in ["https://wa.me/0000000000", "https://wa.me/abc1234567890", "https://wa.me.evil.example/442083661177", "https://api.whatsapp.com/news?phone=442083661177", "https://chat.whatsapp.com/ABCDEF12"]:
            self.assertFalse(valid_wa_candidate(bad))

    def test_rendered_dom_and_qr_are_evidence_not_consent(self):
        result = preflight_website({"website_url": SITE}, respect_robots=False, max_pages=1, delay_seconds=0,
                                   fetcher=lambda url: ("<html><div>Contact</div></html>", url),
                                   render_fetcher=lambda url: (f'<a href="{LINK}">WhatsApp sales</a>', url, ["https://wa.me/message/ABCDEF12"]))
        self.assertEqual(result["wa_preflight_status"], "OFFICIAL_LINK_FOUND")
        self.assertEqual(len(result["wa_routes"]), 2)
        self.assertFalse(result["send_ready"])
        self.assertFalse(result["wa_account_verified"])

    def test_browser_failure_is_hold_not_same_as_no_route(self):
        def blocked(url):
            raise RuntimeError("render_unavailable")
        result = preflight_website({"website_url": SITE}, respect_robots=False, max_pages=1, delay_seconds=0,
                                   fetcher=lambda url: ("<html></html>", url), render_fetcher=blocked)
        self.assertEqual(result["wa_preflight_status"], "HOLD_ACCESS")

    def test_qr_decode_actual_library(self):
        import zxingcpp
        from PIL import Image
        for value, expected in [(LINK, [LINK]), ("https://example.org/payment", [])]:
            barcode = zxingcpp.create_barcode(value, zxingcpp.BarcodeFormat.QRCode)
            png = io.BytesIO()
            Image.fromarray(zxingcpp.write_barcode_to_image(barcode, scale=5)).save(png, format="PNG")
            self.assertEqual(decode_public_qr(png.getvalue()), expected)

    def test_wa_business_activity_60_days_inclusive(self):
        now = datetime.now(timezone.utc)
        rec = CandidateRecord("TEST", "Synthetic", "https://directory.example/listing", channel="WA")
        rec.business_activity_proof = ActivityProof(source_url="https://example.org/news/product-launch", checked_at_utc=now.isoformat(), subject_confirmed=True,
                                                    subject_type="COMPANY", excerpt="Dated commercial activity test fixture.")
        for days, expected in [(0, True), (31, True), (60, True), (61, False), (-1, False)]:
            rec.business_activity_proof.activity_date = (now.date()-timedelta(days=days)).isoformat()
            self.assertEqual(verify_wa_activity(rec, now.date()), expected)
        rec.business_activity_proof.source_url = SITE
        rec.business_activity_proof.activity_date = now.date().isoformat()
        self.assertFalse(verify_wa_activity(rec, now.date()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
