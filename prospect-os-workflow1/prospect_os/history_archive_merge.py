"""Reconcile private historical delivery archives without granting global clearance."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .cross_channel_dedupe import normalize_domain_key
from .source_pool import public_http_url


def _field(row: dict, *keys: str) -> str:
    return next((row[k].strip() for k in keys if isinstance(row.get(k), str) and row[k].strip()), "")


def archive_rows(path: Path, selector: str) -> tuple[list[tuple[int, dict]], list[int]]:
    if selector == "csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, [])
            if not header or len(set(header)) != len(header) or not {"company", "website"} <= set(header):
                raise ValueError("CSV identity headers missing or duplicated")
            rows, invalid = [], []
            try:
                for row in reader:
                    if len(row) != len(header):
                        invalid.append(reader.line_num)
                    else:
                        rows.append((reader.line_num, dict(zip(header, row))))
            except csv.Error:
                invalid.append(reader.line_num)
            return rows, invalid
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload if selector == "array" else payload[selector]
    if not isinstance(items, list):
        raise ValueError("Archive selector is not an array")
    return ([(i, row) for i, row in enumerate(items, 1) if isinstance(row, dict)],
            [i for i, row in enumerate(items, 1) if not isinstance(row, dict)])


def merge_archives(base: dict, specs: list[dict]) -> tuple[dict, list[dict]]:
    """Append source-backed identity locks; each source locator is idempotent.

    READ_VERIFIED means the archive rows parsed, not that any candidate was sent,
    verified for outreach or globally deduplicated. Never promote daily coverage.
    """
    if base.get("schema") != "multihub-history-index-v1":
        raise ValueError("Unsupported history index")
    records = base["records"]
    seen = {(r.get("source_url"), r.get("source_locator")) for r in records}
    inventory = base.setdefault("source_inventory", [])
    report = []
    for spec in specs:
        url, selector, kind = spec["source_url"], spec["selector"], spec["record_kind"]
        if not public_http_url(url) or kind not in {"RESEARCH_PRESENTED", "IN_PROGRESS"}:
            raise ValueError("Expected source URL and explicit archive record kind")
        path = Path(spec["path"])
        parsed, invalid = archive_rows(path, selector)
        count = added = 0
        for ordinal, row in parsed:
            name = _field(row, "company_name", "company", "name")
            website = _field(row, "canonical_domain", "domain", "website", "official_url", "site")
            domain = normalize_domain_key(website) if website and not any(c.isspace() for c in website) else ""
            if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain, re.I):
                domain = ""
            if not name:
                invalid.append(ordinal)
                continue
            locator = f"{selector} row {ordinal}"
            count += 1
            if (url, locator) in seen:
                continue
            contact = _field(row, "contact_url", "route_url", "contact_route", "whatsapp_link", "telegram_url", "facebook_person_url", "fb_personal_url", "contact")
            if not public_http_url(contact):
                contact = ""
            pid = _field(row, "original_prospect_id", "prospect_id")
            if not pid:
                pid = "ARCHIVE-" + hashlib.sha256((url + "#" + locator).encode()).hexdigest()[:20]
            records.append({"source_tag": "DAILY_PRESENTED", "source_url": url,
                            "source_locator": locator, "record_kind": kind,
                            "company_name": name, "canonical_domain": domain,
                            "contact_url": contact, "original_prospect_id": pid,
                            "original_status": _field(row, "stage", "status", "work_status", "history_status") or "ARCHIVED_RESEARCH"})
            seen.add((url, locator))
            added += 1
        entry = {"source_tag": "DAILY_PRESENTED", "source_url": url, "source_locator": selector,
                 "read_status": "READ_VERIFIED" if not invalid else "PARTIAL_EXTRACT",
                 "record_count": count, "invalid_rows": sorted(set(invalid)),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if not any(x.get("source_url") == url and x.get("source_locator") == selector for x in inventory):
            inventory.append(entry)
        report.append({**entry, "added": added})
    daily = base["coverage"]["DAILY_PRESENTED"]
    daily["status"] = "PARTIAL"
    daily["record_count"] = sum(r.get("source_tag") == "DAILY_PRESENTED" for r in records)
    daily["sources"] = sorted(set(daily.get("sources", []) + [s["source_url"] for s in specs]))
    return base, report
