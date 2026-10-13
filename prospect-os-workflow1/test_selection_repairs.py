import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from expand_buyer_sprint import run_expansion
from prospect_os.contact_enrichment import extract_contacts
from prospect_os.contact_reachability import reachability
from prospect_os.expansion import compute_required_slots, make_review_item, run_expansion_loop
from prospect_os.prelock_preflight import preflight_record
from prospect_os.review_repair import ReviewRepairer
from prospect_os.sampling import FORMAL_30_QUOTAS, WEB3, AI_B2B, VAPE_TOBACCO, formal_sample
from prospect_os.source_scheduler import schedule_raw, segment_key, identity_aliases
from prospect_os.source_yield import build_source_yield
import test_contact_pools as fixtures


def company(index, vertical=WEB3, channel="whatsapp", country="Brazil", source="fixture"):
    row = {"source_id": f"fixture-{index}", "company_name": f"Company {index}",
           "website_url": f"https://company-{index}.example", "city_hint": f"city-{index}",
           "vertical": vertical, "industry_hint": {"vape_tobacco": "vape", "alcohol_wine_bar": "wine",
               "adult_retail": "adult retail shop", "ai_software_b2b_agency": "software"}.get(vertical, "blockchain"),
           "country": country, "source_type": source}
    route = {"channel": channel, "value": "https://wa.me/123456789" if channel == "whatsapp" else f"https://t.me/user{index}",
             "route_type": "business_chat" if channel == "whatsapp" else "direct_chat",
             "evidence": {"source_url": row["website_url"]},
             "human_reachability": fixtures.ContactPoolTests.human_route(row),
             "outreach_route": fixtures.ContactPoolTests.business_route(row)}
    row.update(contacts=[route], pages_checked=[row["website_url"]], contact_enrichment_status="completed",
               prelock_assessment=fixtures.ContactPoolTests.evidence(row))
    return row


class SourceSchedulingTests(unittest.TestCase):
    def test_vertical_gap_beats_easy_cached_surplus(self):
        passed = [dict(company(i, AI_B2B), prelock_status="PRELOCK_PASS", buyer_grade="B",
                       available_contact_channels=["whatsapp"]) for i in range(20)]
        slots = compute_required_slots(passed)
        raw = [company(100 + i, AI_B2B) for i in range(10)] + [company(200, WEB3)]
        selected = schedule_raw(raw, slots, {}, batch_size=1, seed=1,
                                cached_keys=["source_id:fixture-100"], processed=passed)
        self.assertEqual(selected[0]["vertical"], WEB3)
        self.assertEqual(slots["channel_shortfall"]["whatsapp"], 17)
        self.assertEqual(slots["track_a_shortfall"], 8)

    def test_joint_segment_yield_beats_source_overall_yield(self):
        portugal, brazil = company(1, country="Portugal", source="directory"), company(2, country="BR", source="directory")
        for row in (portugal, brazil):
            row.pop("contacts")
        metrics = {"directory": {"fresh_raw": 1000, "prelock_pass": 900, "by_segment": {
            segment_key(portugal): {"fresh_raw": 50, "prelock_pass": 40, "outreach_telegram_found": 0},
            segment_key(brazil): {"fresh_raw": 50, "prelock_pass": 20, "outreach_telegram_found": 40}}}}
        slots = {"vertical_shortfall": {}, "channel_shortfall": {"whatsapp": 0, "telegram": 6}}
        selected = schedule_raw([portugal, brazil], slots, metrics, batch_size=1, seed=1)
        self.assertEqual(selected[0]["country"], "BR")
        self.assertEqual(selected[0]["scheduler_target_channel"], "telegram")

    def test_country_and_source_diversity_under_skewed_raw_order(self):
        rows = [company(i, country="Portugal", source="easy") for i in range(20)] + [
            company(100 + i, country="Brazil", source="other") for i in range(20)]
        selected = schedule_raw(rows, compute_required_slots([]), {}, batch_size=6, seed=2)
        counts = Counter(row["country"] for row in selected)
        self.assertEqual(counts, {"Portugal": 3, "Brazil": 3})
        self.assertEqual(selected, schedule_raw(list(reversed(rows)), compute_required_slots([]), {}, batch_size=6, seed=2))

    def test_domain_alias_and_grade_c_do_not_fill_quotas(self):
        row = dict(company(1), prelock_status="PRELOCK_PASS", buyer_grade="B", available_contact_channels=["whatsapp", "telegram"])
        duplicate = {**row, "source_id": "another-source"}
        grade_c = dict(company(2), prelock_status="PRELOCK_PASS", buyer_grade="C", available_contact_channels=["whatsapp"])
        slots = compute_required_slots([row, duplicate, grade_c])
        self.assertEqual(slots["reserve_pool_pass"], 1)
        self.assertEqual(sum(slots["formal_channel_capacity"].values()), 1)
        self.assertTrue(identity_aliases({"source_id": "one", "domain": "www.company-1.example"})
                        & identity_aliases(row))

    def test_exact_selection_keeps_needed_lower_scored_telegram(self):
        rows, index = [], 0
        for vertical, quota in FORMAL_30_QUOTAS.items():
            for _ in range(quota + 3):
                index += 1
                row = company(index, vertical)
                row.update(prelock_status="PRELOCK_PASS", buyer_grade="A", buyer_priority_score=80,
                           available_contact_channels=["whatsapp"])
                rows.append(row)
        for i in range(6):
            index += 1
            row = company(index, WEB3, "telegram")
            row.update(prelock_status="PRELOCK_PASS", buyer_grade="B", buyer_priority_score=60,
                       available_contact_channels=["telegram"])
            # The same company has human WA support. It must consume only TG
            # capacity and export the qualified TG route, never its support WA.
            support = company(index + 1000)["contacts"][0]
            support["evidence"]["source_url"] = row["website_url"]
            for field in ("human_reachability", "outreach_route"):
                support[field]["evidence"]["source_url"] = row["website_url"]
            support["outreach_route"]["purpose"] = "customer_service"
            row["contacts"].insert(0, support)
            row.update(preflight_record(row))
            rows.append(row)
        selected, summary = formal_sample(rows, seed=1)
        self.assertEqual(len(selected), 30)
        self.assertEqual(summary["selected_by_contact_channel"], {"whatsapp": 24, "telegram": 6})
        self.assertEqual(Counter(row["sampling_vertical"] for row in selected), FORMAL_30_QUOTAS)
        for row in selected:
            if row["selected_contact_channel"] == "telegram":
                self.assertTrue(row["selected_contact_value"].startswith("https://t.me/"))


