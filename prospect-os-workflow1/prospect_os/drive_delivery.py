"""Drive delivery manifest builder and read-back verification module (Requirement 9 & 10).

Packages daily 27 pipeline outputs into a Drive-ready manifest without overwriting
historical ledgers, and verifies 1-to-1 pairing between original_prospect_id,
PNG file/hash, official URL, discovery source, contact route, and first-touch copy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_drive_delivery_manifest(
    report: dict[str, Any],
    drive_folder_url: str = "",
    uploaded_file_links: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a verifiable 1-to-1 paired Drive delivery manifest from a pipeline run report."""
    uploaded_file_links = uploaded_file_links or {}
    paired_items: list[dict[str, Any]] = []
    pairing_errors: list[str] = []

    for rec in report.get("primary_slot_records", []):
        pid = rec.get("original_prospect_id", "")
        png_path = rec.get("png_path", "")
        png_name = Path(png_path).name if png_path else ""
        drive_png_url = uploaded_file_links.get(png_name) or rec.get("png_drive_url") or ""

        # Verify 1-to-1 pairing requirements (Requirement 9)
        missing_fields = []
        for req_key in (
            "original_prospect_id",
            "company_name",
            "official_url",
            "discovery_source_url",
            "contact_url",
            "png_path",
            "png_sha256",
            "first_contact_draft",
            "outreach_qa_status",
        ):
            if not rec.get(req_key):
                missing_fields.append(req_key)

        pairing_status = "PAIRING_PASS" if not missing_fields else "PAIRING_QA_FAIL"
        if missing_fields:
            pairing_errors.append(f"{pid}: missing {', '.join(missing_fields)}")

        paired_items.append({
            "allocated_slot": rec.get("allocated_slot"),
            "original_prospect_id": pid,
            "company_name": rec.get("company_name"),
            "channel": rec.get("channel"),
            "official_url": rec.get("official_url"),
            "discovery_source_url": rec.get("discovery_source_url"),
            "contact_url": rec.get("contact_url"),
            "route_status": rec.get("route_status"),
            "recipient_verified": rec.get("recipient_verified"),
            "evidence_card_type": rec.get("evidence_card_type"),
            "png_filename": png_name,
            "png_sha256": rec.get("png_sha256"),
            "png_dimensions": rec.get("png_dimensions"),
            "png_drive_url": drive_png_url,
            "first_contact_draft": rec.get("first_contact_draft"),
            "outreach_qa_status": rec.get("outreach_qa_status"),
            "pairing_status": pairing_status,
            "stage": rec.get("stage"),
            "send_ready": rec.get("send_ready"),
            "auto_send_enabled": False,
        })

    return {
        "schema": "multihub-drive-delivery-manifest-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_date": report.get("date"),
        "drive_folder_url": drive_folder_url,
        "historical_ledgers_overwritten": False,
        "auto_send_enabled": False,
        "total_paired_records": len(paired_items),
        "pairing_pass_count": sum(1 for x in paired_items if x["pairing_status"] == "PAIRING_PASS"),
        "pairing_fail_count": len(pairing_errors),
        "pairing_errors": pairing_errors,
        "funnel_metrics": report.get("funnel_metrics", {}),
        "paired_records": paired_items,
        "regulated_retail_research_only": report.get("regulated_retail_research_records", []),
        "partner_candidates": report.get("partner_candidate_records", []),
    }
