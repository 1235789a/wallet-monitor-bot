from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import workflow1_daily as workflow


# Keep the end-to-end fixture independent from completed production run dates.
RUN_DAY = "2099-01-01"


def demo_candidate(index: int) -> dict:
    telegram = index == 6
    domain = f"safe-demo-{index:02d}.example"
    base_url = f"https://{domain}"
    reply_observed = True
    evidence = [
        {
            "category": "discovery",
            "label": "observed",
            "claim": "Found in a Product Hunt launch listing before the company website was reviewed.",
            "source_url": f"https://www.producthunt.com/posts/safe-demo-{index:02d}",
        },
        {
            "category": "recent_activity",
            "label": "observed",
            "claim": "Published a current fintech product delivery update.",
            "source_url": f"{base_url}/updates/current",
        },
        {
            "category": "reply_behavior",
            "label": "observed",
            "claim": "Replied to recent public business questions.",
            "source_url": f"{base_url}/public-thread",
        },
        {
            "category": "contact_openness",
            "label": "observed",
            "claim": "Publishes a direct business messaging link.",
            "source_url": f"{base_url}/contact",
        },
        {
            "category": "inquiry_responsiveness",
            "label": "inferred",
            "claim": "The active inquiry desk suggests current monitoring; response speed is unconfirmed.",
            "source_url": f"{base_url}/contact",
        },
        {
            "category": "account_authenticity",
            "label": "observed",
            "claim": "Shows consistent team identity and recent project activity.",
            "source_url": f"{base_url}/about",
        },
        {
            "category": "client",
            "label": "observed",
            "claim": "Portfolio shows delivered fintech and SaaS client work.",
            "source_url": f"{base_url}/portfolio",
        },
        {
            "category": "geo_maturity",
            "label": "observed",
            "claim": "No dedicated GEO package, pricing or case study appears in the reviewed services.",
            "source_url": f"{base_url}/services",
        },
        {
            "category": "partnership",
            "label": "self_reported",
            "claim": "The agency invites specialist delivery partners for overflow work.",
            "source_url": f"{base_url}/partners",
        },
        {
            "category": "usdt",
            "label": "observed",
            "claim": "The team documents USDT wallet integration capability; invoice acceptance is not confirmed.",
            "source_url": f"{base_url}/usdt-integration",
        },
    ]
    scores = {
        "recent_activity": 6,
        "reply_behavior": 9 if reply_observed else 0,
        "contact_openness": 4,
        "inquiry_responsiveness": 4,
        "account_authenticity": 4,
        "existing_clients": 9,
        "client_type_fit": 7,
        "decision_maker_access": 5,
        "commercial_activity": 3,
        "geo_gap": 18,
        "partnership_openness": 12,
        "usdt_readiness": 8,
    }
    item = {
        "company_name": f"Safe Demo Agency {index:02d}",
        "website_url": base_url,
        "country": "Philippines",
        "track": "web3_geo",
        "industry": "Fintech product studio and SEO services",
        "business_summary": "A reserved-domain test record representing a small fintech product and search agency.",
        "company_size_estimate": "2-20",
        "size_confidence": "test fixture",
        "activity_signal": "Current product delivery update published on the reserved test domain.",
        "contact_channel": "telegram" if telegram else "whatsapp",
        "contact_value": f"safe_demo_{index:02d}" if telegram else f"63999000{index:04d}",
        "contact_clickable_url": f"https://t.me/safe_demo_{index:02d}" if telegram else f"https://wa.me/63999000{index:04d}",
        "contact_type": "founder",
        "contact_source_url": f"{base_url}/contact",
        "contact_verified_at": f"{RUN_DAY}T09:00:00+08:00",
        "verified_facts": [
            "Offers fintech product delivery.",
            "Publishes search support for client projects.",
        ],
        "cautious_inference": "The documented partner model suggests openness, but commercial terms remain unconfirmed.",
        "personalization_hook": "fintech product launches with ongoing search retainers",
        "fit_reason": "Active founder-reachable client service provider with a documented delivery gap.",
        "source_urls": [f"{base_url}/services", f"{base_url}/portfolio"],
        "discovery_channel": "launch_platform",
        "discovery_source_url": f"https://www.producthunt.com/posts/safe-demo-{index:02d}",
        "discovery_source_note": "Found from a Product Hunt launch listing; the independent website was verified afterwards.",
        "business_quality": "strong",
        "distribution_gap": "strong",
        "tags": ["safe-test"],
        "decision_maker_name": f"Demo Founder {index:02d}",
        "decision_maker_role": "Founder",
        "decision_maker_source_url": f"{base_url}/about",
        "recent_activity_at": RUN_DAY,
        "geo_maturity": "aware",
        "outsourcing_status": "open",
        "usdt_status": "strong_capability",
        "social_profiles": {"facebook": f"https://facebook.com/safe-demo-{index:02d}"},
        "research_evidence": evidence,
        "score_breakdown": scores,
        "first_message": "Hi, I’m [Your Name]. I help Web3 teams make product explanations easier to follow. Your fintech launches include search retainers. Do clients also ask about product clarity?",
    }
    if telegram:
        item["telegram_quality_score"] = 92
        item["telegram_quality_reason"] = "Direct founder handle, clear identity, recent activity and strong client fit."
    return item


