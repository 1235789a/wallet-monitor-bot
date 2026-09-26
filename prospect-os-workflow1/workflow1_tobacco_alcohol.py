"""CLI for the independent lawful tobacco/alcohol prospect track."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from prospect_os.tobacco_alcohol_track import screen_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Source-first tobacco/alcohol prospect gate")
    parser.add_argument("source", type=Path, help="JSON array containing source-first records")
    parser.add_argument("--date", default=datetime.utcnow().date().isoformat())
    parser.add_argument("--requested", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_day = datetime.strptime(args.date, "%Y-%m-%d").date()
        rows = json.loads(args.source.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("source JSON must be an array")
        result = screen_records(rows, run_day, args.requested)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "complete": True,
            "counts": result["counts"],
            "requested": result["requested"],
            "shortfall": result["shortfall"],
            "output": str(args.output),
            "outreach_sent": result["outreach_sent"],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
