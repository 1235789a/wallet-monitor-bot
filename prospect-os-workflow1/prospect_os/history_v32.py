"""Read-only V3.2 provenance and contact-state audit for PRIVATE history snapshots.

This module never promotes history coverage or authorizes unsolicited messages.
It does not connect to Google Workspace; use an authorized export/snapshot.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any

from .cross_channel_dedupe import REQUIRED_HISTORY_KEYS, normalize_domain_key

_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.I)
_DOWNLOAD_METADATA = {"retrieved_at", "downloaded_at", "downloaded_at_utc"}


def semantic_sha256(value: Any) -> str:
    """Compare reserialized JSON despite volatile download timestamps.

    NOT a replacement for the SHA256 of the original source file. Only
    downloader-generated metadata keys are ignored, never business evidence.
    """
    def stable(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: stable(v) for k, v in obj.items() if k not in _DOWNLOAD_METADATA}
        if isinstance(obj, list):
            return [stable(v) for v in obj]
        return obj

    canonical = json.dumps(stable(value), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit_history_index(payload: dict) -> dict:
    """Audit declared source coverage without trusting inherited COMPLETE flags.

    Source inventory checks are metadata checks. They cannot establish whether
    all original Sheets, Docs, chat transcripts or recent batches exist.
    """
    if not isinstance(payload, dict) or payload.get("schema") != "multihub-history-index-v1":
        raise ValueError("Expected multihub-history-index-v1 private index")
    records, coverage = payload.get("records"), payload.get("coverage")
    if not isinstance(records, list) or not isinstance(coverage, dict):
        raise ValueError("History records and coverage object required")
    if any(not isinstance(r, dict) for r in records):
        raise ValueError("Every history record must be an object")
    inventory = payload.get("source_inventory", [])
    if not isinstance(inventory, list) or any(not isinstance(v, dict) for v in inventory):
        raise ValueError("source_inventory must be an array of objects")

    counts = Counter(str(r.get("source_tag") or "") for r in records)
    details = {}
    for tag in REQUIRED_HISTORY_KEYS:
        proof = coverage.get(tag)
        proof = proof if isinstance(proof, dict) else {}
        claimed_complete = proof.get("status") == "VERIFIED_COMPLETE"
        sources = proof.get("sources", [])
        sources = sources if isinstance(sources, list) else []
        sources = sorted(set(s for s in sources if isinstance(s, str) and s.startswith("https://")))
        inventory_evidenced = set()
        for entry in inventory:
            if (entry.get("source_tag") == tag and entry.get("read_status") == "READ_VERIFIED"
                    and isinstance(entry.get("record_count"), int) and entry["record_count"] >= 0
                    and isinstance(entry.get("sha256"), str) and _SHA256.fullmatch(entry["sha256"])
                    and entry.get("source_url") in sources):
                inventory_evidenced.add(entry["source_url"])
        expected_count = proof.get("record_count")
        count_match = type(expected_count) is int and counts[tag] == expected_count
        lacking = sorted(set(sources) - inventory_evidenced)
        # An inventory statement does not re-download or prove completeness of the source universe.
        inventory_attested = bool(sources) and not lacking and count_match
        reasons = []
        if not claimed_complete:
            reasons.append("NOT_DECLARED_COMPLETE")
        if not count_match:
            reasons.append("INDEX_COUNT_MISMATCH")
        if not sources:
            reasons.append("NO_SOURCE_SCOPE")
        if lacking:
            reasons.append("SOURCE_PROVENANCE_NOT_RECHECKED")
        details[tag] = {
            "declared_status": proof.get("status", "MISSING"),
            "index_records": counts[tag],
            "declared_records": expected_count,
            "source_count": len(sources),
            "source_inventory_with_digest": len(inventory_evidenced),
            "inventory_attested": inventory_attested,
            "coverage_issues": reasons,
        }
    names_without_domain = sum(
        bool(str(r.get("company_name") or "").strip())
        and not normalize_domain_key(str(r.get("canonical_domain") or ""))
        for r in records)
    return {
        "schema": "multihub-history-audit-v32",
        "total_source_records": len(records),
        "categories": details,
        "all_declared_complete_and_inventory_attested":
            all(not d["coverage_issues"] for d in details.values()),
        "rows_without_canonical_domain": names_without_domain,
        "semantic_sha256": semantic_sha256(payload),
        "history_clear_authorized": False,
        "send_ready": 0,
        "note": "This read-only audit cannot approve unenumerated sources, contact consent or sending.",
    }


def reconcile_contact_claims(claims: list[dict]) -> dict:
    """Conservative contact-stage reduction across contradictory source rows.

    READY is only a research state. A ledger's REPLIED claim alone is not
    evidence of an inbound message; raw conversation evidence needs separate
    human/source verification.
    """
    if not isinstance(claims, list) or any(not isinstance(c, dict) for c in claims):
        raise ValueError("claims must be an array of objects")
    found = set()
    for claim in claims:
        status = str(claim.get("status") or "").upper()
        note = str(claim.get("detail") or "").upper()
        text = status + " " + note
        if "NO_REPLY" in text or "NOT_REPLIED" in text or "暂无回复" in text or "未回复" in text:
            found.add("NO_REPLY")
        if status in {"REPLIED", "CUSTOMER_REPLIED", "INBOUND_REPLY"} or "已回复" in text or "收到回复" in text:
            found.add("REPLIED_CLAIM")
        if any(x in text for x in ("CONTACTED", "SENT", "已联系", "已发送", "已发出")):
            found.add("CONTACTED")
        if status in {"READY", "SEND_READY", "RESEARCH_READY"}:
            found.add("READY")
        if status in {"PAID", "PAYMENT_RECEIVED"}:
            found.add("PAID_CLAIM")

    issues = []
    if "REPLIED_CLAIM" in found and "NO_REPLY" in found:
        issues.append("REPLY_CONFLICT")
    elif "REPLIED_CLAIM" in found:
        issues.append("REPLY_EVIDENCE_REQUIRED")
    if "PAID_CLAIM" in found:
        issues.append("PAYMENT_EVIDENCE_REQUIRED")
    if "REPLIED_CLAIM" in found or "NO_REPLY" in found or "CONTACTED" in found or "PAID_CLAIM" in found:
        stage = "CONTACTED"
    elif "READY" in found:
        stage = "RESEARCH_READY_ONLY"
    else:
        stage = "UNKNOWN"
    return {
        "stage": stage,
        "claims_seen": sorted(found),
        "issues": issues,
        "manual_evidence_review": bool(issues),
        "eligible_for_new_first_contact": False if stage == "CONTACTED" else None,
        "contact_permission_verified": False,
        "send_ready": False,
    }
