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
        self.assertEqual(by_channel["telegram"][0]["route_type"], "group_or_channel")
        self.assertFalse(by_channel["telegram"][0]["contact_belongs_to_decision_maker"])

    def test_plain_phone_is_never_converted_to_whatsapp(self) -> None:
        result = extract_contacts("https://sample.example/", '<a href="tel:+15550100">Phone</a>')
        self.assertEqual([item["channel"] for item in result["contacts"]], ["phone"])

    def test_explicit_chat_url_embedded_in_site_markup_is_found(self) -> None:
        result = extract_contacts(
            "https://sample.example/",
            '<div data-url="https://api.whatsapp.com/send?phone=15550101"></div>',
        )
        self.assertEqual([item["channel"] for item in result["contacts"]], ["whatsapp"])
        self.assertEqual(result["contacts"][0]["phone_hint"], "15550101")

    def test_unlabeled_telegram_embed_is_not_assumed_direct(self) -> None:
        result = extract_contacts(
            "https://sample.example/",
            '<div data-url="https://t.me/some_account"></div>',
        )
        self.assertEqual(result["contacts"][0]["route_type"], "unverified_telegram_route")

    def test_explicit_telegram_channel_path_is_never_direct(self) -> None:
        result = extract_contacts(
            "https://sample.example/",
            '<a href="https://t.me/c/123456">Contact us on Telegram</a>',
        )
        self.assertEqual(result["contacts"][0]["route_type"], "group_or_channel")

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
        self.assertEqual(len(record["pages_checked"]), 1)

    def test_portuguese_contato_page_finds_whatsapp(self) -> None:
        pages = {
            "https://sample.example": ('<a href="/contato">Contato</a>', "https://sample.example/"),
            "https://sample.example/contato": (
                '<a href="https://wa.me/351912345678">Fale conosco no WhatsApp</a>',
                "https://sample.example/contato"),
        }
        result = enrich_record({"company_name": "Loja", "website_url": "https://sample.example/"},
            max_pages=5, delay_seconds=0, respect_robots=False,
            fetcher=lambda url: pages[url.rstrip("/")])
        self.assertEqual(result["pages_checked"], ["https://sample.example/", "https://sample.example/contato"])
        self.assertEqual(result["contacts"][0]["channel"], "whatsapp")

    def test_multilingual_anchor_and_slug_terms_find_portuguese_and_spanish_pages(self) -> None:
        for path, anchor in (("/faleconosco", "Fale conosco"),
                             ("/contactos", "Contactos"),
                             ("/contáctanos", "Contáctanos"),
                             ("/quem-somos", "Quem somos")):
            calls = []
            pages = {
                "https://sample.example": (f'<a href="{path}">{anchor}</a>', "https://sample.example/"),
                f"https://sample.example{path}": (
                    '<a href="https://api.whatsapp.com/send?phone=351912345678">WhatsApp</a>',
                    f"https://sample.example{path}"),
            }
            result = enrich_record({"company_name": "Shop", "website_url": "https://sample.example/"},
                max_pages=5, delay_seconds=0, respect_robots=False,
                fetcher=lambda url: calls.append(url) or pages[url.rstrip("/")])
            self.assertEqual(result["contacts"][0]["channel"], "whatsapp")
            self.assertEqual(calls[:2], ["https://sample.example/", f"https://sample.example{path}"])

    def test_homepage_chat_stops_before_other_pages(self) -> None:
        requested = []
        def fetcher(url):
            requested.append(url)
            return ('<a href="https://wa.me/15550123456">WhatsApp</a>'
                    '<a href="/contato">Contato</a><a href="/about">About</a>', url)
        enrich_record({"company_name": "Sample", "website_url": "https://sample.example/"},
            max_pages=5, delay_seconds=0, respect_robots=False, fetcher=fetcher)
        self.assertEqual(requested, ["https://sample.example/"])


if __name__ == "__main__":
    unittest.main()