class Workflow1V2EndToEndTest(unittest.TestCase):
    def test_full_safe_batch_on_database_copy(self) -> None:
        with closing(sqlite3.connect(workflow.DEFAULT_DB)) as production:
            production_count_before = production.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
        with tempfile.TemporaryDirectory(prefix="prospect-os-v2-") as temp_name:
            root = Path(temp_name)
            copied_db = root / "prospects-test.db"
            source = root / "safe-candidates.json"
            vault = root / "vault"
            with closing(sqlite3.connect(
                f"file:{workflow.DEFAULT_DB.as_posix()}?mode=ro", uri=True
            )) as original:
                with closing(sqlite3.connect(copied_db)) as copied:
                    original.backup(copied)
            source.write_text(
                json.dumps([demo_candidate(i) for i in range(1, 7)], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result = workflow.execute(source, RUN_DAY, copied_db, vault, dry_run=False)
            self.assertTrue(result["complete"])
            self.assertEqual(result["new"], 6)
            self.assertEqual(result["whatsapp"], 5)
            self.assertEqual(result["telegram"], 1)
            self.assertEqual(result["sprint_tiers"], {"P0": 6})
            self.assertTrue(Path(result["report"]).exists())
            self.assertTrue(Path(result["csv"]).exists())
            report_text = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("Reply Score /30", report_text)
            self.assertIn("是否自动回复", report_text)
            with closing(sqlite3.connect(copied_db)) as conn:
                self.assertEqual(conn.execute(
                    """SELECT COUNT(*) FROM partnership_assessments pa
                       JOIN daily_candidates dc ON dc.company_id=pa.company_id
                       WHERE dc.run_id=?""", (result["run_id"],)
                ).fetchone()[0], 6)
                self.assertEqual(conn.execute(
                    """SELECT COUNT(*) FROM prospect_identities pi
                       JOIN daily_candidates dc ON dc.company_id=pi.company_id
                       WHERE dc.run_id=?""", (result["run_id"],)
                ).fetchone()[0], 12)
                capped = conn.execute(
                    "SELECT reply_score, operational_tier FROM partnership_assessments WHERE decision_maker_name='Demo Founder 01'"
                ).fetchone()
                self.assertEqual(capped, (27, "S"))
                statuses = conn.execute(
                    "SELECT decision_maker_status, auto_reply_status FROM partnership_assessments WHERE decision_maker_name='Demo Founder 01'"
                ).fetchone()
                self.assertEqual(statuses, ("confirmed", "unknown"))
        with closing(sqlite3.connect(workflow.DEFAULT_DB)) as production:
            production_count_after = production.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
        self.assertEqual(production_count_before, production_count_after)

    def test_reply_behaviour_statuses_cap_and_block_p0(self) -> None:
        candidate = demo_candidate(20)
        candidate["contact_type"] = "founder"
        scores = candidate["score_breakdown"]
        self.assertEqual(workflow.reply_score_details("not_found", scores)[0], 12)
        self.assertEqual(workflow.reply_score_details("inaccessible", scores)[0], 14)
        self.assertEqual(
            workflow.resolve_reply_behavior_status(
                {}, [{"category": "reply_behavior", "label": "inferred", "claim": "Private profile; not accessible", "source_url": "https://example.com"}]
            ),
            "inaccessible",
        )
        evidence = candidate["research_evidence"]
        tier, _, _ = workflow.assign_sprint_tier(
            candidate, evidence, 0, scores, False, "not_found"
        )
        self.assertNotEqual(tier, "P0")
        tier, _, _ = workflow.assign_sprint_tier(
            candidate, evidence, 0, scores, False, "inaccessible"
        )
        self.assertNotEqual(tier, "P0")

    def test_search_only_discovery_is_rejected_before_import(self) -> None:
        candidate = demo_candidate(30)
        candidate["discovery_channel"] = "google"
        candidate["discovery_source_url"] = "https://www.google.com/search?q=safe-demo-30"
        with tempfile.TemporaryDirectory(prefix="prospect-os-off-search-") as temp_name:
            root = Path(temp_name)
            copied_db = root / "prospects-test.db"
            source = root / "search-only.json"
            with closing(sqlite3.connect(
                f"file:{workflow.DEFAULT_DB.as_posix()}?mode=ro", uri=True
            )) as original:
                with closing(sqlite3.connect(copied_db)) as copied:
                    original.backup(copied)
            source.write_text(json.dumps([candidate]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "search-only discovery channel"):
                workflow.execute(source, RUN_DAY, copied_db, root / "vault", dry_run=True)


if __name__ == "__main__":
    unittest.main()

