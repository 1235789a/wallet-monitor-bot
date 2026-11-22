#!/usr/bin/env python3
"""Gemini WA-only public business route preflight, before expensive ICP research."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.wa_website_preflight import preflight_website


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array: original_prospect_id, company_name, website_url, discovery_source_url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--per-source", type=int, default=10, help="Bound cheap probes per independent source")
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    ids, probes, counts, output = set(), Counter(), Counter(), []
    for row in rows:
        pid, source = row.get("original_prospect_id"), row.get("discovery_source_url")
        if not pid or pid in ids or not source or not row.get("website_url"):
            raise ValueError("Each row needs a unique ID, source and official website URL")
        ids.add(pid)
        if probes[source] >= args.per_source:
            continue
        probes[source] += 1
        result = preflight_website(row, render=not args.static_only)
        counts[(source, result["wa_preflight_status"])] += 1
        output.append(result)
    args.output.write_text(json.dumps({"records": output, "source_metrics": [
        {"source": source, "status": status, "count": count, "probed": probes[source]}
        for (source, status), count in counts.items()], "send_ready": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
