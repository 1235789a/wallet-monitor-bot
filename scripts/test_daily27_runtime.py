#!/usr/bin/env python3
from __future__ import annotations
import sys
import tempfile
import unittest
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prospect-os-workflow1"))
sys.path.insert(0, str(ROOT / "scripts"))
from validate_daily27_production import is_valid_tg_url, is_valid_wa_url, validate_production_pack
from prospect_os.cross_channel_dedupe import CrossChannelDedupeEngine
from prospect_os.daily27_models import AITestRecord, ActivityProof, CandidateRecord
from prospect_os.fb_activity_gate import check_activity_proof, verify_facebook_activity, apply_fb_activity_manifest
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



    def _fresh_activity_proofs(self, folder: Path) -> tuple[ActivityProof, ActivityProof]:
        now = datetime.now(timezone.utc)
        screenshot = folder / "real-public-post.png"
        screenshot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"evidence image pixels" * 20)
        digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        common = {
            "activity_date": now.date().isoformat(),
            "checked_at_utc": now.isoformat(),
            "excerpt": "We launched a new customer-facing software product this week.",
            "subject_confirmed": True,
            "capture_path": str(screenshot),
            "capture_sha256": digest,
        }
        business = ActivityProof(
            source_url="https://example.org/news/customer-launch-2026",
            subject_type="COMPANY",
            **common,
        )
        personal = ActivityProof(
            source_url="https://www.facebook.com/founder.name/posts/123456789",
            subject_type="CONTACT_PERSON",
            **common,
        )
        return business, personal

    def test_fb_activity_rejects_legacy_pass_without_real_posts(self) -> None:
        rec = CandidateRecord(
            original_prospect_id="OLD-FB", company_name="Old client",
            discovery_source_url="https://clutch.co/developers",
            channel="FB", recipient_verified=True, fb_route_type="PERSON",
            recent_30d_activity_status="PASS_COMPANY_BLOG_2026-06-30",
            recent_30d_activity_evidence="June 2026 publication",
            recent_30d_activity_url="https://example.org/",
        )
        self.assertFalse(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))
        self.assertEqual(rec.recent_30d_activity_status, "HOLD_FB_ACTIVITY_UNVERIFIED")
        self.assertTrue(any("DATE_MISSING" in v for v in rec.hold_or_reject_reasons))
        self.assertFalse(rec.fb_activity_verified)

    def test_fb_activity_accepts_two_exact_recent_reviewed_captures(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            business, personal = self._fresh_activity_proofs(Path(folder))
            rec = CandidateRecord(
                original_prospect_id="OK-FB", company_name="Studio",
                discovery_source_url="https://clutch.co/developers",
                channel="FB", recipient_verified=True, fb_route_type="PERSON",
                business_activity_proof=business, fb_activity_proof=personal,
            )
            self.assertTrue(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))
            self.assertTrue(rec.fb_activity_verified)
            self.assertEqual(rec.recent_30d_activity_status, "VERIFIED_FB_PUBLIC_POST_WITH_CAPTURE_30D")

    def test_fb_activity_rejects_old_future_unknown_and_expired_review(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            business, personal = self._fresh_activity_proofs(Path(folder))
            today = datetime.now(timezone.utc).date()
            personal.activity_date = (today - timedelta(days=31)).isoformat()
            self.assertTrue(any("STALE_31D" in s for s in check_activity_proof(personal, as_of=today, kind="FB_POST")))
            personal.activity_date = (today + timedelta(days=1)).isoformat()
            self.assertTrue(any("FUTURE_DATE" in s for s in check_activity_proof(personal, as_of=today, kind="FB_POST")))
            personal.activity_date = today.isoformat()
            personal.checked_at_utc = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
            self.assertTrue(any("REVIEW_EXPIRED" in s for s in check_activity_proof(personal, as_of=today, kind="FB_POST")))
            personal.checked_at_utc = datetime.now(timezone.utc).isoformat()
            personal.source_url = "https://www.facebook.com/founder.name/"
            self.assertTrue(any("NOT_A_SPECIFIC_PUBLIC_POST" in s for s in check_activity_proof(personal, as_of=today, kind="FB_POST")))
            personal.source_url = "https://www.facebook.com/founder.name/posts/123456789"
            personal.capture_sha256 = "0" * 64
            self.assertTrue(any("HASH_MISMATCH" in s for s in check_activity_proof(personal, as_of=today, kind="FB_POST")))

    def test_fb_activity_rejects_page_only_even_with_public_post(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            business, personal = self._fresh_activity_proofs(Path(folder))
            rec = CandidateRecord(
                original_prospect_id="FB-PAGE", company_name="Company",
                discovery_source_url="https://clutch.co/developers",
                channel="FB", recipient_verified=False, fb_route_type="COMPANY_PAGE",
                business_activity_proof=business, fb_activity_proof=personal,
            )
            self.assertFalse(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))
            self.assertIn("HOLD_FB_ACTIVITY_NO_VERIFIED_PERSONAL_RECIPIENT", rec.hold_or_reject_reasons)

    def test_fb_pipeline_refuses_stale_post_even_if_route_person_verified(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            from prospect_os.cross_channel_dedupe import CrossChannelDedupeEngine
            dedupe = CrossChannelDedupeEngine()
            dedupe.mark_all_required_sources_loaded()
            business, personal = self._fresh_activity_proofs(Path(folder))
            personal.activity_date = (datetime.now(timezone.utc).date() - timedelta(days=70)).isoformat()
            rec = CandidateRecord(
                original_prospect_id="FB-STALE-01",
                company_name="Fresh Studio",
                discovery_source_url="https://clutch.co/developers",
                official_url="https://freshstudio.example/",
                canonical_domain="freshstudio.example",
                claimed_size_range="2 - 9",
                channel="FB",
                contact_url="https://www.facebook.com/founder.name",
                fb_route_type="PERSON",
                recipient_verified=True,
                observed_site_fact="Independent service studio.",
                business_activity_proof=business,
                fb_activity_proof=personal,
            )
            pipeline = Daily27Pipeline(output_dir=Path(folder) / "run", dedupe_engine=dedupe)
            report = pipeline.run([rec])
            self.assertEqual(report["loss_breakdown"]["held_fb_activity_not_verified"], 1)
            self.assertEqual(report["funnel_metrics"]["by_channel_slot_filled"]["FB"], 0)
            self.assertEqual(report["funnel_metrics"]["fb_activity_verified"], 0)
            self.assertEqual(report["funnel_metrics"]["strict_send_ready"], 0)
            self.assertEqual(report["hold_or_rejected_summary"][0]["stage"], "HOLD_FB_ACTIVITY")

    def test_fb_manifest_import_rechecks_evidence_instead_of_trusting_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            business, personal = self._fresh_activity_proofs(Path(folder))
            rec = CandidateRecord(
                original_prospect_id="FB-MANIFEST", company_name="Agency",
                discovery_source_url="https://clutch.co/developers",
                channel="FB", recipient_verified=True, fb_route_type="PERSON",
            )
            file = Path(folder) / "fb_activity_evidence.json"
            from dataclasses import asdict
            file.write_text(json.dumps({"records": [{
                "original_prospect_id": rec.original_prospect_id,
                "business_activity_proof": asdict(business),
                "fb_activity_proof": asdict(personal),
                "send_ready": True,
                "recent_30d_activity_status": "PASS",
            }]}), encoding="utf-8")
            self.assertEqual(apply_fb_activity_manifest([rec], file), 1)
            self.assertFalse(rec.send_ready)
            self.assertFalse(rec.fb_activity_verified)
            self.assertTrue(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))

    def test_fb_cross_platform_exact_posts_and_separate_route(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            business, personal = self._fresh_activity_proofs(Path(folder))
            for url in ("https://x.com/founder/status/123456789",
                        "https://www.linkedin.com/posts/founder_public-news-activity-123456789-ab12",
                        "https://www.instagram.com/reel/aBc123/"):
                personal.source_url = url
                rec = CandidateRecord("CROSS", "Studio", "https://clutch.co/developers",
                                      channel="FB", recipient_verified=True, fb_route_type="PERSON",
                                      business_activity_proof=business, fb_activity_proof=personal)
                self.assertTrue(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))
                rec.fb_route_type = "COMPANY_PAGE"
                self.assertFalse(verify_facebook_activity(rec, datetime.now(timezone.utc).date()))
            for url in ("https://x.com/founder", "https://www.linkedin.com/in/founder",
                        "https://www.instagram.com/founder/", "https://example.org/events/founder"):
                personal.source_url = url
                self.assertTrue(any("NOT_A_SPECIFIC_PUBLIC_POST" in s for s in
                                    check_activity_proof(personal, as_of=datetime.now(timezone.utc).date(), kind="FB_POST")))

    def test_missing_history_never_clears_no_match(self) -> None:
        rec = CandidateRecord("NEW", "Example Studio", "https://clutch.co/developers",
                              official_url="https://example-studio.example")
        engine = CrossChannelDedupeEngine()
        self.assertEqual(engine.check_candidate(rec, set()).history_status, "HOLD_HISTORY_INCOMPLETE")

    def test_partial_index_matches_but_does_not_grant_clearance(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder) / "history.json"
            snapshot.write_text(json.dumps({
                "schema": "multihub-history-index-v1",
                "checked_on": datetime.now(timezone.utc).date().isoformat(),
                "records": [{"source_tag": "CENTRAL_HISTORY", "company_name": "Old Studio",
                             "canonical_domain": "old-studio.example"}],
                "coverage": {"CENTRAL_HISTORY": {"status": "VERIFIED_COMPLETE",
                             "sources": ["central"], "record_count": 1}},
            }), encoding="utf-8")
            engine = CrossChannelDedupeEngine()
            self.assertEqual(engine.load_verified_history_index(snapshot), 1)
            old = CandidateRecord("OLD", "Old Studio", "https://clutch.co/developers",
                                  official_url="https://old-studio.example")
            new = CandidateRecord("NEW", "New Studio", "https://clutch.co/developers",
                                  official_url="https://new-studio.example")
            self.assertEqual(engine.check_candidate(old, set()).history_status, "HISTORY_MATCH_EXCLUDE")
            self.assertEqual(engine.check_candidate(new, set()).history_status, "HOLD_HISTORY_INCOMPLETE")

if __name__ == "__main__":
    unittest.main(verbosity=2)
