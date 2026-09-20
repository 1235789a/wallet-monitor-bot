"""Enrich a source-first pool from each company's supplied website only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prospect_os.contact_enrichment import enrich_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservatively enrich contacts for a RAW company pool")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--ignore-robots", action="store_true")
    args = parser.parse_args()
    try:
        records = json.loads(args.source.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("source must contain a JSON array")
        enriched = enrich_records(
            records, max_pages=max(1, min(args.max_pages, 10)),
            delay_seconds=max(0.0, args.delay), respect_robots=not args.ignore_robots,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "complete": True,
            "records": len(enriched),
            "completed": sum(item.get("contact_enrichment_status") == "completed" for item in enriched),
            "output": str(args.output),
            "messages_sent": 0,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
