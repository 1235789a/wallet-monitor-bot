from __future__ import annotations

import unittest

from prospect_os.contact_enrichment import enrich_record, extract_contacts


HTML = """
<html><body>
  <a href="mailto:info@sample.example">General email</a>
  <a href="mailto:maya.chen@sample.example">Maya</a>
  <a href="tel:+1-555-0100">Call us</a>
  <a href="https://wa.me/15550101">WhatsApp</a>
  <a href="https://t.me/sample_news">Telegram news</a>
  <a href="/about-us">Meet our founder</a>
</body></html>
"""


class ContactEnrichmentTests(unittest.TestCase):
    def test_explicit_routes_do_not_become_decision_maker_routes(self) -> None:
        result = extract_contacts("https://sample.example/", HTML)
        by_channel = {}
        for contact in result["contacts"]:
            by_channel.setdefault(contact["channel"], []).append(contact)
        self.assertEqual(by_channel["email"][0]["email_type"], "GENERIC_BUSINESS")
        self.assertTrue(any(item["email_type"] == "NAMED_EMPLOYEE" for item in by_channel["email"]))
        self.assertEqual(by_channel["phone"][0]["route_type"], "phone_only")
        self.assertFalse(by_channel["whatsapp"][0]["contact_belongs_to_decision_maker"])
        self.assertEqual(by_channel["telegram"][0]["route_type"], "unknown")
        self.assertFalse(by_channel["telegram"][0]["contact_belongs_to_decision_maker"])

    def test_plain_phone_is_never_converted_to_whatsapp(self) -> None:
        result = extract_contacts("https://sample.example/", '<a href="tel:+15550100">Phone</a>')
        self.assertEqual([item["channel"] for item in result["contacts"]], ["phone"])

    def test_enrichment_keeps_decision_access_unknown(self) -> None:
        pages = {
            "https://sample.example": (HTML, "https://sample.example/"),
            "https://sample.example/about-us": (
                "<p>Maya Chen — Founder</p>", "https://sample.example/about-us",
            ),
        }

        def fetcher(url: str) -> tuple[str, str]:
            return pages[url.rstrip("/")]

        record = enrich_record(
            {"company_name": "Sample", "website_url": "https://sample.example"},
            max_pages=3, delay_seconds=0, respect_robots=False, fetcher=fetcher,
        )
        self.assertEqual(record["contact_enrichment_status"], "completed")
        self.assertFalse(record["decision_maker_identified"])
        self.assertFalse(record["direct_decision_maker_route"])
        self.assertEqual(record["decision_access_confidence"], "unknown")
        self.assertEqual(len(record["pages_checked"]), 2)


if __name__ == "__main__":
    unittest.main()
