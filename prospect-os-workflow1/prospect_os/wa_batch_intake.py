"""Strict Gemini discovery handoff, independent of verified outreach status."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlsplit

from .cross_channel_dedupe import REQUIRED_HISTORY_KEYS, CrossChannelDedupeEngine, normalize_domain_key
from .source_pool import canonical_domain, public_http_url
from .wa_website_preflight import valid_wa_candidate

SCHEMA = "multihub-wa-discovery-v1"
REQUIRED = {"original_prospect_id", "company_name", "website_url", "discovery_source_url"}
OPTIONAL = {"wa_hint", "activity_hint_url", "activity_hint_date", "size_hint_url", "founder_hint_url"}
PARTIAL_PILOT_MAX = 10


def validate_discovery(payload: object) -> list[dict]:
    """Reject malformed batches atomically; model claims never become verified flags."""
    if not isinstance(payload, dict) or set(payload) != {"schema", "records"} or payload["schema"] != SCHEMA:
        raise ValueError(f"Expected object with schema={SCHEMA!r} and records array")
    rows = payload["records"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("records must be a nonempty array")
    ids = set()
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not REQUIRED <= set(row) or set(row) - REQUIRED - OPTIONAL:
            raise ValueError(f"Row {i}: missing or unknown field (no READY or verification claims allowed)")
        if any(not isinstance(v, str) for v in row.values()) or any(not row[k].strip() for k in REQUIRED):
            raise ValueError(f"Row {i}: required fields must be nonempty strings; hints must be strings")
        pid = row["original_prospect_id"].strip()
        if pid in ids:
            raise ValueError(f"Row {i}: duplicate prospect ID")
        ids.add(pid)
        for key in ("website_url", "discovery_source_url", "activity_hint_url", "size_hint_url", "founder_hint_url"):
            value = row.get(key, "")
            if value and (not public_http_url(value) or urlsplit(value).username or urlsplit(value).password):
                raise ValueError(f"Row {i}: invalid public URL in {key}")
        website = normalize_domain_key(row["website_url"])
        source = normalize_domain_key(row["discovery_source_url"])
        if not website or not source or website == source or canonical_domain(row["discovery_source_url"]) in {"google.com", "bing.com", "search.yahoo.com"}:
            raise ValueError(f"Row {i}: independent discovery source required")
        if row.get("wa_hint") and not valid_wa_candidate(row["wa_hint"]):
            raise ValueError(f"Row {i}: invalid WhatsApp link hint")
    return rows


def load_discovery(path: Path) -> list[dict]:
    return validate_discovery(json.loads(path.read_text(encoding="utf-8")))


def history_precheck(path: Path | None) -> tuple[CrossChannelDedupeEngine, dict]:
    engine = CrossChannelDedupeEngine()
    count, error = 0, None
    if path is not None:
        try:
            count = engine.load_verified_history_index(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = f"{type(exc).__name__}: invalid/unavailable history index"
            engine = CrossChannelDedupeEngine()
    else:
        error = "history index not supplied"
    missing = [k for k in REQUIRED_HISTORY_KEYS if k not in engine.loaded_sources]
    return engine, {"history_records": count, "verified_categories": sorted(engine.loaded_sources),
                    "missing_categories": missing, "error": error, "scale_allowed": not missing,
                    "partial_pilot_max": PARTIAL_PILOT_MAX if missing else None}


def audit_legacy_csv(path: Path) -> dict:
    """Report width/quoting errors without repairing or trusting old model CSV."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, [])
        bad = []
        count = 0
        try:
            for row in reader:
                count += 1
                if len(row) != len(header):
                    bad.append({"line": reader.line_num, "fields": len(row)})
        except csv.Error:
            bad.append({"line": reader.line_num, "error": "CSV_QUOTING_ERROR"})
    return {"header_fields": len(header), "rows_parsed": count, "invalid_rows": bad,
            "valid": bool(header) and len(set(header)) == len(header) and not bad,
            "usable_for_wa_intake": False}
