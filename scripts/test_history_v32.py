#!/usr/bin/env python3
"""Synthetic privacy-safe V3.2 regression tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.cross_channel_dedupe import REQUIRED_HISTORY_KEYS
from prospect_os.history_v32 import audit_history_index, semantic_sha256, reconcile_contact_claims
import audit_history_v32 as cli

DIGEST = "a" * 64


def fixture():
    records = [{"source_tag": tag, "company_name": f"Fixture {i}",
                "canonical_domain": f"fixture{i}.example", "original_prospect_id": f"TEST-{i}"}
               for i, tag in enumerate(REQUIRED_HISTORY_KEYS)]
    coverage = {tag: {"status": "VERIFIED_COMPLETE", "record_count": 1,
                      "sources": [f"https://archive.example/{tag}"]}
                for tag in REQUIRED_HISTORY_KEYS}
    inventory = [{"source_tag": tag, "source_url": f"https://archive.example/{tag}",
                  "read_status": "READ_VERIFIED", "record_count": 1, "sha256": DIGEST}
                 for tag in REQUIRED_HISTORY_KEYS]
    return {"schema": "multihub-history-index-v1", "checked_on": "2026-11-23",
            "records": records, "coverage": coverage, "source_inventory": inventory}


class HistoryV32Tests(unittest.TestCase):
    def test_partial_coverage_stays_partial(self):
        data = fixture()
        data["coverage"]["DAILY_PRESENTED"]["status"] = "PARTIAL"
        out = audit_history_index(data)
        self.assertFalse(out["all_declared_complete_and_inventory_attested"])
        self.assertFalse(out["history_clear_authorized"])
        self.assertEqual(out["send_ready"], 0)
        self.assertIn("NOT_DECLARED_COMPLETE", out["categories"]["DAILY_PRESENTED"]["coverage_issues"])

    def test_inherited_complete_without_inventory_not_attested(self):
        data = fixture()
        data.pop("source_inventory")
        out = audit_history_index(data)
        self.assertFalse(out["all_declared_complete_and_inventory_attested"])
        self.assertIn("SOURCE_PROVENANCE_NOT_RECHECKED", out["categories"]["103_MASTER"]["coverage_issues"])

    def test_count_and_invalid_inventory_fail_closed(self):
        data = fixture()
        data["coverage"]["112_MASTER"]["record_count"] = 3
        data["source_inventory"][0]["sha256"] = "not-a-hash"
        out = audit_history_index(data)
        self.assertIn("INDEX_COUNT_MISMATCH", out["categories"]["112_MASTER"]["coverage_issues"])
        self.assertFalse(out["all_declared_complete_and_inventory_attested"])

    def test_digest_stable_across_download_metadata_only(self):
        a = fixture()
        b = json.loads(json.dumps(a))
        a["retrieved_at"] = "2026-11-22T09:00Z"
        b["retrieved_at"] = "2026-11-23T11:30Z"
        self.assertEqual(semantic_sha256(a), semantic_sha256(b))
        b["records"][0]["original_prospect_id"] = "NEW"
        self.assertNotEqual(semantic_sha256(a), semantic_sha256(b))

    def test_contact_reply_conflict_holds(self):
        rows = [{"status": "REPLIED"}, {"status": "READY"},
                {"status": "已联系", "detail": "暂无回复；不要重复联系"}]
        out = reconcile_contact_claims(rows)
        self.assertEqual(out["stage"], "CONTACTED")
        self.assertIn("REPLY_CONFLICT", out["issues"])
        self.assertFalse(out["eligible_for_new_first_contact"])
        self.assertFalse(out["send_ready"])

    def test_ready_never_overwrites_existing_contact(self):
        self.assertEqual(reconcile_contact_claims([{"status": "SENT"}, {"status": "READY"}])["stage"], "CONTACTED")
        self.assertEqual(reconcile_contact_claims([{"status": "READY"}])["stage"], "RESEARCH_READY_ONLY")
        self.assertFalse(reconcile_contact_claims([{"status": "READY"}])["send_ready"])

    def test_no_reply_does_not_create_fake_reply(self):
        out = reconcile_contact_claims([{"status": "NOT_REPLIED"}])
        self.assertNotIn("REPLIED_CLAIM", out["claims_seen"])
        self.assertEqual(out["stage"], "CONTACTED")

    def test_cli_private_report_without_index_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            idx, claims, result = d / "index.json", d / "claims.json", d / "result.json"
            idx.write_text(json.dumps(fixture()))
            before = idx.read_bytes()
            claims.write_text(json.dumps({"subjects": [{"key": "test-example",
                          "claims": [{"status": "REPLIED"}, {"status": "暂无回复"}]}]}))
            self.assertEqual(cli.main(["--history-index", str(idx), "--claims", str(claims),
                                       "--output", str(result)]), 0)
            self.assertEqual(idx.read_bytes(), before)
            audit = json.loads(result.read_text())
            self.assertEqual(audit["contact_conflicts"], 1)
            self.assertEqual(audit["send_ready"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
