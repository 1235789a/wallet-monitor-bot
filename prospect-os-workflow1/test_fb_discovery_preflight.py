import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prospect_os.fb_discovery_preflight import probe_source


class TestFBDiscoveryPreflight(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.capture = Path(self.tmp.name) / "fixture.png"
        self.capture.write_bytes(b"synthetic test-only fixture" * 10)

    def probe(self, i, valid=True):
        return {
            "probe_id": str(i),
            "profile_url": f"https://www.facebook.com/founder{i}",
            "identity_source_url": "https://example.com/team",
            "decision_maker_confirmed": valid,
            "access_status": "PUBLIC_CONTENT_OBSERVED" if valid else "BLOCKED",
            "fb_activity_proof": {
                "source_url": f"https://www.facebook.com/founder{i}/posts/123456789",
                "activity_date": self.now.date().isoformat(),
                "checked_at_utc": self.now.isoformat(),
                "excerpt": "Synthetic fixture, not a real prospect.",
                "subject_type": "CONTACT_PERSON",
                "subject_confirmed": valid,
                "capture_path": str(self.capture),
                "capture_sha256": hashlib.sha256(self.capture.read_bytes()).hexdigest(),
            },
        }

    def test_no_yield_stops(self):
        result = probe_source([self.probe(i, False) for i in range(10)], as_of=self.now.date())
        self.assertEqual(result["verdict"], "SWITCH_SOURCE_OR_HOLD")
        self.assertEqual(result["ready"], 0)

    def test_two_distinct_probes_continue_not_ready(self):
        result = probe_source([self.probe(1), self.probe(2)], as_of=self.now.date())
        self.assertEqual(result["verdict"], "CONTINUE_RESEARCH")
        self.assertEqual(result["ready"], 0)

    def test_profile_does_not_count_twice(self):
        a, b = self.probe(1), self.probe(2)
        b["profile_url"] = a["profile_url"]
        result = probe_source([a, b], as_of=self.now.date())
        self.assertEqual(result["verified_unique_people"], 1)

    def test_capture_mismatch_never_passes(self):
        row = self.probe(1)
        row["fb_activity_proof"]["capture_sha256"] = "0" * 64
        result = probe_source([row], as_of=self.now.date())
        self.assertEqual(result["verified_unique_people"], 0)


if __name__ == "__main__":
    unittest.main()
