#!/usr/bin/env python3
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prospect-os-workflow1"))
sys.path.insert(0, str(ROOT / "scripts"))
from validate_daily27_production import is_valid_tg_url, is_valid_wa_url, validate_production_pack
from prospect_os.cross_channel_dedupe import CrossChannelDedupeEngine
from prospect_os.daily27_models import AITestRecord, CandidateRecord
from prospect_os.daily27_pipeline import Daily27Pipeline
from prospect_os.geo_image_renderer import render_geo_card_png
from prospect_os.icp_and_channel_gate import verify_channel_route, verify_icp_and_segment
from prospect_os.outreach_qa_gate import evaluate_outreach_qa, generate_personalized_first_touch
from prospect_os.drive_delivery import build_drive_delivery_manifest

class TestMultiHubDaily27Pipeline(unittest.TestCase):
    def test_reject_telegram_bots_and_channels(self) -> None:
        self.assertFalse(is_valid_tg_url("https://t.me/Omegalab_bot", reject_bots=True))
        self.assertFalse(is_valid_tg_url("https://t.me/sample_bot", reject_bots=True))
        self.assertFalse(is_valid_tg_url("https://t.me/+AbCdEfGhIjK", reject_bots=True))
        self.assertFalse(is_valid_tg_url("https://t.me/s/some_channel", reject_bots=True))
        self.assertTrue(is_valid_tg_url("https://t.me/RealJohnnyTime", reject_bots=True))

    def test_reject_placeholder_whatsapp(self) -> None:
        self.assertFalse(is_valid_wa_url("https://wa.me/910000000000"))
        self.assertFalse(is_valid_wa_url("https://wa.me/00000000"))
        self.assertTrue(is_valid_wa_url("https://wa.me/917800007500"))

    def test_cross_channel_dedupe_and_cluster_aliases(self) -> None:
        dedupe = CrossChannelDedupeEngine()
        dedupe.mark_all_required_sources_loaded()
        dedupe._add_entry(
            source_tag="103_MASTER",
            company_name="Codefacture",
            domain_or_url="https://codefacture.com/",
            wa="https://wa.me/908503085436",
            prospect_id="HIST-CF-01",
        )
        seen: set[str] = set()
        # Sub-brand nextjsdevelopment.com must be caught via cluster deduplication!
        sub_rec = CandidateRecord(
            original_prospect_id="NEW-001",
            company_name="NextJS Development Practice",
            discovery_source_url="https://clutch.co/developers",
            official_url="https://www.nextjsdevelopment.com/",
            canonical_domain="nextjsdevelopment.com",
        )
        checked = dedupe.check_candidate(sub_rec, seen)
        self.assertEqual(checked.history_status, "HISTORY_MATCH_EXCLUDE")
        self.assertEqual(checked.stage, "HISTORY_LOCK")

    def test_geo_seo_peer_separated_as_partner(self) -> None:
        rec = CandidateRecord(
            original_prospect_id="20261101-R02-083",
            company_name="Ozturksoft",
            discovery_source_url="https://www.goodfirms.co/directory/city/top-software-development-companies/ankara",
            official_url="https://ozturksoft.net/",
            canonical_domain="ozturksoft.net",
            claimed_size_range="2 - 9",
        )
        ok = verify_icp_and_segment(rec)
        self.assertFalse(ok)
        self.assertEqual(rec.segment, "PARTNER_CANDIDATE")

    def test_regulated_retail_isolated_as_research_only(self) -> None:
        rec = CandidateRecord(
            original_prospect_id="R-20261101-001",
            company_name="The Solent Cellar",
            discovery_source_url="https://www.vindependents.co.uk/",
            official_url="https://thesolentcellar.co.uk/",
            canonical_domain="thesolentcellar.co.uk",
            retail_category="wine",
        )
        ok = verify_icp_and_segment(rec)
        self.assertFalse(ok)
        self.assertEqual(rec.stage, "RESEARCH_ONLY")
        self.assertTrue(rec.is_retail_research)
        self.assertFalse(rec.send_ready)

    def test_1080x1350_png_rendering_and_outreach_qa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rec = CandidateRecord(
                original_prospect_id="TEST-MT7-001",
                company_name="Mt7 Private Limited",
                discovery_source_url="https://www.goodfirms.co/company/mt7-pvt-ltd",
                official_url="https://mt7.io/",
                canonical_domain="mt7.io",
                channel="WA",
                allocated_slot="WA-01",
                contact_url="https://wa.me/917800007500",
                contact_route_source="https://mt7.io/locations/bengaluru",
                primary_service="resort booking engines with Razorpay and two-way eZee PMS sync",
                observed_site_fact="Official resort page documents direct booking with Razorpay and eZee sync.",
                recipient_name="Abdul Adnan",
                recipient_verified=True,
            )
            render_geo_card_png(rec, Path(tmp))
            self.assertTrue(rec.image_completed)
            self.assertEqual(rec.png_dimensions, "1080x1350")
            self.assertEqual(rec.evidence_card_type, "STUDY_FACT_CARD")
            self.assertEqual(len(rec.png_sha256), 64)

            generate_personalized_first_touch(rec)
            evaluate_outreach_qa(rec)
            self.assertEqual(rec.outreach_qa_status, "PASS")
            self.assertGreaterEqual(rec.outreach_qa_score, 9)

    def test_study_fact_card_cannot_masquerade_as_strict_send_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dedupe = CrossChannelDedupeEngine()
            dedupe.mark_all_required_sources_loaded()
            pipeline = Daily27Pipeline(output_dir=Path(tmp), dedupe_engine=dedupe)
            rec = CandidateRecord(
                original_prospect_id="TEST-MT7-001",
                company_name="Mt7 Private Limited",
                discovery_source_url="https://www.goodfirms.co/company/mt7-pvt-ltd",
                official_url="https://mt7.io/",
                canonical_domain="mt7.io",
                claimed_size_range="2 - 9",
                channel="WA",
                contact_url="https://wa.me/917800007500",
                contact_route_source="https://mt7.io/locations/bengaluru",
                primary_service="resort booking engines with Razorpay and eZee PMS sync",
                observed_site_fact="Official resort page documents direct booking with Razorpay and eZee sync.",
            )
            report = pipeline.run([rec])
            validation = validate_production_pack(report, check_png_files=True)
            self.assertTrue(validation["structural_and_integrity_valid"])
            # Because AI test was not run, STUDY_FACT_CARD is ASSET_READY, not strict_send_ready!
            self.assertEqual(report["funnel_metrics"]["research_completed"], 1)
            self.assertEqual(report["funnel_metrics"]["image_completed"], 1)
            self.assertEqual(report["funnel_metrics"]["contact_qualified"], 1)
            self.assertEqual(report["funnel_metrics"]["strict_send_ready"], 0)



    def test_image_failure_preserves_verified_facts(self) -> None:
        """Requirement 12: A screenshot/image failure or budget cap must never wipe verified company facts."""
        with tempfile.TemporaryDirectory() as tmp:
            dedupe = CrossChannelDedupeEngine()
            dedupe.mark_all_required_sources_loaded()
            # Set max_image_budget=0 to simulate image generation skipped/blocked
            pipeline = Daily27Pipeline(output_dir=Path(tmp), dedupe_engine=dedupe, max_image_budget=0)
            rec = CandidateRecord(
                original_prospect_id="TEST-CACHE-001",
                company_name="Mt7 Private Limited",
                discovery_source_url="https://www.goodfirms.co/company/mt7-pvt-ltd",
                official_url="https://mt7.io/",
                canonical_domain="mt7.io",
                claimed_size_range="2 - 9",
                channel="WA",
                contact_url="https://wa.me/917800007500",
                contact_route_source="https://mt7.io/locations/bengaluru",
                primary_service="resort booking engines with Razorpay and eZee PMS sync",
                observed_site_fact="Official resort page documents direct booking with Razorpay and eZee sync.",
            )
            report = pipeline.run([rec])
            self.assertEqual(report["funnel_metrics"]["research_completed"], 1)
            self.assertEqual(report["funnel_metrics"]["contact_qualified"], 1)
            self.assertEqual(report["funnel_metrics"]["image_completed"], 0)
            # Verify facts are persisted in cache
            cached = pipeline.cache.facts.get("TEST-CACHE-001", {})
            self.assertEqual(cached.get("canonical_domain"), "mt7.io")
            self.assertIn("Razorpay", cached.get("observed_site_fact", ""))

    def test_automatic_backfill_replaces_disqualified_candidates(self) -> None:
        """Requirement 6 & 7: Disqualified candidates are logged and replaced by next qualified candidate without wasting images."""
        with tempfile.TemporaryDirectory() as tmp:
            dedupe = CrossChannelDedupeEngine()
            dedupe.mark_all_required_sources_loaded()
            pipeline = Daily27Pipeline(output_dir=Path(tmp), dedupe_engine=dedupe)
            bad_oversized = CandidateRecord(
                original_prospect_id="BAD-OVERSIZED-01",
                company_name="Softean",
                discovery_source_url="https://clutch.co/developers",
                official_url="https://softean.com/",
                canonical_domain="softean.com",
                claimed_size_range="50 - 249",
                channel="WA",
                contact_url="https://wa.me/919345199337",
            )
            bad_bot = CandidateRecord(
                original_prospect_id="BAD-BOT-02",
                company_name="OmegaLab",
                discovery_source_url="https://clutch.co/developers",
                official_url="https://omegalab.dev/",
                canonical_domain="omegalab.dev",
                claimed_size_range="2 - 9",
                channel="TG",
                contact_url="https://t.me/Omegalab_bot",
                observed_site_fact="Web3 studio",
            )
            good_tg = CandidateRecord(
                original_prospect_id="GOOD-TG-03",
                company_name="CODESPECT",
                discovery_source_url="https://clutch.co/developers/blockchain",
                official_url="https://www.codespect.net/",
                canonical_domain="codespect.net",
                claimed_size_range="2 - 9",
                channel="TG",
                contact_url="https://t.me/talfao",
                contact_route_source="https://www.codespect.net/",
                observed_site_fact="Smart contract security audits and API penetration testing.",
            )
            report = pipeline.run([bad_oversized, bad_bot, good_tg])
            slots = report["primary_slot_records"]
            self.assertEqual(len(slots), 1)
            self.assertEqual(slots[0]["original_prospect_id"], "GOOD-TG-03")
            self.assertTrue(slots[0]["image_completed"])
            # Disqualified candidates did NOT get PNGs rendered
            self.assertEqual(report["funnel_metrics"]["image_completed"], 1)



    def test_drive_delivery_manifest_pairing(self) -> None:
        """Requirement 9: Every record must verify 1-to-1 pairing of PNG, SHA256, draft, URL, source, ID, and QA status."""
        with tempfile.TemporaryDirectory() as tmp:
            dedupe = CrossChannelDedupeEngine()
            dedupe.mark_all_required_sources_loaded()
            pipeline = Daily27Pipeline(output_dir=Path(tmp), dedupe_engine=dedupe)
            rec = CandidateRecord(
                original_prospect_id="PAIR-001",
                company_name="Mt7 Private Limited",
                discovery_source_url="https://www.goodfirms.co/company/mt7-pvt-ltd",
                official_url="https://mt7.io/",
                canonical_domain="mt7.io",
                claimed_size_range="2 - 9",
                channel="WA",
                contact_url="https://wa.me/917800007500",
                contact_route_source="https://mt7.io/locations/bengaluru",
                primary_service="resort booking engines with Razorpay and eZee PMS sync",
                observed_site_fact="Official resort page documents direct booking with Razorpay and eZee sync.",
            )
            report = pipeline.run([rec])
            manifest = build_drive_delivery_manifest(report, drive_folder_url="https://drive.google.com/drive/folders/test")
            self.assertEqual(manifest["pairing_pass_count"], 1)
            self.assertEqual(manifest["pairing_fail_count"], 0)
            self.assertFalse(manifest["historical_ledgers_overwritten"])

    unittest.main(verbosity=2)
if __name__ == "__main__":
    unittest.main(verbosity=2)
