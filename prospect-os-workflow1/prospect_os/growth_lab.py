"""Attach Growth Lab observations to existing Prospect OS cards and append history."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from prospect_os.outreach_humanizer import review_conversation_copy

STAGES = {
    "DISCOVERED", "QUALIFIED", "TESTING", "VERIFIED", "PREVIEW_READY", "REVIEWED",
    "SEND_READY", "SENT", "REPLIED", "PAID", "DELIVERED", "RETESTED", "HOLD",
}


def domain(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def enrich_card(card: dict, observation: dict, *, drafts: dict, preview: dict | None) -> dict:
    """Preserve the original acquisition status and attach the Lab workflow."""
    if card.get("original_prospect_id") != observation.get("prospect_id"):
        raise ValueError("Growth Lab status belongs to another prospect")
    if not domain(card["official_url"]) or domain(card["official_url"]) != domain(observation["website"]):
        raise ValueError("Growth Lab and prospect official domains differ")
    stage = observation["stage"]
    if stage not in STAGES:
        raise ValueError(f"Unexpected Growth Lab stage: {stage}")

    baseline = observation.get("baseline", {})
    evidence_ready = baseline.get("runs") == 6
    report = None
    if preview:
        report = next((item for item in observation.get("reports", [])
                       if item["id"] == preview["reportId"] and not item.get("revoked_at")
                       and item.get("expires_at") == preview["expiresAt"]), None)
    url = preview.get("url") if preview and report and preview.get("accessible") else None
    reason = observation.get("hold_reason")
    share_required = stage in {"PREVIEW_READY", "REVIEWED", "SEND_READY", "SENT", "REPLIED"}
    if share_required and not url:
        stage, reason = "HOLD", "The customer link is not externally accessible."
    elif not evidence_ready and stage not in {"DISCOVERED", "QUALIFIED", "TESTING", "HOLD"}:
        stage, reason = "HOLD", "The baseline evidence is incomplete."

    reviewed_drafts = {}
    if card.get("do_not_contact"):
        drafts = {}
    for kind, draft in drafts.items():
        issues = review_conversation_copy(draft["english"], stage=draft["stage"],
                                         evidence_ready=evidence_ready and bool(url))
        reviewed_drafts[kind] = {**draft, "lint_issues": issues, "human_review_required": True}

    return {
        **card,
        "growth_lab": {
            "stage": stage,
            "underlying_stage": observation.get("previousStage", observation["stage"]),
            "hold_reason": reason,
            "company_id": observation["id"],
            "report_url": url,
            "opportunity": observation.get("opportunity", {}).get("headline"),
            "evidence_status": "verified" if evidence_ready else "incomplete",
            "baseline": baseline,
            "drafts": reviewed_drafts,
            "access": {key: report.get(key, 0) if report else 0 for key in
                       ("confirmed_visits", "preview_bots", "unverified_loads")},
            "order_status": "verified_paid" if observation.get("orders") else "no_verified_payment",
            "delivery_status": "delivered" if (observation.get("deliverable") or {}).get("deliveredAt") else "pending",
            "retests": observation.get("retests", []),
            "auto_send_enabled": False,
        },
    }


def atomic_json(path: Path, payload: bytes) -> None:
    partial = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with partial.open("xb") as stream:
        os.chmod(partial, 0o600)
        stream.write(payload)
    partial.replace(path)


def archive_card(card: dict, directory: Path) -> Path:
    """Keep earlier snapshots intact and make replays idempotent."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (json.dumps(card, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    key = hashlib.sha256(card["original_prospect_id"].encode()).hexdigest()[:16]
    revision = hashlib.sha256(payload).hexdigest()
    snapshot_path = directory / f"{key}-{revision}.json"
    if not snapshot_path.exists():
        atomic_json(snapshot_path, payload)
    return snapshot_path
