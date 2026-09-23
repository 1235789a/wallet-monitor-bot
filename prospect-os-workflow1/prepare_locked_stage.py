"""Gate externally prepared buyer-query, audit and outreach JSON against Sample Lock.

This does not generate claims, queries, contacts or messages. Each stage reads
and preserves exactly the locked cohort before a later stage can consume it.
"""

import argparse
import json
from pathlib import Path

from prospect_os.sample_lock import DEFAULT_LOCK, align_to_lock, load_lock, verify_final_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a manually/AI prepared research stage")
    parser.add_argument("source", type=Path)
    parser.add_argument("--stage", required=True, choices=("buyer-query", "contact-discovery",
                                                        "audit", "outreach"))
    parser.add_argument("--sample-lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        lock = load_lock(args.sample_lock)
        rows = align_to_lock(json.loads(args.source.read_text(encoding="utf-8")), lock,
                             rejected_path=args.output.with_name('rejected-not-in-sample-lock.json'))
        verify_final_ids(rows, lock)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"stage": args.stage, "companies": len(rows),
                          "sample_lock_verified": True, "output": str(args.output)}))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        args.output.unlink(missing_ok=True)
        print(json.dumps({"stage": args.stage, "sample_lock_verified": False,
                          "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
