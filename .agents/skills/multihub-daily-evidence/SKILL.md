---
name: multihub-daily-evidence
description: Produce MultiHub's daily evidence-first 12 WhatsApp + 2 Telegram prospect pack using the live Drive identity history, research, screenshots, source manifest, annotated PNGs, and non-deceptive first messages. Trigger on 每日获客、重装获客系统、12WA2TG、证据图首联、获客日交付.
---

# MultiHub Daily Evidence v3.0 — evidence first

## Authority and scope
This skill is the operational **daily selection & packaging** layer. It extends but never weakens:
- `prospect-os-workflow1/system/outreach-message-policy.md`
- `.codex/skills/geo-outreach-copy/SKILL.md`
- `.codex/skills/geo-outreach-copy/references/precision-evidence.md`
- `.agents/skills/facebook-geo-prospect/SKILL.md` for cross-channel history semantics.
- Drive master SOP: https://docs.google.com/document/d/1Hyxbj7GTKEn1-l8Ewyo4P9Y5sjgsRUAO_nUJnSHz7BY/edit
- v3 queue and daily log (tabs of legacy spreadsheet): https://docs.google.com/spreadsheets/d/1zxgVIDyUJIAWWPgV0RFNOWW96IR6fXW0Fn045U6xDlk/edit

Do not conflate delivered, sent, responded, or opted out. This skill NEVER sends bulk DMs or acts as an authorized sender. Human must review and send through suitable business routes.

## Hard deliverable
Daily target >=12 verified distinct WA business contacts + >=2 verified distinct TG contacts, **each** with all mandatory assets. This is a target, not a promise. Fail closed: deliver the verified subset and a numerical shortfall when available data, tool access, or real findings do not justify full quota. Do not count past delivered clients as new.

## Stage 0 — reconcile before prospecting
1. Read actual accessible history coverage, including Drive central `RECONCILIATION_LEDGER` History/Reconciliation, pre-existing 103 list, all relevant 112 reservations, presented FB registry, sent/declined CRM, cases and permissions.
2. Normalize canonical domain and parent/brand aliases, international phone, Telegram handle, and official site redirects. Mark exact duplicate, possible duplicate/HOLD, or no match in **checked** sources.
3. Lock every company already presented to user. Refinement retains the original identifier; does not increment unique delivered count.
4. Historical status can contradict. A bulk-imported REPLIED value without the actual reply must be `REPLY_UNVERIFIED`, not fact.

## Stage 1 — multi-source business discovery
Source pool uses public company registries, relevant professional directories, company official sites, specialized communities, social updates with verified company relationships. Do not only search companies already marketed as SEO-ready. Prefer small B2B SaaS/AI, Web3 security, appropriate boutique services, tech-forward cross-border firms, hospitality operators with a *business* marketing contact. Regulated industries require separate compliance gates; avoid indiscriminate promotion.
For each candidate record: `entity_key,company,canonical_domain,industry,market,company_size_evidence,company_buyer,actual_purchase_trigger,public_route,route_source,active_signal,decision_maker_evidence,reviewed_at`.
Reject numbers not explicitly presented as WhatsApp. Telegram group/channel/bot is not direct recipient. Treat customer support/order/booking-only lines as ineligible for acquisition pitch.

## Stage 2 — live company research, not remembered pain points
Use industry Research Pack for *questions to ask*, not conclusions about the company. Inspect the company site's product/services, pricing/terms/integrations, locations/coverage, client proof, and contact pages. If possible cross-check independent professional sources and region-specific industry norms. Each company-specific claim must have an evidence ID:
`{id,type,source_url,captured_at,source_text,scope,verification,status,sha256}`.
Three allowed types:
- `onsite_observation`: scoped facts about the inspected live page; no claims about the whole site or model results.
- `search_sample`: real web search only, documented engine, query, time, locale and sample limits; NOT AI testing.
- `ai_answer_test`: actual platform/model query with original prompt/response, timestamp, model, fresh context, region/language, actual links/screenshot.
A/B classification:
- A verified mismatch in documented page facts.
- B scoped potential clarification/improvement with facts but not a demonstrated problem.
- AI outcome ONLY if true test evidence exists. Query constructed from real buyer triggers; discovery queries do not contain target brand. A single non-mention never proves invisibility or economic loss.
No observed issue? Mark NO_DEFECT and move on.

## Stage 3 — client-specific image pack
For each accepted client produce **genuine** mobile-legible PNG; never use an illustration or AI-rendered fake site/search screenshot as factual evidence. Capture original screenshot and text/html, log browser viewport/time, save SHA-256 and source URL. Annotate only outside or atop clearly framed portions without altering page text.
Image composition: 1 specific truthful headline; original snippet(s), one restrained highlight, OBSERVED, BUYER QUESTION, SUGGESTED FIX, scope limitation, source URL and capture date. Size 1080×1350 suggested. Deliver links to `raw_screenshot`, `html/text`, `final_png`, `source_manifest.json`.
For previous customers revalidate live facts and reuse original ID. Do not publish private customer materials without explicit rights.

## Stage 4 — route and message QA
Maintain separate booleans for `route_verified`, `evidence_verified`, `image_and_raw_ready`, `message_pass`, `history_cleared`. A score cannot override a hard fail. Business route must be appropriate; unknown recipient only allows a single recipient-check CTA, not a concurrent audit pitch. No outreach recommendation to order, helpdesk or bot contacts.
One image and one 25–45 English-word (or appropriate local-language) message:
- Transparent MultiHub identity.
- One **actually observed** company-specific fact with evidence ID.
- The genuine purchaser's decision question; one simple CTA.
- No meeting/price pitch, no AI/competitor ranking claim absent real test, no fake urgency, no impersonation.
Only `READY_FOR_USER_REVIEW` when all mandatory gates pass. Messages and images are a matched pair. Never mark SENT without user-confirmed send.

## Stage 5 — traceable daily batch
Daily queue: 12 WA and 2 TG TARGET; acquire candidates at >target headroom, use early-stage rejection cheaply, make PNG only after identity/route/history pass. If quota not reached do NOT fabricate. Append outcome `2026-10-26, channel, accepted, shortfall, reasons, source_coverage, image_completed, manually_sent, actual_replies` to `V3_DAILY_LOG`. Append or update per-company `V3_QA_QUEUE` with sources and statuses. Report verified numbers separately from quota.
For each ready client: [company, industry, buyer, business route click link, source, observation & scope, link to evidence PNG, first-message text, direct contact URL, follow-up status]. Hide or clearly label HOLD prospects.
Outreach is manually sent. Stop on decline. Report reply and payment funnel only from logged factual events.

## Known regression tests / baseline (2026-10-26)
- Legacy 112 candidate `WA-001 Peiko`: phone listed under Call us, WA not proven. Must HOLD_ROUTE.
- Legacy `WA-007 118 Technology Dubai`: ERP buyer question wrongly uses real-estate RERA scenario. Must HOLD_INDUSTRY until new onsite research.
- Legacy `WA-008 Fresa Technologies`: website lists actual WhatsApp and freight ERP; but industry presence is not a documented company defect, and no evidence PNG/AI test exists. Must HOLD_EVIDENCE rather than invent a gap.
- Existing 072/073/094/096/097 evidence PNGs from 2026-10-24 do not count as NEW leads. Recheck if used.

## Required gate checks
Use `python scripts/validate_daily_evidence.py daily_batch.json` where filesystem is available, or implement equivalent manual QA in connected Work; no ability to run code or connect a platform must be reported, never assumed.
