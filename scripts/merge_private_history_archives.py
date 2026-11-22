#!/usr/bin/env python3
"""Merge private archive manifest into an existing history index; no network or outreach."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.history_archive_merge import merge_archives


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("base", type=Path)
    p.add_argument("manifest", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("report", type=Path)
    a = p.parse_args()
    if a.output.resolve() == a.base.resolve():
        p.error("Write a new snapshot; do not overwrite the source")
    result, report = merge_archives(json.loads(a.base.read_text()), json.loads(a.manifest.read_text()))
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"records": len(result["records"]), "added": sum(x["added"] for x in report),
                      "archive_sources": len(report), "partial_sources": sum(x["read_status"] != "READ_VERIFIED" for x in report),
                      "daily_coverage": result["coverage"]["DAILY_PRESENTED"]["status"]}))


if __name__ == "__main__": main()