class MixedSourceLocationTests(unittest.TestCase):
    def test_directory_tags_do_not_crash_or_become_location_proof(self):
        rows = [
            {"website_url": "https://shop.example", "raw_source_record": {"tags": ["SaaS", "AI"]}},
            {"website_url": "https://shop.example", "raw_source_record": {"type": "Feature", "properties": {"tags": {"address": "Store A"}}}},
            {"website_url": "https://shop.example", "raw_source_record": {"tags": {"addr:full": "Store B"}}},
            {"website_url": "https://other.example", "raw_source_record": ["malformed"]},
        ]
        with tempfile.TemporaryDirectory() as temp:
            repairer = ReviewRepairer(temp, raw_rows=rows)
        self.assertEqual(repairer.domain_locations, {"shop.example": {"Store A", "Store B"}})


class HumanReachabilityTests(unittest.TestCase):
    def test_generic_whatsapp_and_automated_welcome_stay_review(self):
        for anchor, state in (("WhatsApp", "unknown"), ("Automated welcome", "automated_welcome")):
            row = company(1)
            row["contacts"] = extract_contacts(row["website_url"], f'<a href="https://wa.me/123456789">{anchor}</a>')["contacts"]
            result = preflight_record(row)
            self.assertEqual(reachability(row["contacts"][0], row["website_url"]), state)
            self.assertEqual(result["prelock_status"], "PRELOCK_REVIEW")
            self.assertIn("human_contact_reachability_evidence", result["prelock_missing_evidence"])
            self.assertEqual(result["available_contact_channels"], [])

    def test_bot_only_is_rejected_and_transfer_does_not_become_owner(self):
        for anchor, status, state in (("Bot-only automated support", "PRELOCK_REJECT", "bot_only"),
                                      ("Transfer to a human agent", "PRELOCK_REVIEW", "human_transfer")):
            row = company(1)
            row["contacts"] = extract_contacts(row["website_url"], f'<a href="https://wa.me/123456789">{anchor}</a>')["contacts"]
            result = preflight_record(row)
            self.assertEqual(result["prelock_status"], status)
            self.assertEqual(result["contact_reachability"]["whatsapp"], state)
            self.assertFalse(result["decision_maker_reachability_confirmed"])

    def test_positive_state_requires_route_specific_dated_evidence(self):
        row = company(1)
        contact = row["contacts"][0]
        contact["human_reachability"]["evidence"]["source_url"] = "https://unrelated.example"
        self.assertEqual(reachability(contact, row["website_url"]), "unknown")
        contact["human_reachability"]["evidence"].update(kind="owned_reply_export", reviewed=True, route="another-route")
        self.assertEqual(reachability(contact, row["website_url"]), "unknown")

    def test_query_without_test_metadata_or_visibility_stays_review(self):
        row = company(1)
        row["prelock_assessment"]["buyer_queries"][0].pop("tested_at")
        result = preflight_record(row)
        self.assertEqual(result["prelock_status"], "PRELOCK_REVIEW")
        self.assertIn("buyer_query_test_metadata", result["prelock_missing_evidence"])


