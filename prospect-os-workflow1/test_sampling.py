from __future__ import annotations

import unittest
from collections import Counter

from prospect_os.sampling import (
    ADULT_RETAIL,
    AI_B2B,
    ALCOHOL_BAR,
    SECONDARY,
    VAPE_TOBACCO,
    WEB3,
    classify_vertical,
    stratified_sample,
)


def raw_record(index: int, vertical: str, *, city: str | None = None, source: str | None = None) -> dict:
    labels = {
        WEB3: "Web3 blockchain smart contract development company",
        AI_B2B: "AI software SaaS B2B agency",
        VAPE_TOBACCO: "Independent vape tobacco cigar shop",
        ALCOHOL_BAR: "Independent wine liquor cocktail bar",
        ADULT_RETAIL: "Lawful adult retail sexual wellness shop",
        SECONDARY: "Automotive car repair and detailing",
    }
    return {
        "company_name": f"Company {vertical} {index:03d}",
        "directory_id": f"id-{vertical}-{index:03d}",
        "directory_team_range": "2 - 9",
        "industry_hint": labels[vertical],
        "city_hint": city or f"{vertical} City {index}",
        "source_dataset_url": source or f"https://source-{index % 4}.example/dataset",
    }


class SamplingTests(unittest.TestCase):
    def test_vertical_classifier_keeps_automotive_secondary(self) -> None:
        self.assertEqual(classify_vertical({"industry_hint": "blockchain and Web3 development"}), WEB3)
        self.assertEqual(classify_vertical({"industry_hint": "AI software B2B agency"}), AI_B2B)
        self.assertEqual(classify_vertical({"source_tags": {"shop": "tobacco"}}), VAPE_TOBACCO)
        self.assertEqual(classify_vertical({"source_tags": {"amenity": "bar"}}), ALCOHOL_BAR)
        self.assertEqual(classify_vertical({"source_tags": {"shop": "erotic"}}), ADULT_RETAIL)
        self.assertEqual(
            classify_vertical({"industry_hint": "automotive software and car repair"}),
            SECONDARY,
        )

    def test_biased_pool_and_input_order_still_produce_formal_mix(self) -> None:
        raw = []
        counts = {WEB3: 40, AI_B2B: 35, VAPE_TOBACCO: 80, ALCOHOL_BAR: 60, ADULT_RETAIL: 25, SECONDARY: 100}
        for vertical, count in counts.items():
            raw.extend(raw_record(i, vertical) for i in range(count))

        selected, summary = stratified_sample(raw, limit=30, seed=1234)
        reversed_selected, reversed_summary = stratified_sample(list(reversed(raw)), limit=30, seed=1234)

        distribution = Counter(row["sampling_vertical"] for row in selected)
        self.assertEqual(distribution, {
            WEB3: 8, AI_B2B: 7, VAPE_TOBACCO: 5, ALCOHOL_BAR: 5, ADULT_RETAIL: 5,
        })
        self.assertEqual(summary["track_counts"], {"track_a": 15, "track_b": 15})
        self.assertEqual(summary["secondary_excluded_count"], 100)
        self.assertEqual(
            [row["directory_id"] for row in selected],
            [row["directory_id"] for row in reversed_selected],
        )
        self.assertEqual(summary, reversed_summary)

    def test_city_cap_and_source_diversity_are_applied(self) -> None:
        raw = []
        verticals = (WEB3, AI_B2B, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL)
        for vertical in verticals:
            for index in range(30):
                raw.append(raw_record(
                    index, vertical,
                    city=f"City {index % 15}",
                    source=f"https://source-{index % 5}.example/data",
                ))
        selected, summary = stratified_sample(raw, limit=30, seed=88)
        city_counts = Counter(row["city_hint"] for row in selected)
        self.assertLessEqual(max(city_counts.values()), 2)
        source_counts = [item["count"] for item in summary["source_selection"].values()]
        self.assertLessEqual(max(source_counts), 12)
        self.assertEqual(len(selected), 30)

    def test_shortfall_backfills_only_inside_same_track(self) -> None:
        raw = []
        raw.extend(raw_record(i, WEB3) for i in range(3))
        raw.extend(raw_record(i, AI_B2B) for i in range(30))
        raw.extend(raw_record(i, VAPE_TOBACCO) for i in range(30))
        raw.extend(raw_record(i, ALCOHOL_BAR) for i in range(30))
        # No adult-retail records: Track B may use only its other two verticals.
        raw.extend(raw_record(i, SECONDARY) for i in range(50))

        selected, summary = stratified_sample(raw, limit=30, seed=99)
        distribution = Counter(row["sampling_vertical"] for row in selected)
        self.assertEqual(summary["track_counts"], {"track_a": 15, "track_b": 15})
        self.assertEqual(distribution[WEB3], 3)
        self.assertEqual(distribution[AI_B2B], 12)
        self.assertEqual(distribution[ADULT_RETAIL], 0)
        self.assertEqual(distribution[VAPE_TOBACCO] + distribution[ALCOHOL_BAR], 15)
        self.assertEqual(distribution[SECONDARY], 0)
        self.assertEqual(summary["shortfall_by_vertical"][WEB3], 5)
        self.assertEqual(summary["shortfall_by_vertical"][ADULT_RETAIL], 5)


if __name__ == "__main__":
    unittest.main()
