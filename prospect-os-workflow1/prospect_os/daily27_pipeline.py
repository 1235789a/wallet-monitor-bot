"""End-to-End MultiHub GEO Daily 27 Production Pipeline (15 WA + 2 TG + 10 FB).

Implements the complete 11-stage workflow:
  1. Independent Directory Discovery & RAW Pool Ingestion (no re-searching from scratch)
  2. Official Website & Legal/Brand Entity Verification
  3. Cross-Channel Historical Deduplication (preserving original_prospect_id)
  4. Low-Cost ICP Qualification (2-20 preferred, <=50 max; GEO/SEO peer -> PARTNER_CANDIDATE;
     3 Regulated Retail -> RESEARCH_ONLY)
  5. Channel Route Verification (WA business route, TG non-bot/non-group/non-channel, FB page vs person)
  6. Recent 30-Day Activity & Buyer Scenario Verification + Automatic Slot Replacement / Backfill
  7. Authentic Evidence Archival (raw website screenshots / text + live AI test records if present)
  8. 1080x1350 English GEO PNG Generation (only after low-cost screening passes; SHA256 verified)
  9. Personalized First-Touch Copy Generation & Outreach QA Gate
  10. Strict Four-Counter Funnel Accounting (research_completed, image_completed, contact_qualified, send_ready)
  11. Local & Google Drive Delivery Manifest Generation (auto_send_enabled=False)
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .checkpoint_cache import PipelineCheckpointCache, run_with_retry
from .cross_channel_dedupe import CrossChannelDedupeEngine, normalize_domain_key
from .daily27_models import (
    DAILY_QUOTA_TARGETS,
    RETAIL_EXPERIMENT_QUOTA,
    TOTAL_DAILY_QUOTA,
    AITestRecord,
    CandidateRecord,
)
from .geo_image_renderer import compute_file_sha256, render_geo_card_png
from .icp_and_channel_gate import (
    verify_channel_route,
    verify_icp_and_segment,
    verify_off_search_discovery,
)
from .outreach_qa_gate import evaluate_outreach_qa, generate_personalized_first_touch


class Daily27Pipeline:
    """Production orchestrator for MultiHub GEO Daily 27 pipeline."""

    def __init__(
        self,
        output_dir: Path,
        dedupe_engine: CrossChannelDedupeEngine | None = None,
        max_image_budget: int = 40,
        render_provisional_cards: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.png_dir = self.output_dir / "png_cards"
        self.cache = PipelineCheckpointCache(self.output_dir / "cache")
        self.dedupe = dedupe_engine or CrossChannelDedupeEngine()
        self.max_image_budget = max_image_budget
        self.render_provisional_cards = render_provisional_cards

    def run(
        self,
        candidates: list[CandidateRecord],
        run_date: str | None = None,
    ) -> dict[str, Any]:
        run_date = run_date or date.today().isoformat()
        now_utc = datetime.now(timezone.utc).isoformat()
        seen_in_batch: set[str] = set()

        processed_records: list[CandidateRecord] = []
        partner_pool: list[CandidateRecord] = []
        retail_research_pool: list[CandidateRecord] = []
        rejected_or_hold_pool: list[CandidateRecord] = []

        # Eligible pools per channel for automatic slot allocation & backfill
        channel_qualified_pools: dict[str, list[CandidateRecord]] = {"WA": [], "TG": [], "FB": []}
        channel_provisional_pools: dict[str, list[CandidateRecord]] = {"WA": [], "TG": [], "FB": []}

        # Loss tracking counters across stages
        loss_breakdown = {
            "total_raw_ingested": len(candidates),
            "failed_off_search_or_missing_site": 0,
            "excluded_by_history_dedupe": 0,
            "separated_as_geo_seo_partner": 0,
            "isolated_as_regulated_retail_research": 0,
            "failed_icp_headcount_or_independence": 0,
            "failed_channel_route_missing_or_invalid": 0,
            "held_channel_unverified_human_or_fb_page_only": 0,
            "passed_low_cost_screening": 0,
        }

        for rec in candidates:
            rec.last_updated_utc = now_utc
            rec = self.cache.restore_cached_facts(rec)

            # Stage 1: Cross-channel historical deduplication (runs on name/domain/account before expensive checks)
            rec = self.dedupe.check_candidate(rec, seen_in_batch)
            if rec.history_status != "HISTORY_CLEAR":
                loss_breakdown["excluded_by_history_dedupe"] += 1
                rejected_or_hold_pool.append(rec)
                processed_records.append(rec)
                continue

            # Stage 2: Low-cost ICP qualification (headcount <=50, GEO/SEO partner separation, regulated retail isolation)
            icp_ok = verify_icp_and_segment(rec)
            if not icp_ok:
                if rec.segment == "PARTNER_CANDIDATE":
                    loss_breakdown["separated_as_geo_seo_partner"] += 1
                    partner_pool.append(rec)
                elif rec.segment == "REGULATED_RETAIL_RESEARCH":
                    loss_breakdown["isolated_as_regulated_retail_research"] += 1
                    rec.research_completed = bool(rec.official_url and rec.observed_site_fact)
                    self.cache.save_verified_facts(rec)
                    retail_research_pool.append(rec)
                else:
                    loss_breakdown["failed_icp_headcount_or_independence"] += 1
                    rejected_or_hold_pool.append(rec)
                processed_records.append(rec)
                continue

            # Stage 3: Off-search independent directory & official website verification
            if not verify_off_search_discovery(rec):
                rec.stage = "HOLD_DISCOVERY_OR_SITE"
                loss_breakdown["failed_off_search_or_missing_site"] += 1
                rejected_or_hold_pool.append(rec)
                processed_records.append(rec)
                continue

            # Mark research completed for verified B2B candidates with website facts
            rec.research_completed = bool(rec.official_url and (rec.observed_site_fact or rec.primary_service))
            self.cache.save_verified_facts(rec)

            # Stage 5: Channel route verification (WA / TG / FB)
            route_ok = verify_channel_route(rec)
            ch = rec.channel if rec.channel in {"WA", "TG", "FB"} else "UNASSIGNED"
            if ch == "UNASSIGNED" or rec.route_status in {
                "NO_HTTPS_CONTACT_ROUTE",
                "INVALID_WA_HOST",
                "INVALID_OR_PLACEHOLDER_WA_NUMBER",
                "INVALID_TG_HOST",
                "REJECT_TG_GROUP_OR_CHANNEL_INVITE",
                "INVALID_TG_HANDLE",
                "REJECT_TG_BOT",
                "INVALID_FB_HOST",
                "INVALID_FB_URL",
            }:
                rec.stage = "HOLD_INVALID_OR_MISSING_CHANNEL"
                loss_breakdown["failed_channel_route_missing_or_invalid"] += 1
                rejected_or_hold_pool.append(rec)
                processed_records.append(rec)
                continue

            if route_ok and rec.contact_qualified:
                rec.low_cost_screen_passed = True
                rec.stage = "ICP_PASS"
                loss_breakdown["passed_low_cost_screening"] += 1
                channel_qualified_pools[ch].append(rec)
            else:
                # Has a public route (e.g. FB company page or TG public corp handle), kept as provisional hold
                rec.low_cost_screen_passed = False
                rec.stage = "HOLD_RECIPIENT_OR_ROUTE_TYPE"
                loss_breakdown["held_channel_unverified_human_or_fb_page_only"] += 1
                channel_provisional_pools[ch].append(rec)

            processed_records.append(rec)

        # Stage 6: Automatic Slot Allocation & Replacement Backfill (15 WA, 2 TG, 10 FB = 27)
        # Regulated retail slots (1 wine, 1 vape, 1 adult) are tracked separately as RESEARCH_ONLY
        # and NEVER counted as sendable leads; core B2B candidates fill the sendable seats!
        allocated_primary: dict[str, list[CandidateRecord]] = {"WA": [], "TG": [], "FB": []}
        shortfalls: dict[str, int] = {}

        for ch, target_count in DAILY_QUOTA_TARGETS.items():
            # Prioritize candidates with verified recipient, then recent 30d activity, then 2-20 employee size
            qualified_sorted = sorted(
                channel_qualified_pools[ch],
                key=lambda r: (
                    1 if r.recipient_verified else 0,
                    1 if r.raw_web_screenshot_path else 0,
                    1 if r.recent_30d_activity_status.startswith("PASS") or r.recent_30d_activity_status.startswith("VERIFIED") else 0,
                    1 if (r.estimated_max_employees or 50) <= 20 else 0,
                ),
                reverse=True,
            )
            selected = qualified_sorted[:target_count]
            # If qualified candidates are fewer than target_count, fill remaining research slots from provisional pool
            # (strictly keeping their stage as HOLD and contact_qualified=False so they never fake SEND_READY!)
            if len(selected) < target_count and self.render_provisional_cards:
                needed = target_count - len(selected)
                prov_sorted = sorted(
                    channel_provisional_pools[ch],
                    key=lambda r: (
                        1 if r.raw_web_screenshot_path else 0,
                        1 if r.recent_30d_activity_status.startswith("PASS") else 0,
                    ),
                    reverse=True,
                )
                selected.extend(prov_sorted[:needed])

            for idx, item in enumerate(selected, 1):
                item.allocated_slot = f"{ch}-{idx:02d}"
            allocated_primary[ch] = selected
            # True contact-qualified shortfall vs target
            qualified_count = sum(1 for r in selected if r.contact_qualified)
            shortfalls[ch] = max(0, target_count - qualified_count)

        # Select the 3 regulated retail research slots (1 wine, 1 vape, 1 adult) for parallel tracking
        selected_retail: list[CandidateRecord] = []
        for cat in RETAIL_EXPERIMENT_QUOTA:
            matches = [r for r in retail_research_pool if r.retail_category == cat]
            if matches:
                chosen = matches[0]
                chosen.allocated_slot = f"RETAIL-{cat.upper()}-01"
                selected_retail.append(chosen)

        # Stage 7, 8 & 9: Expensive 1080x1350 PNG Generation + Personalized First-Touch & QA Gate
        # Only run for candidates that passed low-cost screening or occupy active research slots within budget
        images_rendered = 0
        all_slot_records = (
            allocated_primary["WA"]
            + allocated_primary["TG"]
            + allocated_primary["FB"]
        )

        for rec in all_slot_records:
            if images_rendered >= self.max_image_budget:
                rec.hold_or_reject_reasons.append("Skipped PNG generation due to max_image_budget limit")
                continue

            if rec.raw_web_screenshot_path and Path(rec.raw_web_screenshot_path).exists():
                rec.raw_web_screenshot_sha256 = compute_file_sha256(Path(rec.raw_web_screenshot_path))

            ok, _, err = run_with_retry(lambda r=rec: render_geo_card_png(r, self.png_dir), retries=2)
            if ok and rec.image_completed:
                images_rendered += 1
            else:
                # Screenshot/image failure does NOT wipe out verified company facts! (Requirement 12)
                rec.image_completed = False
                rec.hold_or_reject_reasons.append(f"Image generation error (facts preserved): {err}")
                self.cache.save_verified_facts(rec)
                continue

            # Generate personalized first-touch copy and run Outreach QA Gate
            generate_personalized_first_touch(rec)
            evaluate_outreach_qa(rec)

            # Determine final stage & send_ready status (Requirement 8, 9, 10)
            rec.strict_evidence_verified = rec.ai_test.is_strict_live_proof
            # Can a record be marked SEND_READY?
            # Must have: CORE_B2B, HISTORY_CLEAR, contact_qualified=True, recipient_verified=True,
            # image_completed=True, outreach_qa_status="PASS", and not retail research.
            # Furthermore, if strict AI evidence is required, STUDY_FACT_CARD stays ASSET_READY (not strict AI proof).
            if (
                rec.segment == "CORE_B2B"
                and not rec.is_retail_research
                and rec.history_status == "HISTORY_CLEAR"
                and rec.low_cost_screen_passed
                and rec.contact_qualified
                and rec.recipient_verified
                and rec.image_completed
                and rec.outreach_qa_status == "PASS"
            ):
                if rec.strict_evidence_verified:
                    rec.send_ready = True
                    rec.stage = "SEND_READY"
                else:
                    # Has verified founder/human route + verified website fact card + QA pass,
                    # but uses STUDY_FACT_CARD (AI live test not run) -> ASSET_READY_WEBSITE_FACT_ONLY
                    rec.send_ready = False
                    rec.stage = "ASSET_READY"
                    rec.hold_or_reject_reasons.append(
                        "HOLD_STRICT_AI_PROOF: Website fact card (STUDY_FACT_CARD) & founder route verified, "
                        "but live AI recommendation screenshot proof not yet archived"
                    )
            elif rec.image_completed and rec.outreach_qa_status == "PASS" and rec.low_cost_screen_passed:
                rec.send_ready = False
                rec.stage = "ASSET_READY"
            else:
                rec.send_ready = False

            self.cache.save_verified_facts(rec)

        # Stage 10: Compute Four-Counter Funnel Metrics & Capacity Reserve Estimation
        funnel_metrics = {
            "total_raw_candidates_evaluated": len(processed_records),
            "research_completed": sum(1 for r in processed_records if r.research_completed),
            "low_cost_icp_and_route_passed": sum(1 for r in processed_records if r.low_cost_screen_passed),
            "image_completed": sum(1 for r in all_slot_records if r.image_completed),
            "image_completed_live_ai_proof": sum(
                1 for r in all_slot_records if r.image_completed and r.evidence_card_type == "AI_LIVE_TEST_CARD"
            ),
            "image_completed_study_fact_card": sum(
                1 for r in all_slot_records if r.image_completed and r.evidence_card_type == "STUDY_FACT_CARD"
            ),
            "contact_qualified": sum(1 for r in processed_records if r.contact_qualified),
            "contact_qualified_with_verified_human_recipient": sum(
                1 for r in processed_records if r.contact_qualified and r.recipient_verified
            ),
            "complete_package_ready_for_human_review": sum(
                1
                for r in all_slot_records
                if r.research_completed
                and r.image_completed
                and r.outreach_qa_status == "PASS"
                and r.contact_qualified
            ),
            "strict_send_ready": sum(1 for r in all_slot_records if r.send_ready),
            "partner_candidates_separated": len(partner_pool),
            "regulated_retail_research_only": len(retail_research_pool),
            "by_channel_qualified": {
                ch: sum(1 for r in channel_qualified_pools[ch] if r.contact_qualified)
                for ch in ("WA", "TG", "FB")
            },
            "by_channel_human_recipient_verified": {
                ch: sum(1 for r in channel_qualified_pools[ch] if r.contact_qualified and r.recipient_verified)
                for ch in ("WA", "TG", "FB")
            },
            "by_channel_slot_filled": {
                ch: len(allocated_primary[ch]) for ch in ("WA", "TG", "FB")
            },
            "by_channel_shortfall_for_verified_route": shortfalls,
        }

        # Estimate required RAW candidate pool to reach 27 qualified leads
        raw_total = max(1, len(processed_records))
        wa_pass_rate = funnel_metrics["by_channel_qualified"]["WA"] / raw_total
        tg_pass_rate = funnel_metrics["by_channel_qualified"]["TG"] / raw_total
        fb_pass_rate = funnel_metrics["by_channel_qualified"]["FB"] / raw_total
        overall_pkg_rate = funnel_metrics["complete_package_ready_for_human_review"] / raw_total

        capacity_estimate = {
            "observed_overall_route_pass_rate": round(funnel_metrics["contact_qualified"] / raw_total, 4),
            "observed_human_recipient_pass_rate": round(
                funnel_metrics["contact_qualified_with_verified_human_recipient"] / raw_total, 4
            ),
            "estimated_raw_needed_for_15_WA_routes": (
                int(15 / wa_pass_rate) + 1 if wa_pass_rate > 0 else 450
            ),
            "estimated_raw_needed_for_2_TG_human_routes": (
                int(2 / tg_pass_rate) + 1 if tg_pass_rate > 0 else 200
            ),
            "estimated_raw_needed_for_10_FB_person_routes": (
                int(10 / fb_pass_rate) + 1 if fb_pass_rate > 0 else 600
            ),
            "estimated_total_raw_reserve_for_daily_27": max(
                int(27 / overall_pkg_rate) + 1 if overall_pkg_rate > 0 else 500,
                320,
            ),
        }

        report = {
            "schema": "multihub-daily27-production-v1",
            "date": run_date,
            "generated_at_utc": now_utc,
            "target_total": TOTAL_DAILY_QUOTA,
            "targets_by_channel": DAILY_QUOTA_TARGETS,
            "retail_experiment_targets": RETAIL_EXPERIMENT_QUOTA,
            "auto_send_enabled": False,
            "funnel_metrics": funnel_metrics,
            "loss_breakdown": loss_breakdown,
            "capacity_estimate": capacity_estimate,
            "primary_slot_records": [r.to_dict() for r in all_slot_records],
            "regulated_retail_research_records": [r.to_dict() for r in selected_retail],
            "partner_candidate_records": [r.to_dict() for r in partner_pool],
            "hold_or_rejected_summary": [
                {
                    "original_prospect_id": r.original_prospect_id,
                    "company_name": r.company_name,
                    "canonical_domain": r.canonical_domain,
                    "stage": r.stage,
                    "reasons": r.hold_or_reject_reasons,
                }
                for r in rejected_or_hold_pool
            ],
        }

        self.cache.save_run_checkpoint(report)
        report_path = self.output_dir / f"daily27_run_report_{run_date}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