class EvidenceRepairTests(unittest.TestCase):
    def test_ownership_and_location_are_actually_collected_and_cached(self):
        row = company(1, VAPE_TOBACCO)
        for key in ("ownership_type", "ownership_evidence_url", "locations", "location_evidence_url", "chain"):
            row["prelock_assessment"].pop(key)
        calls = []
        def fetch(url):
            calls.append(url)
            body = '<a href="/locations">Our locations</a>' if url == row["website_url"] else '<p>Independently owned vape shop. Our only store is in Lisbon.</p>'
            return body, url
        with tempfile.TemporaryDirectory() as temp:
            repairer = ReviewRepairer(temp, fetcher=fetch, query_tester=lambda _: self.fail("query already tested"), respect_robots=False)
            result = repairer(preflight_record(row), "check ownership and locations")
            self.assertEqual(result["prelock_status"], "PRELOCK_PASS")
            self.assertEqual(result["prelock_assessment"]["locations"], 1)
            self.assertEqual(result["prelock_assessment"]["ownership_evidence_url"], row["website_url"] + "/locations")
            self.assertEqual(len(calls), 2)
            repairer(preflight_record(row), "check ownership and locations")
            self.assertEqual(len(calls), 2)

    def test_team_gap_uses_the_team_page(self):
        row = company(1)
        row["prelock_assessment"].pop("small_team_evidence")
        row["prelock_assessment"].pop("team_evidence_url")
        calls = []
        def fetch(url):
            calls.append(url)
            return ('<a href="/team">Team</a>' if url == row["website_url"] else '<p>Our team of 6 engineers builds blockchain products.</p>', url)
        with tempfile.TemporaryDirectory() as temp:
            result = ReviewRepairer(temp, fetcher=fetch, respect_robots=False)(preflight_record(row), "inspect team")
            self.assertEqual(result["prelock_status"], "PRELOCK_PASS")
            self.assertEqual(calls[-1], row["website_url"] + "/team")

    def test_buyer_query_and_visibility_are_tested_not_fabricated(self):
        row = company(1)
        row["prelock_assessment"].pop("buyer_queries")
        calls = []
        def tester(query):
            calls.append(query)
            return {"query": query, "platform": "bing", "tested_at": "2026-10-07T00:00:00Z",
                    "scope": "first 10 results", "evidence_url": "https://www.bing.com/search?q=fixture",
                    "results": [{"title": "Blockchain development provider pricing", "url": "https://competitor.example", "snippet": "B2B blockchain service pricing"}]}
        with tempfile.TemporaryDirectory() as temp:
            repairer = ReviewRepairer(temp, fetcher=lambda _: self.fail("only query evidence is missing"), query_tester=tester)
            result = repairer(preflight_record(row), "test buyer query")
            self.assertEqual(result["prelock_status"], "PRELOCK_PASS")
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(q["tested"] and q["visibility_gap"] for q in result["prelock_buyer_queries"]))
            repairer(preflight_record(row), "test buyer query")
            self.assertEqual(len(calls), 2)

    def test_unavailable_query_stays_review_and_does_not_repeat_network_calls(self):
        row = company(1)
        row["prelock_assessment"].pop("buyer_queries")
        calls = []
        def unavailable(query):
            calls.append(query)
            raise TimeoutError("fixture search unavailable")
        with tempfile.TemporaryDirectory() as temp:
            repairer = ReviewRepairer(temp, query_tester=unavailable)
            first = repairer(preflight_record(row), "test query")
            self.assertEqual(first["prelock_status"], "PRELOCK_REVIEW")
            self.assertTrue(all(q["tested"] is False for q in first["prelock_buyer_queries"]))
            second = repairer(first, "test query")
            self.assertFalse(second["review_evidence_changed"])
            self.assertEqual(len(calls), 2)

    def test_observed_three_locations_is_a_hard_failure(self):
        row = company(1, VAPE_TOBACCO)
        row["prelock_assessment"].pop("locations")
        row["prelock_assessment"].pop("location_evidence_url")
        with tempfile.TemporaryDirectory() as temp:
            result = ReviewRepairer(temp, fetcher=lambda url: ("We operate 3 stores", url), respect_robots=False)(preflight_record(row), "locations")
            self.assertEqual(result["prelock_status"], "PRELOCK_REJECT")


