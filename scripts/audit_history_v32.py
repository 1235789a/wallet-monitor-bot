#!/usr/bin/env python3
"""Audit a private history index and optional contact-claim file. NO WRITES to index."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prospect-os-workflow1"))
from prospect_os.history_v32 import audit_history_index, reconcile_contact_claims


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history-index", required=True, type=Path)
    p.add_argument("--claims", type=Path, help="Private JSON: {subjects: [{key, claims: [{status, detail}]}]}")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    if args.output.resolve() in {args.history_index.resolve(), args.claims.resolve() if args.claims else None}:
        p.error("Output must not overwrite the index or claims")
    try:
        report = audit_history_index(json.loads(args.history_index.read_text(encoding="utf-8")))
        if args.claims:
            obj = json.loads(args.claims.read_text(encoding="utf-8"))
            items = obj.get("subjects") if isinstance(obj, dict) else None
            if not isinstance(items, list):
                raise ValueError("claims must have a subjects array")
            results = []
            keys = set()
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"].strip():
                    raise ValueError("Each subject must have a nonempty key")
                if item["key"] in keys:
                    raise ValueError("Duplicate subject key")
                keys.add(item["key"])
                outcome = reconcile_contact_claims(item.get("claims"))
                results.append({"key": item["key"], **outcome})
            report["contact_reviews"] = results
            report["contact_conflicts"] = sum("REPLY_CONFLICT" in r["issues"] for r in results)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "error": str(exc)}))
        return 2
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "AUDITED_READ_ONLY",
                      "source_records": report["total_source_records"],
                      "declared_complete_with_inventory":
                          report["all_declared_complete_and_inventory_attested"],
                      "contact_conflicts": report.get("contact_conflicts", 0),
                      "history_clear_authorized": False, "send_ready": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
