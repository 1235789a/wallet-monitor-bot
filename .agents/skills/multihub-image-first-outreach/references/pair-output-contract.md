# Required one-to-one pairing contract

All rows are joined by **original_prospect_id**, never row number, company nickname, or index. Export `pairs.json` (array) and `pairs.md` (human copy).

## Required fields
- `original_prospect_id`: immutable canonical history/CRM identifier.
- `company`, `website`, `channel`, `route_url`, `route_verified`, `recipient_role_verified`.
- `image_file_name`, `image_drive_url`, `image_sha256`, `image_evidence_type` (`ORIGINAL_CAPTURE` or `TEXT_EVIDENCE_CARD`), `raw_screenshot_url` (nullable), `raw_screenshot_sha256` (nullable).
- `source_urls` nonempty array, `checked_at`, `observation`, `inference` (nullable), `buyer_question`, `message`, `cta`.
- `history_dedupe_status`, `contact_qa_status`, `image_qa_status`, `send_ready` boolean, `sent_at` nullable, `reply_at` nullable.

## Invariants
1. Exactly one output row for each scoped, non-excluded original ID.
2. All `image_drive_url` values point to matching, distinct finished PNGs. No markdown-only 'image' and no shared image file across companies.
3. Image-specific factual claim, the linked sourced observation, and message must align without unsupported inference.
4. `image_sha256` must equal actual generated image bytes. Full SHA-256, not truncated. Never claim raw screen capture when none exists.
5. For honest attached-image language, message and photo are packaged **together** for manual sending. If the sender will not actually attach the image, substitute a no-attachment variant; do not falsely imply it is attached.
6. `send_ready` true requires: dedupe clear; current verified business recipient and valid channel; source and raw-evidence gate passed; image matches; allowed industry/channel; manual review. `TEXT_EVIDENCE_CARD` cannot meet the raw original-capture requirement from v3 alone.
7. `sent_at` remains null until actual externally confirmed send. `reply_at` remains null until received and proven.
8. Sources and dates are captured at research time; do not manufacture 'today checked' based on file write time.
9. WhatsApp phone may have separate correct number; save clickable actual `wa.me` only when verified. A TG `t.me` address may be a bot/channel; validate exact entity.
10. Every user-facing result groups Company, Image link, Message and QA state in the same block. Image and message must never require index matching.

## Minimal local deterministic QA
- Parse manifest; verify all IDs unique.
- Confirm all linked assets have appropriate company identity and SHA-256.
- Reject null/invalid Drive image URLs, message-free items, stock placeholders, mismatched source and image.
- Review unsupported claims and policy manually; code alone cannot prove sourcing, recipient identity or permission.

## Historical record
Each deliverable marks `presented_at` once per canonical ID. Presented is not contacted, replied, opted out, or sold. Old delivered batches cannot be passed off as newly discovered.
