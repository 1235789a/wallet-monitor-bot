#!/usr/bin/env python3
"""Main executable CLI entrypoint for MultiHub GEO Daily 27 Production Pipeline.

Connects:
  Independent Directory / RAW Pool Ingestion -> Website & Entity Verification ->
  Cross-Channel History Deduplication -> Low-Cost ICP & Channel Screening ->
  Automatic Slot Backfill -> 1080x1350 English GEO PNG Rendering ->
  Personalized First-Touch Copy & Outreach QA -> Validation & Funnel Report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prospect-os-workflow1"))
sys.path.insert(0, str(ROOT / "scripts"))

from prospect_os.cross_channel_dedupe import CrossChannelDedupeEngine
from prospect_os.daily27_pipeline import Daily27Pipeline
from prospect_os.raw_pool_loader import load_all_raw_and_checkpoint_candidates
from validate_daily27_production import validate_production_pack


def build_dedupe_engine(
    history_dir: Path,
    downloads_dir: Path,
    strict_exclude_unsent_daily_locks: bool = False,
) -> CrossChannelDedupeEngine:
    engine = CrossChannelDedupeEngine()
    # Load authoritative historical delivered/contacted ledgers
    engine.load_csv_ledger("103_MASTER", history_dir / "candidates_103.csv")
    engine.load_csv_ledger("112_MASTER", history_dir / "master_112.csv")
    engine.load_csv_ledger("CENTRAL_HISTORY", history_dir / "reconciliation_ledger.csv")
    engine.load_json_ledger("CENTRAL_HISTORY", history_dir / "dedup_215.json")
    engine.load_json_ledger("CENTRAL_HISTORY", history_dir / "dedup_2026_10_24.json")
    engine.load_csv_ledger("FB_PRESENTED", history_dir / "fb_lock.csv")

    # Load DAILY_PRESENTED locks (2026-10-31 and 2026-11-01)
    # In continuation mode (default), unsent research locks register original_prospect_id for continuation
    # while marking DAILY_PRESENTED as checked; in strict net-new mode, they are excluded as HISTORY_LOCK.
    engine.load_csv_ledger(
        "DAILY_PRESENTED",
        downloads_dir / "presented_records_20261031.csv",
        is_in_progress=not strict_exclude_unsent_daily_locks,
    )
    engine.load_csv_ledger(
        "DAILY_PRESENTED",
        downloads_dir / "presented_lock_20261101.csv",
        is_in_progress=not strict_exclude_unsent_daily_locks,
    )
    engine.mark_all_required_sources_loaded()
    return engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MultiHub GEO Daily 27 Production Pipeline")
    parser.add_argument(
        "--downloads-dir",
        type=Path,
        default=Path("/working_dir/c_3134177ccee79b95/downloads"),
        help="Path to downloaded RAW checkpoints and evidence archives",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=Path("/working_dir/c_88e8855a999448da/downloads"),
        help="Path to historical 103/112/central/FB ledgers",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/wallet-monitor-bot/outputs/daily27_run"),
        help="Output directory for generated PNGs, checkpoints, and reports",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Execution date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-image-budget",
        type=int,
        default=35,
        help="Maximum 1080x1350 PNG images to render in this run",
    )
    parser.add_argument(
        "--strict-exclude-unsent-daily-locks",
        action="store_true",
        help="Exclude even unsent RESEARCH_PRESENTED checkpoint rows from 2026-10-31/2026-11-01",
    )
    args = parser.parse_args()

    dedupe_engine = build_dedupe_engine(
        history_dir=args.history_dir,
        downloads_dir=args.downloads_dir,
        strict_exclude_unsent_daily_locks=args.strict_exclude_unsent_daily_locks,
    )
    candidates = load_all_raw_and_checkpoint_candidates(args.downloads_dir)

    pipeline = Daily27Pipeline(
        output_dir=args.output_dir,
        dedupe_engine=dedupe_engine,
        max_image_budget=args.max_image_budget,
        render_provisional_cards=True,
    )
    report = pipeline.run(candidates, run_date=args.date)
    validation = validate_production_pack(report, check_png_files=True)

    summary_out = {
        "run_date": args.date,
        "mode": "strict_net_new" if args.strict_exclude_unsent_daily_locks else "resume_and_backfill",
        "validation_passed": validation["structural_and_integrity_valid"],
        "quota_27_strict_send_ready_met": validation["quota_fully_met_27_send_ready"],
        "funnel_metrics": report["funnel_metrics"],
        "loss_breakdown": report["loss_breakdown"],
        "capacity_estimate": report["capacity_estimate"],
        "validation_errors": validation["errors"],
        "validation_warnings": validation["warnings"],
    }
    print(json.dumps(summary_out, ensure_ascii=False, indent=2))
    return 0 if validation["structural_and_integrity_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
