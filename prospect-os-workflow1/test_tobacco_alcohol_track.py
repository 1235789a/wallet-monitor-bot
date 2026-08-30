from __future__ import annotations

import unittest
from datetime import date

from prospect_os.tobacco_alcohol_track import qualify_record, record_reply_test, screen_records


RUN_DAY = date(2026, 8, 30)


def evidence(category: str, source_url: str, claim: str, label: str = "observed") -> dict:
    return {"category": category, "source_url": source_url, "claim": claim, "label": label}


def good_record() -> dict:
    source = "https://www.openstreetmap.org/node/123"
    site = "https://smallbrew.example"
    return {
        "company_name": "Small Brew House",
        "discovery_channel": "map_local_business_directory",
        "discovery_source_url": source,
        "discovery_source_note": "Found in a structured local-business map record before the official site was reviewed.",
        "website_url": site,
        "official_business_type": "craft brewery",
        "business_type_verified": True,
        "business_type_source_url": site + "/about",
        "physical_location_verified": True,
        "physical_location_source_url": source,
        "ownership_model": "independent_small_business",
        "location_count": 1,
        "chain_status": "no",
        "ownership_location_evidence_url": source,
        "recent_activity_verified": True,
        "recent_activity_at": "2026-08-25",
        "recent_activity_source_url": site + "/events",
        "contact_channel": "whatsapp",
        "contact_url": "https://wa.me/15550000000",
        "contact_verification": "official_link",
        "contact_source_url": site + "/contact",
        "payment_signal_type": "xbt",
        "usdt_status": "crypto_signal",
        "reply_behavior_status": "observed",
        "payment_intent_status": "unknown",
        "research_evidence": [
            evidence("business_type", site + "/about", "Official page describes an independent craft brewery."),
            evidence("physical_location", source, "The structured record identifies one physical location."),
            evidence("ownership_locations", source, "One mapped physical location; no chain marker."),
            evidence("recent_activity", site + "/events", "A current tasting event is listed."),
            evidence("contact_openness", site + "/contact", "Official WhatsApp link is published."),
            evidence("reply_behavior", site + "/public-comments", "The business replied to recent public customer questions."),
        ],
    }


class TobaccoAlcoholGateTests(unittest.TestCase):
    def test_source_first_record_can_be_ready_but_usdt_is_not_upgraded(self) -> None:
        result = qualify_record(good_record(), RUN_DAY)
        self.assertEqual(result.status, "READY_FOR_REPLY_TEST")
        self.assertNotIn("usdt_confirmation_question_required", result.reason_codes)
        self.assertEqual(result.normalized["usdt_status"], "crypto_signal")
        self.assertTrue(result.normalized["payment_validation_required"])

    def test_direct_reply_test_is_recorded_separately(self) -> None:
        updated = record_reply_test(good_record(), "asked_price", "2026-08-30T10:00:00Z", "https://wa.me/15550000000")
        self.assertEqual(updated["direct_reply_status"], "asked_price")
        self.assertEqual(updated["payment_intent_status"], "asked_price")
        self.assertEqual(updated["reply_behavior_status"], "observed")

    def test_search_discovery_is_hard_quarantine(self) -> None:
        row = good_record()
        row["discovery_channel"] = "google"
        result = qualify_record(row, RUN_DAY)
        self.assertEqual(result.status, "QUARANTINED")
        self.assertIn("search_engine_discovery_forbidden", result.hard_failures)

    def test_missing_business_verification_stays_in_review(self) -> None:
        row = good_record()
        row["business_type_verified"] = False
        result = qualify_record(row, RUN_DAY)
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIn("business_type_official_verification", result.missing_evidence)

    def test_public_phone_is_not_mistaken_for_verified_whatsapp(self) -> None:
        row = good_record()
        row["contact_verification"] = "official_phone"
        result = qualify_record(row, RUN_DAY)
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIn("contact_account_verification", result.missing_evidence)

    def test_same_domain_discovery_is_not_provenance(self) -> None:
        row = good_record()
        row["discovery_source_url"] = "https://smallbrew.example/map-listing"
        result = qualify_record(row, RUN_DAY)
        self.assertEqual(result.status, "QUARANTINED")
        self.assertIn("discovery_source_same_domain_as_official_site", result.hard_failures)

    def test_chain_and_three_locations_are_hard_exclusions(self) -> None:
        row = good_record()
        row["location_count"] = 3
        result = qualify_record(row, RUN_DAY)
        self.assertEqual(result.status, "QUARANTINED")
        self.assertIn("more_than_two_locations_or_no_entity_location", result.hard_failures)

    def test_no_quota_filling(self) -> None:
        result = screen_records([good_record()], RUN_DAY, requested=10)
        self.assertEqual(result["counts"]["raw_records"], 1)
        self.assertEqual(len(result["qualified"]), 1)
        self.assertEqual(result["shortfall"], 9)
        self.assertTrue(result["no_quota_filling"])


if __name__ == "__main__":
    unittest.main()
