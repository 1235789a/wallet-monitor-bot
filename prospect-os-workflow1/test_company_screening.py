from __future__ import annotations

import unittest
from datetime import date

from workflow1_company_screening import prefilter


def row(index: int, *, whatsapp: bool = False, usdt: bool = False) -> dict:
    tags = {
        "name": f"Independent Roofer {index}",
        "website": f"https://roofer-{index}.example",
        "craft": "roofer",
    }
    if whatsapp:
        tags["contact:whatsapp"] = f"+1555000{index:04d}"
    if usdt:
        tags["currency:USDT"] = "yes"
    return {
        "id": f"node:{index}",
        "osm_json": {"lat": 25.7 + index / 1000, "lon": -80.2, "tags": tags},
        "updated_at": "2026-09-01T00:00:00Z",
    }


class CompanyScreeningPrefilterTests(unittest.TestCase):
    def test_missing_chat_and_crypto_do_not_remove_company_from_raw_screen(self) -> None:
        candidates, reasons = prefilter([row(1)], date(2026, 9, 20))
        self.assertEqual(len(candidates), 1)
        self.assertNotIn("no_public_direct_contact", reasons)
        self.assertNotIn("no_public_crypto_payment_signal", reasons)

    def test_contact_and_usdt_are_small_tie_breakers_only(self) -> None:
        candidates, _ = prefilter(
            [row(1), row(2, whatsapp=True, usdt=True)], date(2026, 9, 20)
        )
        by_name = {item["company_name"]: item["prefilter_score"] for item in candidates}
        self.assertLessEqual(
            by_name["Independent Roofer 2"] - by_name["Independent Roofer 1"], 4
        )


if __name__ == "__main__":
    unittest.main()
