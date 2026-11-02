"""Checkpoint, fact caching, retry, and budget controller (Requirement 12).

Ensures that a screenshot or image failure never zeroes out verified company facts.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .daily27_models import CandidateRecord


class PipelineCheckpointCache:
    """Persists verified candidate facts and stage progress across runs."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.facts_path = self.cache_dir / "verified_company_facts.json"
        self.checkpoint_path = self.cache_dir / "pipeline_checkpoint.json"
        self.facts: dict[str, dict[str, Any]] = self._load_json(self.facts_path, default={})

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return default
        return default

    def save_verified_facts(self, rec: CandidateRecord) -> None:
        """Persist verified company facts independently of screenshot/image status."""
        key = rec.original_prospect_id
        existing = self.facts.get(key, {})
        # Never overwrite non-empty verified facts with empty values
        updated = dict(existing)
        for field_name, val in rec.to_dict().items():
            if val not in (None, "", [], {}):
                updated[field_name] = val
        updated["last_cached_utc"] = datetime.now(timezone.utc).isoformat()
        self.facts[key] = updated
        self.facts_path.write_text(json.dumps(self.facts, ensure_ascii=False, indent=2), encoding="utf-8")

    def restore_cached_facts(self, rec: CandidateRecord) -> CandidateRecord:
        cached = self.facts.get(rec.original_prospect_id)
        if not cached:
            return rec
        for attr in (
            "official_url",
            "canonical_domain",
            "primary_service",
            "observed_site_fact",
            "recent_30d_activity_status",
            "recent_30d_activity_evidence",
            "recent_30d_activity_url",
            "buyer_question",
            "contact_url",
            "contact_route_source",
            "raw_web_screenshot_path",
            "raw_web_screenshot_sha256",
        ):
            if not getattr(rec, attr, None) and cached.get(attr):
                setattr(rec, attr, cached[attr])
        return rec

    def save_run_checkpoint(self, state: dict[str, Any]) -> Path:
        self.checkpoint_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.checkpoint_path


def run_with_retry(fn: Callable[[], Any], retries: int = 2, delay_sec: float = 0.05) -> tuple[bool, Any, str]:
    """Execute a step with bounded retries; isolate errors without wiping state."""
    last_err = ""
    for attempt in range(retries + 1):
        try:
            return True, fn(), ""
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(delay_sec)
    return False, None, last_err
