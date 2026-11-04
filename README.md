# MultiHub GEO / Prospect OS

Evidence-first business discovery, verification, buyer-intent research, credible GEO evidence images, and human-reviewed prospect outreach.

**Legacy retirement:** This repository originally hosted the Whale Wallet Tracker Telegram bot (Ethereum/BSC/Tron scanners, smart-money signals, wallet subscriptions and USDT verification). That *application* is removed from the current source tree. It remains in Git history; this cleanup does not delete prior commits, branches, deployed services, secrets or external payment records.

## Active components

- [Prospect OS](prospect-os-workflow1/README.md): company discovery, ICP checks, buyer intent, history reconciliation, route review and QA.
- [Facebook GEO prospect skill](.agents/skills/facebook-geo-prospect/SKILL.md): company/owner identification, Facebook Page versus person, opt-outs, cross-channel exclusions.
- [Image-first outreach skill](.agents/skills/multihub-image-first-outreach/SKILL.md): genuine source evidence, 1080×1350 image, 1:1 company/image/message/ID pairing and Drive verification.
- [GEO outreach copy](.codex/skills/geo-outreach-copy/SKILL.md): accurate industry insight, plain-language first contacts, honest AI visibility claims.
- [Outreach policy](prospect-os-workflow1/system/outreach-message-policy.md) and [evidence policy](.codex/skills/geo-outreach-copy/references/precision-evidence.md).

## Current daily target — 2026-10-29 Drive operating specification

15 WhatsApp (3 lanes × 5), 2 direct Telegram (2 lanes × 1), 10 Facebook (2 accounts × 5), **27 primary prospects**; up to 10 additional FB backups, not counted toward 27. No same-company cross-channel double count.

This is a goal, not an unconditional READY guarantee. Legacy Prospect OS's separate 30-company sample lock remains a different workflow. [Draft PR #9](https://github.com/1235789a/wallet-monitor-bot/pull/9) still contains the earlier 12 WA + 2 TG daily validator: it requires its own reviewed synchronization and is **not** merged by this cleanup.

Require source-backed ICP, relevant buyer problem, exact historical dedupe scope, appropriately verified business recipient and channel, genuine raw screenshot/evidence and traceable asset hashes, matched evidence PNG + natural 25–45-word first-contact draft. Real ChatGPT/Gemini/Perplexity outcomes need actual original model-answer evidence; site text or Google snippets are not model tests.

Track separately: discovered, ICP-qualified, recipient-verified, raw capture archived, PNG paired, READY, user-confirmed sent, actual replies, real sales/payment. HOLD does not count as READY; prepared is not sent. Respect consent, platform contact rules and all opt-outs; never auto-send.

## Authoritative operating references

- [Evidence-image system v2.0 / 27 per day](https://docs.google.com/document/d/1AUn5Oopy7-VzAIt9oPxloZ2prJlQrzfkuS6JKtZCoGU/edit)
- [27-prospect Work execution requirements](https://docs.google.com/document/d/1TRRJh2zvG5cK5vzasBBw_O-7lJkx56_kA3lMqf-W1nU/edit)
- [Growth Engine v3 SOP / older 14-per-day baseline](https://docs.google.com/document/d/1Hyxbj7GTKEn1-l8Ewyo4P9Y5sjgsRUAO_nUJnSHz7BY/edit)
- [112-company ledger + V3_QA_QUEUE + V3_DAILY_LOG](https://docs.google.com/spreadsheets/d/1zxgVIDyUJIAWWPgV0RFNOWW96IR6fXW0Fn045U6xDlk/edit)

## Basic checks

```bash
cd prospect-os-workflow1
python -m unittest discover -v
```

Real recipient identity, public evidence, image-to-message pairing, human review and verified outcomes are not proved by a unit test. Deleting the old wallet GitHub Actions workflow only stops that scheduled workflow once the cleanup reaches the default branch; any external Railway/VPS deployment must be retired separately. The repository name is unchanged for existing links.
