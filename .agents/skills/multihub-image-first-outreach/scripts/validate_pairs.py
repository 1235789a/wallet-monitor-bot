#!/usr/bin/env python3
"""Fail closed on mismatched MultiHub image/message pairs. No network or sending."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def validate(items, image_dir=None):
    errors = []
    ids = set()
    urls = set()
    filenames = set()
    ready = 0
    for n, item in enumerate(items, 1):
        lead = item.get("original_prospect_id")
        label = f"item {n} ({lead or 'UNKNOWN'})"
        if not lead or lead in ids:
            errors.append(f"{label}: empty/duplicate original_prospect_id")
        ids.add(lead)
        name = item.get("company", "")
        if not name:
            errors.append(f"{label}: missing company")
        png = item.get("image_file_name", "")
        if not png.lower().endswith(".png") or png in filenames:
            errors.append(f"{label}: absent/duplicate PNG filename")
        filenames.add(png)
        url = item.get("image_drive_url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ("drive.google.com", "docs.google.com") or "/file/d/" not in parsed.path or url in urls:
            errors.append(f"{label}: invalid/duplicate image Drive URL")
        urls.add(url)
        message = item.get("message", "")
        if not message or len(message.split()) > 60 or message.count("?") != 1:
            errors.append(f"{label}: message empty, over 60 words, or lacks one CTA")
        if "I attached" not in message and "I've attached" not in message:
            errors.append(f"{label}: message must describe the actual attached image")
        if "Could I share" in message or "Can I share" in message:
            errors.append(f"{label}: cannot ask to send image that is already attached")
        sources = item.get("source_urls", [])
        if not sources or not all(isinstance(x, str) and x.startswith("https://") for x in sources):
            errors.append(f"{label}: nonempty source_urls required")
        sha = item.get("image_sha256", "")
        if not isinstance(sha, str) or len(sha) != 64 or any(x not in "0123456789abcdef" for x in sha.lower()):
            errors.append(f"{label}: invalid full image SHA256")
        if image_dir:
            file = image_dir / png
            if not file.is_file():
                errors.append(f"{label}: local PNG missing: {file}")
            elif hashlib.sha256(file.read_bytes()).hexdigest() != sha:
                errors.append(f"{label}: image sha mismatch: {file}")
        is_ready = item.get("send_ready") is True
        if is_ready:
            ready += 1
            if item.get("image_evidence_type") != "ORIGINAL_CAPTURE" or not item.get("raw_screenshot_url"):
                errors.append(f"{label}: SEND_READY requires real screenshot evidence")
            if item.get("history_dedupe_status") != "CLEAR":
                errors.append(f"{label}: SEND_READY requires resolved history")
            if item.get("route_verified") != "VERIFIED_MARKETING_RECIPIENT":
                errors.append(f"{label}: SEND_READY requires verified marketing recipient")
        if item.get("sent_at") and not item.get("send_ready"):
            errors.append(f"{label}: sent timestamp exists without send-ready evidence; review needed")
    return {"count": len(items), "unique_ids": len(ids), "unique_images": len(urls),
            "send_ready": ready, "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs_json", type=Path)
    parser.add_argument("--image-dir", type=Path, help="Verify local full SHA-256 of images")
    args = parser.parse_args()
    pairs = json.loads(args.pairs_json.read_text(encoding="utf-8-sig"))
    if not isinstance(pairs, list):
        raise SystemExit("pairs.json must be an array")
    result = validate(pairs, args.image_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
