"""Score imported intent events from permitted, already-collected sources.

Examples:

    python intent_signal_cli.py events.json --source generic --output scored.json
    python intent_signal_cli.py chatwoot-webhooks.json --source chatwoot --output scored.json

The CLI is read-only with respect to external channels.  It never sends a
WhatsApp/Telegram message or creates a payment request.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prospect_os.intent_signals import events_from_payloads, score_events, utc_now_iso


def main() -> int:
    parser = argparse.ArgumentParser(description="Score observed reply and purchase signals")
    parser.add_argument("source", type=Path, help="JSON array of collected events/webhook payloads")
    parser.add_argument("--source", dest="source_kind", default="generic", choices=[
        "generic", "n8n", "manual", "agent_reach", "chatwoot", "mautic", "posthog"
    ])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payloads = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(payloads, list):
        raise ValueError("source JSON must be an array")
    events = events_from_payloads(payloads, args.source_kind)
    result = {
        "generated_at": utc_now_iso(),
        "source_kind": args.source_kind,
        "events_accepted": len(events),
        "read_only": True,
        "outreach_sent": False,
        "score": score_events(events),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "events_accepted": len(events),
        "reply_willingness_score": result["score"]["reply_willingness_score"],
        "purchase_intent_score": result["score"]["purchase_intent_score"],
        "output": str(args.output),
        "outreach_sent": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
