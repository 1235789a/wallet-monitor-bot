#!/usr/bin/env python3
"""Synthetic regression coverage for historical archive reconciliation and WA continuation."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.history_archive_merge import merge_archives
from prospect_os.cross_channel_dedupe import REQUIRED_HISTORY_KEYS
from run_wa_resume_presented import review_existing


def base():
    return {"schema": "multihub-history-index-v1", "checked_on": datetime.now(timezone.utc).date().isoformat(),
            "coverage": {tag: {"status": "PARTIAL", "record_count": 0, "sources": []} for tag in REQUIRED_HISTORY_KEYS},
            "records": [], "source_inventory": []}


class ReconciliationTests(unittest.TestCase):
    def test_merge_idempotent_never_grants_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "archive.json"
            p.write_text(json.dumps([{"company": "Synthetic", "website": "https://example.org", "original_prospect_id": "TEST-001"}]))
            specs = [{"path": str(p), "selector": "array", "source_url": "https://archive.example/a", "record_kind": "RESEARCH_PRESENTED"}]
            result, report = merge_archives(base(), specs)
            self.assertEqual(len(result["records"]), 1)
            self.assertEqual(result["records"][0]["original_prospect_id"], "TEST-001")
            self.assertEqual(result["coverage"]["DAILY_PRESENTED"]["status"], "PARTIAL")
            self.assertEqual(report[0]["read_status"], "READ_VERIFIED")
            result, report = merge_archives(result, specs)
            self.assertEqual(report[0]["added"], 0)
            self.assertEqual(len(result["source_inventory"]), 1)

    def test_invalid_csv_quarantine_and_no_placeholder_domain(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "archive.csv"
            p.write_text('company,website\nSynthetic,unknown\nInvalid,https://example.org,extra\n')
            result, report = merge_archives(base(), [{"path": str(p), "selector": "csv", "source_url": "https://archive.example/b", "record_kind": "RESEARCH_PRESENTED"}])
            self.assertEqual(result["records"][0]["canonical_domain"], "")
            self.assertEqual(report[0]["read_status"], "PARTIAL_EXTRACT")
            self.assertEqual(report[0]["invalid_rows"], [3])

    def test_self_occurrence_excluded_only_for_continuation(self):
        a = base()
        a["records"] = [{"source_url": "https://archive.example/current", "source_locator": "row 1", "source_tag": "DAILY_PRESENTED", "record_kind": "RESEARCH_PRESENTED", "company_name": "Synthetic", "canonical_domain": "example.org"}]
        r = review_existing(a, {"https://archive.example/current"})
        self.assertEqual(r["records"][0]["comparison_status"], "HOLD_HISTORY_INCOMPLETE")
        self.assertEqual(r["new_leads"], 0)
        self.assertFalse(r["records"][0]["send_ready"])
        a["records"].append({**a["records"][0], "source_url": "https://archive.example/previous"})
        r = review_existing(a, {"https://archive.example/current"})
        self.assertEqual(r["records"][0]["comparison_status"], "HISTORY_MATCH_EXCLUDE")

    def test_no_live_fetch_for_known_duplicate_or_unapproved_source(self):
        a = base()
        a["records"] = [{"source_url": "https://archive.example/current", "source_locator": "row 1", "source_tag": "DAILY_PRESENTED", "record_kind": "RESEARCH_PRESENTED", "company_name": "Synthetic", "canonical_domain": "example.org"}]
        a["records"].append({**a["records"][0], "source_url": "https://archive.example/previous"})
        with patch("run_wa_resume_presented.preflight_website") as probe:
            review_existing(a, {"https://archive.example/current"}, fetch=True)
            probe.assert_not_called()
        with self.assertRaises(ValueError): review_existing(a, {"https://archive.example/not-in-index"})
        with self.assertRaises(ValueError): review_existing(a, {"https://archive.example/current"}, max_records=11, fetch=True)


if __name__ == "__main__": unittest.main(verbosity=2)
