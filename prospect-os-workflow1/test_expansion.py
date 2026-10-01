import tempfile
import unittest
import json
from pathlib import Path

from prospect_os.expansion import (
    compute_required_slots, make_review_item, record_review_attempt,
    rank_sources, run_expansion_loop, source_exhausted_criteria, source_stop_reason,
)
from prospect_os.sampling import (
    WEB3, AI_B2B, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL,
)


class ExpansionTests(unittest.TestCase):
    def test_required_slots_track_vertical_and_channels(self):
        rows = [
            {"company_name": "w", "vertical": WEB3, "sampling_track": "track_a",
             "prelock_status": "PRELOCK_PASS", "prelock_channel": "whatsapp"},
            {"company_name": "a", "vertical": AI_B2B, "sampling_track": "track_a",
             "prelock_status": "PRELOCK_PASS", "prelock_channel": "telegram"},
            {"company_name": "v", "vertical": VAPE_TOBACCO, "sampling_track": "track_b",
             "prelock_status": "PRELOCK_PASS", "prelock_channel": "telegram"},
        ]
        slots = compute_required_slots(rows, reserve_pool_target=42)
        self.assertEqual(slots["reserve_pool_shortfall"], 39)
        self.assertEqual(slots["track_a_shortfall"], 13)
        self.assertEqual(slots["track_b_shortfall"], 14)
        self.assertEqual(slots["vertical_shortfall"][WEB3], 7)
        self.assertEqual(slots["vertical_shortfall"][AI_B2B], 6)
        self.assertEqual(slots["vertical_shortfall"][VAPE_TOBACCO], 4)
        self.assertEqual(slots["channel_shortfall"], {"whatsapp": 23, "telegram": 4})

    def test_review_queue_attempts_park_without_blocking(self):
        row = make_review_item({"company_name": "x"}, "ownership_missing")
        self.assertEqual(row["next_review_action"], "check official about page and independent ownership evidence")
        for i in (1, 2):
            row = record_review_attempt(row, {"prelock_status": "PRELOCK_REVIEW"})
            self.assertEqual(row["prelock_status"], "PRELOCK_REVIEW")
        row = record_review_attempt(row, {"prelock_status": "PRELOCK_REVIEW"})
        self.assertEqual(row["prelock_status"], "PRELOCK_PARKED")
        self.assertEqual(row["review_attempts"], 3)

    def test_review_is_retried_then_loop_continues_to_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "expansion-state.json"
            slots_path = Path(temp) / "required_slots.json"
            yield_path = Path(temp) / "source-yield.json"
            review = make_review_item({"company_name": "first"}, "ownership_missing")
            from prospect_os.sampling import sampling_record_key
            review["identity_key"] = sampling_record_key(review)
            state = {
                "status": "RUNNING", "sources_attempted": ["one"], "source_yield": {},
                "batch_history": [], "fresh_raw_scanned": 1, "pass_records": [],
                "review_queue": [review], "parked_records": [], "rejected_count": 0,
                "consecutive_low_yield_batches": 0, "reserve_pool_target": 2,
            }
            state_path.write_text(__import__("json").dumps(state))
            found = {"calls": 0}
            repair_calls = {"count": 0}

            def discover_batch(**kwargs):
                found["calls"] += 1
                if found["calls"] == 1:
                    return {"source_name": "two", "records": [
                        {"company_name": "second", "identity_key": "second",
                         "vertical": WEB3, "website_url": "https://second.example",
                         "prelock_channel": "whatsapp"}
                    ]}
                return {"source_name": "three", "records": [
                    {"company_name": "third", "identity_key": "third",
                     "vertical": AI_B2B, "website_url": "https://third.example",
                     "prelock_channel": "whatsapp"}
                ]}

            def screen(rows, _slots):
                return [{**r, "prelock_status": "PRELOCK_PASS"} for r in rows]

            def repair(row, _action):
                repair_calls["count"] += 1
                return {**row, "prelock_status": "PRELOCK_REVIEW"}

            result = run_expansion_loop(
                state_path=state_path, required_slots_path=slots_path, source_yield_path=yield_path,
                discover_batch=discover_batch, screen_and_preflight=screen,
                repair_review=repair, sample_ready=lambda rows: len(rows) >= 2,
                reserve_pool_target=2, batch_size=1, max_cycles=5,
            )
            self.assertEqual(result["status"], "SAMPLE_READY")
            self.assertEqual(found["calls"], 2)
            self.assertEqual(repair_calls["count"], 2)
            self.assertEqual(result["parked"], 0)
            self.assertEqual(result["review_queue_count"], 1)
            self.assertEqual(result["fresh_raw_scanned"], 3)  # one checkpoint row + two fresh RAW rows
            self.assertTrue(slots_path.exists())
            self.assertTrue(yield_path.exists())
            source_yield = json.loads(yield_path.read_text())
            self.assertEqual(source_yield["two"]["prelock_pass"], 1)
            self.assertEqual(source_yield["two"]["by_country"]["unknown"]["fresh_raw"], 1)
            self.assertEqual(source_yield["two"]["by_vertical"][WEB3]["prelock_pass"], 1)

    def test_source_stop_reason_uses_window_and_reason(self):
        self.assertIsNone(source_stop_reason({"fresh_raw": 20, "whatsapp_found": 0, "telegram_found": 0}))
        self.assertEqual(source_stop_reason({"fresh_raw": 30, "whatsapp_found": 0, "telegram_found": 0}),
                         "no_valid_chat_route_in_minimum_screen_window")
        self.assertEqual(source_stop_reason({"fresh_raw": 50, "prelock_pass": 0,
                                             "whatsapp_found": 1, "website_resolution_rate": 0.5}),
                         "zero_prelock_pass_after_50_raw")

    def test_source_rank_and_exhaustion_threshold(self):
        ordered = rank_sources({
            "low": {"fresh_raw": 50, "prelock_pass": 0, "whatsapp_found": 1,
                    "website_resolution_rate": 0.3},
            "high": {"fresh_raw": 50, "prelock_pass": 10, "whatsapp_found": 10,
                     "website_resolution_rate": 0.8},
            "stopped": {"fresh_raw": 80, "source_stop_reason": "zero_prelock_pass"},
        })
        self.assertEqual(ordered, ["high", "low"])
        state = {"fresh_raw_scanned": 999, "sources_attempted": list(range(8)),
                 "batch_history": [{"fresh_raw": 100, "prelock_pass": 0}] * 3}
        self.assertFalse(source_exhausted_criteria(state))
        state["fresh_raw_scanned"] = 1000
        self.assertTrue(source_exhausted_criteria(state))


if __name__ == "__main__":
    unittest.main()
