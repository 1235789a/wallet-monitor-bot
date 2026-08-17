"""Run the optional read-only Trafilatura evidence pass for a candidate JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from prospect_os.source_tools import audit_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit supplied Prospect OS source URLs without contacting prospects")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_json(args.source, args.output)
    print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

