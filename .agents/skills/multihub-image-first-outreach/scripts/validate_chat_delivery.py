#!/usr/bin/env python3
"""Validate MultiHub chat delivery manifest; does not test actual UI rendering or network."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = {"original_prospect_id", "company", "channel", "route_url",
            "image_drive_url", "inline_image_ref", "inline_image_render_verified",
            "route_click_verified", "message", "chat_block_emitted",
            "chat_delivery_status", "hold_reasons", "send_ready"}

def validate(items, expected=None, channel_counts=None):
    errors, seen, counts = [], set(), {"WA": 0, "FB": 0, "TG": 0}
    for i, item in enumerate(items, 1):
        label = f"row {i} ({item.get('original_prospect_id', 'UNKNOWN')})"
        missing = REQUIRED - set(item)
        if missing:
            errors.append(f"{label}: missing {sorted(missing)}")
            continue
        pid = item["original_prospect_id"]
        if not isinstance(pid, str) or not pid or pid in seen:
            errors.append(f"{label}: duplicate/empty original ID")
        seen.add(pid)
        channel = item["channel"]
        if channel not in counts:
            errors.append(f"{label}: invalid channel")
            continue
        counts[channel] += 1
        route = urlparse(item["route_url"])
        if route.scheme != "https":
            errors.append(f"{label}: route must be HTTPS")
        elif channel == "WA" and route.hostname not in ("wa.me", "api.whatsapp.com"):
            errors.append(f"{label}: not a WhatsApp chat link")
        elif channel == "TG" and route.hostname not in ("t.me", "telegram.me"):
            errors.append(f"{label}: not a Telegram link")
        elif channel == "FB" and route.hostname not in ("www.facebook.com", "facebook.com", "m.me", "www.messenger.com"):
            errors.append(f"{label}: not a Facebook/Messenger link")
        if not item["company"] or not item["message"]:
            errors.append(f"{label}: missing company or copy")
        if not isinstance(item["hold_reasons"], list):
            errors.append(f"{label}: hold_reasons must be array")
        image_ref = item["inline_image_ref"]
        if not isinstance(image_ref, str) or not image_ref or image_ref.startswith("sandbox:") or image_ref.lower().endswith((".zip", ".pdf")):
            errors.append(f"{label}: invalid inline image ref")
        if item["chat_delivery_status"] == "CHAT_DELIVERED":
            if not all(item[k] is True for k in ("chat_block_emitted", "inline_image_render_verified", "route_click_verified")):
                errors.append(f"{label}: CHAT_DELIVERED without verified chat block/image/route")
        elif item["chat_delivery_status"] != "CHAT_DELIVERY_UNVERIFIED":
            errors.append(f"{label}: invalid chat delivery status")
        if item["send_ready"] is True and item["hold_reasons"]:
            errors.append(f"{label}: SEND_READY conflicts with HOLD reasons")
    if expected is not None and len(items) != expected:
        errors.append(f"expected {expected} rows, got {len(items)}")
    if channel_counts is not None and counts != channel_counts:
        errors.append(f"channel counts mismatch: expected {channel_counts}, got {counts}")
    return {"rows": len(items), "channel_counts": counts, "errors": errors}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument("--expected", type=int)
    p.add_argument("--wa", type=int)
    p.add_argument("--fb", type=int)
    p.add_argument("--tg", type=int)
    args = p.parse_args()
    items = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(items, list):
        raise SystemExit("chat_delivery.json must be an array")
    cc = {"WA": args.wa, "FB": args.fb, "TG": args.tg} if None not in (args.wa, args.fb, args.tg) else None
    result = validate(items, args.expected, cc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))

if __name__ == "__main__":
    main()