class ExpansionAccountingTests(unittest.TestCase):
    def test_repair_updates_current_source_yield_and_separates_this_run(self):
        row = make_review_item(company(1), "ownership_missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = {"review_queue": [row], "pass_records": [], "fresh_raw_scanned": 5}
            (root / "state.json").write_text(json.dumps(state))
            result = run_expansion_loop(state_path=root/"state.json", required_slots_path=root/"slots.json", source_yield_path=root/"yield.json",
                discover_batch=lambda **_: {"records": [], "all_sources_exhausted": True},
                screen_and_preflight=lambda *_: self.fail("no RAW"), repair_review=lambda row, _: {**row, "prelock_status": "PRELOCK_PASS"},
                sample_ready=lambda _: True, reserve_pool_target=1)
            self.assertEqual(result["this_run"]["fresh_raw_processed"], 0)
            self.assertEqual(result["this_run"]["review_to_pass"], 1)
            self.assertEqual(result["current_totals"], {"pass": 1, "review": 0, "parked": 0, "reject": 0})
            self.assertEqual(result["fresh_raw_scanned"], 5)
            self.assertEqual(result["source_yield"]["fixture"]["prelock_pass"], 1)
            self.assertEqual(result["source_yield"]["fixture"]["prelock_review"], 0)
            self.assertEqual(result["source_yield"]["fixture"]["pass_rate"], 1)

    def test_no_new_evidence_is_parked_without_three_identical_replays(self):
        row = make_review_item(company(1), "ownership_missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"state.json").write_text(json.dumps({"review_queue": [row]}))
            result = run_expansion_loop(state_path=root/"state.json", required_slots_path=root/"slots.json", source_yield_path=root/"yield.json",
                discover_batch=lambda **_: {"records": [], "all_sources_exhausted": True}, screen_and_preflight=lambda *_: [],
                repair_review=lambda row, _: {**row, "review_evidence_changed": False}, sample_ready=lambda _: False)
            self.assertEqual(result["this_run"]["review_attempts"], 1)
            self.assertEqual(result["current_totals"]["parked"], 1)

    def test_production_budget_and_resume_use_existing_raw_without_recount(self):
        rows = [company(i) for i in range(6)]
        calls = []
        def screen(row):
            calls.append(row["source_id"])
            return row
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = dict(root=root, run_dir=root/"run", history_sources=[], max_records=2, max_reviews=0,
                        max_cycles=1, screen_fn=screen)
            first = run_expansion(rows, [], **args)
            self.assertEqual(first["this_run"]["fresh_raw_processed"], 2)
            self.assertEqual(first["fresh_raw_scanned"], 2)
            second = run_expansion(rows, [], **args)
            self.assertEqual(second["this_run"]["fresh_raw_processed"], 2)
            self.assertEqual(second["fresh_raw_scanned"], 4)
            self.assertEqual(len(calls), len(set(calls)))
            self.assertEqual(second["pending_raw_remaining"], 2)

    def test_parked_record_can_resume_when_new_reviewed_evidence_arrives(self):
        row = company(1)
        row["contacts"][0].pop("human_reachability")
        review = preflight_record(row)
        review["prelock_status"] = "PRELOCK_PARKED"
        patch = company(1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "expansion-state.json").write_text(json.dumps({"parked_records": [review]}))
            result = run_expansion([], [], root=root, run_dir=run_dir, history_sources=[],
                review_evidence=[patch], max_records=0,
                repairer=ReviewRepairer(root/"review", evidence_rows=[patch],
                    fetcher=lambda _: self.fail("supplied evidence completes the gap")))
            self.assertEqual(result["current_totals"]["parked"], 0)
            self.assertEqual(result["current_totals"]["pass"], 1)
            self.assertEqual(result["this_run"]["review_to_pass"], 1)

    def test_history_excludes_seeded_passes_as_well_as_raw(self):
        row = preflight_record(company(1))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history = root / "history.json"
            history.write_text(json.dumps([{"website_url": row["website_url"]}]))
            result = run_expansion([], [row], root=root, run_dir=root/"run",
                history_sources=[("previous_contacted", history)], max_records=0, max_reviews=0)
            self.assertEqual(result["current_totals"]["pass"], 0)
            self.assertEqual(result["initial_history_excluded"], 1)

    def test_source_conversion_denominator_is_screened_not_unscreened_raw(self):
        raw = [company(i) for i in range(100)]
        screened = preflight_record(raw[0])
        group = build_source_yield(raw, [], [screened])["groups"][0]
        self.assertEqual(group["screened_count"], 1)
        self.assertEqual(group["raw_count"], 100)
        self.assertEqual(group["prelock_pass_rate"], 1)
        self.assertEqual(group["screening_coverage"], .01)


if __name__ == "__main__":
    unittest.main()
