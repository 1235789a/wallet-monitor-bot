"""Immutable company identity boundary between RAW sampling and research.

The lock carries RAW snapshots so missing downstream rows can be retained without
discovering replacements.  Evidence, contacts and qualification remain mutable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sampling import sampling_record_key

DEFAULT_LOCK = Path("runs/buyer-sprint/sampled-lock.json")
IDENTITY_FIELDS = ("source_id", "identity_key", "company_name", "sampling_vertical", "sampling_track")
DRIFT_ERROR = "ERROR: downstream introduced unsampled companies"


def make_lock(rows: list[dict[str, Any]], *, seed: int, limit: int,
              summary: dict[str, Any] | None = None) -> dict[str, Any]:
    samples = []
    for row in rows:
        item = {"id": sampling_record_key(row), **{field: row.get(field) for field in IDENTITY_FIELDS},
                "record": dict(row)}
        samples.append(item)
    ids = [item["id"] for item in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("sample contains duplicate company ids")
    return {"seed": seed, "generated_at": datetime.now(timezone.utc).isoformat(),
            "limit": limit, "sample_ids": ids, "samples": samples,
            **({"sampling_summary": summary} if summary is not None else {})}


def load_lock(path: Path) -> dict[str, Any]:
    lock = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = lock["samples"]
    ids = lock["sample_ids"]
    if not isinstance(samples, list) or not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise ValueError("invalid or empty sample lock")
    if ids != [item["id"] for item in samples] or len(ids) > lock["limit"]:
        raise ValueError("sample lock ids/limit mismatch")
    for item in samples:
        if sampling_record_key(item["record"]) != item["id"] or any(
            item.get(field) != item["record"].get(field) for field in IDENTITY_FIELDS
        ):
            raise ValueError("sample lock identity mismatch")
    return lock


def freeze_sample(path: Path, rows: list[dict[str, Any]], *, seed: int, limit: int,
                  summary: dict[str, Any] | None = None) -> dict[str, Any]:
    proposed = make_lock(rows, seed=seed, limit=limit, summary=summary)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(proposed, stream, ensure_ascii=False, indent=2)
    except FileExistsError:
        existing = load_lock(path)
        if (existing["seed"], existing["limit"], existing["sample_ids"]) != (
            seed, limit, proposed["sample_ids"]
        ) or existing["samples"] != proposed["samples"]:
            raise ValueError("existing sample lock differs; use a new run directory")
    return load_lock(path)


def align_to_lock(rows: list[dict[str, Any]], lock: dict[str, Any], *,
                  rejected_path: Path | None = None) -> list[dict[str, Any]]:
    """Reject drift before a sales output; preserve missing locked companies in place."""
    if not isinstance(rows, list):
        raise ValueError("downstream input must be a JSON array")
    allowed = {item["id"]: item for item in lock["samples"]}
    accepted: dict[str, dict[str, Any]] = {}
    rejected = []
    for row in rows:
        key = sampling_record_key(row)
        item = allowed.get(key)
        if item is None or any(field in row and row[field] != item.get(field) for field in IDENTITY_FIELDS):
            rejected.append({**row, "status": {"rejected_reason": "not_in_sample_lock"},
                             "sample_lock_verified": False})
        elif key in accepted:
            rejected.append({**row, "status": {"rejected_reason": "duplicate_sample_id"},
                             "sample_lock_verified": False})
        else:
            accepted[key] = {**item["record"], **row, "sample_lock_verified": True}
    if rejected:
        if rejected_path:
            rejected_path.parent.mkdir(parents=True, exist_ok=True)
            rejected_path.write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(f"{DRIFT_ERROR}: {len(rejected)} rejected; see {rejected_path}")
    aligned = []
    for item in lock["samples"]:
        row = accepted.get(item["id"])
        if row is None:
            row = {**item["record"], "status": {"research_failed": True, "contact_missing": True},
                   "sample_lock_verified": True}
        aligned.append(row)
    verify_final_ids(aligned, lock)
    return aligned


def verify_final_ids(rows: list[dict[str, Any]], lock: dict[str, Any]) -> None:
    ids = [sampling_record_key(row) for row in rows]
    if ids != lock["sample_ids"] or len(ids) != len(set(ids)):
        raise ValueError(DRIFT_ERROR + ": final_company_ids != sampled_lock_ids")
