#!/usr/bin/env python3
"""Offline intake/coverage regression tests; synthetic identities only."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.wa_batch_intake import validate_discovery, history_precheck, audit_legacy_csv, SCHEMA
from prospect_os.cross_channel_dedupe import REQUIRED_HISTORY_KEYS, CrossChannelDedupeEngine
from prospect_os.daily27_models import CandidateRecord
import run_wa_website_preflight as cli


def row(i=1):
    return {"original_prospect_id": f"TEST-{i}", "company_name": f"Synthetic {i}",
            "website_url": f"https://example{i}.org", "discovery_source_url": "https://directory.example/list"}


def payload(rows):
    return {"schema": SCHEMA, "records": rows}


def index(path, partial=True):
    rows = [{"source_tag": tag, "company_name": f"Historical fixture {i}", "canonical_domain": f"old{i}.example"}
            for i, tag in enumerate(REQUIRED_HISTORY_KEYS)]
    coverage = {tag: {"status": "PARTIAL" if partial and tag == "DAILY_PRESENTED" else "VERIFIED_COMPLETE",
                      "record_count": 1, "sources": ["https://history.example/ledger"]} for tag in REQUIRED_HISTORY_KEYS}
    path.write_text(json.dumps({"schema": "multihub-history-index-v1", "checked_on": datetime.now(timezone.utc).date().isoformat(),
                                "coverage": coverage, "records": rows}))


class IntakeTests(unittest.TestCase):
    def test_schema_rejects_ready_claim_and_duplicate_ids(self):
        self.assertEqual(validate_discovery(payload([row()])), [row()])
        for invalid in [payload([row(), row()]), payload([{**row(), "send_ready": True}]), [row()],
                        payload([{**row(), "discovery_source_url": row()["website_url"]}]),
                        payload([{**row(), "discovery_source_url": "https://google.com/search?q=example"}])]:
            with self.assertRaises(ValueError): validate_discovery(invalid)

    def test_history_precheck_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "history.json"
            index(p)
            _, status = history_precheck(p)
            self.assertFalse(status["scale_allowed"])
            self.assertEqual(status["missing_categories"], ["DAILY_PRESENTED"])
            index(p, partial=False)
            self.assertTrue(history_precheck(p)[1]["scale_allowed"])
            self.assertFalse(history_precheck(None)[1]["scale_allowed"])

    def test_partial_batch_still_dedupes(self):
        e = CrossChannelDedupeEngine()
        seen = set()
        self.assertEqual(e.check_candidate(CandidateRecord("a", "Fixture", "", official_url="https://example.org"), seen).history_status, "HOLD_HISTORY_INCOMPLETE")
        self.assertEqual(e.check_candidate(CandidateRecord("b", "Fixture", "", official_url="https://example.org"), seen).history_status, "DUPLICATE_IN_CURRENT_BATCH")

    def test_csv_width_error_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "legacy.csv"
            p.write_text('a,b\n"quoted, valid",ok\nnot,quoted,extra\n')
            report = audit_legacy_csv(p)
            self.assertFalse(report["valid"])
            self.assertEqual(report["invalid_rows"], [{"line": 3, "fields": 3}])
            self.assertFalse(report["usable_for_wa_intake"])

    def test_cli_blocks_mass_scan_before_any_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "history.json"; inp = Path(tmp) / "input.json"; out = Path(tmp) / "out.json"
            index(p); inp.write_text(json.dumps(payload([row(i) for i in range(11)])))
            args = ["cli", str(inp), str(out), "--history-index", str(p)]
            for extra in [[], ["--partial-pilot"]]:
                with patch.object(sys, "argv", args + extra), patch.object(cli, "preflight_website") as fetch:
                    self.assertEqual(cli.main(), 2)
                    fetch.assert_not_called()
                    self.assertFalse(out.exists())

    def test_pilot_route_hint_cannot_become_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "history.json"; inp = Path(tmp) / "input.json"; out = Path(tmp) / "out.json"
            index(p); inp.write_text(json.dumps(payload([{**row(), "wa_hint": "https://wa.me/442083661177"}])))
            with patch.object(sys, "argv", ["cli", str(inp), str(out), "--history-index", str(p), "--partial-pilot"]), patch.object(cli, "preflight_website", return_value={"wa_routes": [], "wa_preflight_status": "NO_ROUTE_OBSERVED", "send_ready": False}):
                self.assertEqual(cli.main(), 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["records"][0]["history_status"], "HOLD_HISTORY_INCOMPLETE")
            self.assertEqual(report["records"][0]["wa_preflight_status"], "NO_ROUTE_OBSERVED")
            self.assertEqual(report["send_ready"], 0)


if __name__ == "__main__": unittest.main(verbosity=2)
