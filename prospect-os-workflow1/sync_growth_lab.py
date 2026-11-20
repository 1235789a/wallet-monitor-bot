"""Read protected Lab status and extend an existing Prospect OS batch. Never sends outreach."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from prospect_os.growth_lab import archive_card, atomic_json, enrich_card


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def confirm_share(base_url: str, report: dict) -> dict:
    relative = report["path"]
    if not relative.startswith("/r/") or not relative.removeprefix("/r/").replace("_", "").replace("-", "").isalnum():
        raise ValueError("Expected a relative Growth Lab share path")
    url = urljoin(base_url, relative)
    host = urlsplit(url).hostname
    accessible = False
    if urlsplit(url).scheme == "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        try:
            with urlopen(Request(url, method="HEAD", headers={"User-Agent": "MultiHubPreviewBot/1.0"}), timeout=12) as response:
                accessible = response.status == 200 and "noindex" in response.headers.get("X-Robots-Tag", "")
        except (HTTPError, URLError):
            pass
    return {**report, "url": url if accessible else None, "accessible": accessible}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Existing Prospect OS batch JSON")
    parser.add_argument("assignments", type=Path, help="Private object keyed by original prospect ID")
    parser.add_argument("output", type=Path, help="New enriched batch JSON")
    parser.add_argument("--history", type=Path, required=True, help="Append-only Lab history directory")
    args = parser.parse_args()
    if args.output.resolve() == args.batch.resolve():
        raise ValueError("Choose an output path distinct from the historical batch")
    base_url = os.environ["LAB_URL"].rstrip("/")
    token = os.environ["LAB_ADMIN_TOKEN"]
    source = read_json(args.batch)
    assignments = read_json(args.assignments)
    cards = source["primary_slot_records"]
    unresolved = assignments.keys() - {card.get("original_prospect_id") for card in cards}
    if unresolved:
        raise ValueError(f"Assignments have no matching Prospect OS card: {', '.join(sorted(unresolved))}")

    enriched = []
    for card in cards:
        assignment = assignments.get(card.get("original_prospect_id"))
        if not assignment:
            enriched.append(card)
            continue
        endpoint = f"{base_url}/api/lab/companies/{assignment['companyId']}"
        with urlopen(Request(endpoint, headers={"Authorization": f"Bearer {token}"}), timeout=15) as response:
            observation = json.load(response)
        preview = confirm_share(base_url, assignment["report"]) if assignment.get("report") else None
        item = enrich_card(card, observation, drafts=assignment.get("drafts", {}), preview=preview)
        enriched.append(item)

    for card in enriched:
        if "growth_lab" in card:
            archive_card(card, args.history)
    output = {**source, "primary_slot_records": enriched, "growth_lab_sync_at": datetime.now(timezone.utc).isoformat()}
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(args.output, (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
