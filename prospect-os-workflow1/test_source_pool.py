from __future__ import annotations

import unittest

from prospect_os.source_pool import (
    build_overpass_query, merge_records, parse_csv_rows, parse_overpass, pool_manifest,
)


class SourcePoolTests(unittest.TestCase):
    def test_overpass_record_preserves_source_provenance(self) -> None:
        payload = {"elements": [{
            "type": "node", "id": 123, "lat": 25.76, "lon": -80.19,
            "timestamp": "2026-09-01T00:00:00Z",
            "tags": {"name": "Independent Cigar Room", "shop": "tobacco", "website": "https://cigar.example"},
        }]}
        record = parse_overpass(payload, "2026-09-20T00:00:00+00:00")[0]
        self.assertEqual(record["stage"], "RAW")
        self.assertEqual(record["discovery_channel"], "map_local")
        self.assertEqual(record["discovery_source_url"], "https://www.openstreetmap.org/node/123")
        self.assertEqual(record["website_discovery_method"], "source_record_tag")
        self.assertFalse(record["website_inferred"])
        self.assertFalse(record["source_activity"]["counts_as_recent_marketing"])
        self.assertEqual(len(record["raw_snapshot_sha256"]), 64)

    def test_missing_osm_website_is_unknown_not_no_website(self) -> None:
        record = parse_overpass({"elements": [{
            "type": "node", "id": 7, "lat": 1, "lon": 2,
            "tags": {"name": "Detail Shop", "shop": "car_repair"},
        }]})[0]
        self.assertEqual(record["website_url"], "")
        self.assertEqual(record["website_discovery_method"], "not_present_in_source_record")
        self.assertEqual(record["website_absence_status"], "unknown")

    def test_source_website_without_scheme_is_explicitly_inferred(self) -> None:
        record = parse_overpass({"elements": [{
            "type": "node", "id": 8, "lat": 1, "lon": 2,
            "tags": {"name": "Detail Shop", "shop": "car_repair", "website": "detail.example/contact"},
        }]})[0]
        self.assertEqual(record["website_url"], "https://detail.example/contact")
        self.assertEqual(record["website_discovery_method"], "source_record_tag_scheme_inferred")
        self.assertTrue(record["website_inferred"])

    def test_merge_preserves_multiple_location_observations(self) -> None:
        payload = {"elements": [
            {"type": "node", "id": 1, "lat": 1.0, "lon": 2.0,
             "tags": {"name": "One Brand", "shop": "wine", "website": "https://one.example"}},
            {"type": "node", "id": 2, "lat": 1.1, "lon": 2.1,
             "tags": {"name": "One Brand Downtown", "shop": "wine", "website": "https://one.example"}},
        ]}
        merged = merge_records(parse_overpass(payload))
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["location_observations"]), 2)
        self.assertEqual(len(merged[0]["source_memberships"]), 2)

    def test_tabular_import_rejects_search_discovery_channel(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved off-search"):
            parse_csv_rows(
                [{"name": "Sample"}], dataset_url="https://data.example/business.csv",
                source_name="city-data", discovery_channel="google",
            )

    def test_overpass_query_is_sector_limited_and_manifest_has_no_ranking(self) -> None:
        query = build_overpass_query((25.0, -81.0, 26.0, -80.0), ["regulated_retail"])
        self.assertIn('nwr["shop"="tobacco"]', query)
        self.assertNotIn('nwr["craft"="roofer"]', query)
        manifest = pool_manifest([], ["fixture"])
        self.assertFalse(manifest["ranking_applied"])
        self.assertFalse(manifest["contact_quota_applied"])
        self.assertEqual(manifest["discovery_mode"], "source_first_no_search")


if __name__ == "__main__":
    unittest.main()
