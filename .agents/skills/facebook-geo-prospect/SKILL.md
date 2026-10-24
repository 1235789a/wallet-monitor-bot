---
name: facebook-geo-prospect
description: Run MultiHub's evidence-first Facebook GEO prospecting. Use for Facebook获客、FB客户名单、跨渠道去重、Facebook老板/创始人搜索、Facebook话术、FB跟进或FB一键整客. Research and draft only: never send DMs automatically.
---

# MultiHub Facebook GEO Prospect — execution skill v1.0

## Mission and first principles
Optimize **verified net profit per unit of operator effort**, not message counts, group size, or speculative reply rates. Count direct prospects and partnership/referral prospects separately. Paid conversion and profit must be derived solely from logged events; unobserved rates are `UNKNOWN`.

## Priorities and constraints
1. FB is a distinct acquisition route, but shares an **entity-level history exclusion** with WhatsApp, Telegram, prior FB batches, and Case Engine. Do not count a company twice or fill WA/TG quotas with FB.
2. Read existing MultiHub Prospect OS history and conflict ledger before researching deeply. Prefer connected Drive (historical records and status) and GitHub SOPs. If inaccessible, accept verified exports and describe exactly what historical coverage is missing. **Never claim global dedupe from absence in one sheet.**
3. Validate the company's identity, independent source, official website, FB business Page/personal profile relationship, visible role of decision maker, and latest evidence date. A Facebook Page is not automatically a direct personal DM channel. Do not guess profile URLs or fabricate names.
4. Prefer real, current buying triggers and a justified reason for external GEO help. Being discoverable on Facebook or having an interesting company is insufficient.
5. Do not automatically message, add friends, scrape private group members, bypass login gates/rate limits, rotate identities, or simulate activity. No automated engagement or bulk sending. Respect declines and contact preferences. Only user-approved, manually sent outreach through suitable business contact routes.
6. Regulated industries are research-only by default and require their separate compliant gate; do not draft promotion or route them into general outreach.

## Default run on request such as '给我一批 FB 多行业客户'
### Stage 0 — Reconcile and exclude
- Read Drive `MultiHub GE v2.1｜RECONCILIATION_LEDGER`, `MultiHub Prospect OS` historical lists, prior FB candidates, and known sent/declined statuses. Original (read-only) SOP: https://docs.google.com/document/d/1U4RHCntmoNRyGXZgkYoAYXi1J5WqHymGShdeQJZgMQo/edit . Current GitHub outreach policy: `prospect-os-workflow1/system/outreach-message-policy.md`.
- If working from CSV exports, run `scripts/dedupe.py` against **all available** history files plus `assets/prior_fb_candidates.csv`. No-history-match means only checked sources yielded no match. Preserve ambiguity, aliases, parent/subsidiaries, alternate domains, same owner, and cross-channel contact history as review items.
- **Presented-contact lock (2026-10-24):** always check Google Drive Facebook registry `https://docs.google.com/spreadsheets/d/1dZxd1gsbcxQiea9sNrdmLDkbZDvInXtn9zaXH3-EKZg/edit`, tab `已出示客户去重锁`, as well as the central History ledger `https://docs.google.com/spreadsheets/d/1gMiJr8TODAvJxweoXb7Y6hoJPTvP7NVX0BUo-knnwmk/edit` (entity IDs `fb-presented-20261024:*`). An entity marked `FB_PRESENTED_NOT_CONTACTED` is **not new** and must not be re-delivered in a new lead batch, but must never be claimed as contacted, replied, or declined. If asked specifically for follow-up, retrieve the existing card rather than rediscovering it.
- Stop contact preparation for matched sent/declined entities. Old batch with uncertain status -> `PRIOR_BATCH_REVIEW`, not new.

### Stage 1 — Source-first diversified discovery
- Start with independent public business registries, trade directories, niche association lists, and business websites. Find businesses before searching founder profiles. Do not search only Facebook and then invent source provenance.
- Default batch: up to 12 researched candidates from >= 4 industries, at least 2 geographic markets if sources permit. User-specified quotas override this. If fewer are qualified, report the shortfall rather than pad.
- Prioritize B2B AI/SaaS, non-regulated boutique high-ticket services, professional services, independent hospitality/travel, specialist property management, B2B ecommerce tools, local energy installation. Route SEO/GEO agencies into `PARTNER` unless buyer need clearly established.

### Stage 2 — Cheap validation and buying logic
- Research each company's official site, ownership/decision-maker evidence, the real buyer job, customer value, and their sales/marketing signals. Reference a public source URL for every important claim. Reuse sources; batch lookups; avoid duplicated browsing.
- Score each 0–10: ICP/economic value (0–3), genuine buying-question relevance (0–2), confirmed decision-maker contact (0–2), external purchasing fit (0–2), dated recent business activity (0–1). Mark missing evidence `UNKNOWN`, do not fill by guess. A score is not a substitute for route and history gates.
- Evaluate in two queues: `DIRECT` (potential buyer) and `PARTNER` (referral). Evidence of actual purchase pain > apparent online popularity.

### Stage 3 — FB route gate and outreach QA
- Store business Page and actual person profile as separate fields; include clickable URL only if actually found/verified. `FB_PAGE_ONLY`, `ROLE_UNKNOWN`, `DM_AVAILABILITY_UNKNOWN`, `DUPLICATE_REVIEW`, `HISTORY_CONTACTED`, `DECLINED` must remain HOLD. No cold DM to random private profiles.
- For an allowed business recipient, generate one 25–45-word English/local-language draft: public specific business fact, MultiHub's transparent role, one meaningful buyer scenario, one easy question. If a general business inbox has unknown recipient, ask to identify marketing/owner **without simultaneously pitching an audit**.
- Reuse the existing initial-contact wording and semantic QA Skill `.codex/skills/geo-outreach-copy/SKILL.md` with `.codex/skills/geo-outreach-copy/references/message-rules.md` and `prospect-os-workflow1/system/outreach-message-policy.md` for evidence grounding, single CTA, and unsupported-claim checks. **That Skill originally targets WhatsApp/Telegram; do not transfer WA/TG route validation to Facebook**. Apply this Facebook Skill's independent recipient identity, business-Page-vs-personal-profile, permission and channel gates. A Facebook Page link alone is never a verified Messenger inbox.
- Never claim a real ChatGPT/Gemini test, lost customers, competitor outranking or higher ROI without dated test records. Only propose a *possible* sample test until authorized. Generate two internal candidates, select the most natural, grounded version; no robotic flattery, fear tactics, or multiple CTAs.
- All messages are drafts, never sent by the skill. Track `CONTACT_ROUTE_REVIEWED` and `USER_MARKED_SENT` separately.

### Stage 4 — Deliver one-click customer cards and data
- Output per lead: company + vertical + market; business economics; named decision maker and role/evidence; official company site; verified business Page and/or person profile (separate); score + reasons; duplicate coverage/result; FB route status; proposed outreach sentence (or explicit HOLD reason); next action.
- Present clickable FB URLs and independent, easily copied message text. Group qualified `READY_FOR_HUMAN_REVIEW` before HOLD. A clickable Page is not a confirmed DM route.
- Export when the environment permits `fb_batch.csv` and `fb_batch_summary.md` (schema in `references/output-schema.md`); preserve sources and checked date. Do not mutate existing main ledger without express instruction.

### Stage 5 — Human-operated conversion and feedback
- Update outcomes only from user-confirmed sent/reply/permission/quote/payment data. Stop upon refusal. Offer Evidence Bite only with real evidence and client permission.
- Report: verified distinct businesses, READY, HOLD, manual sent, substantive replies, tests permitted, quotes, paid USDT/expenses, per-lead research minutes, per-channel conversion; unknown values should stay unknown. Compare DIRECT and PARTNER by profit/hour once enough data is observed.

## Trigger phrases
- “用 Facebook 获客系统找 10 个多行业客户” -> Stage 0–4.
- “Facebook 一键整客” -> recheck all dedupe + produce clickable/copyable cards.
- “Facebook 回复了” -> classify actual reply and next response; do not fabricate sending status.
- “FB 复盘” -> only verified actual events and bottleneck recommendations.

## Files and compatibility
- `references/output-schema.md`: CSV field descriptions and status enum.
- `scripts/dedupe.py`: conservative CSV deduplication against selected history exports; this script does NOT access Google Drive, GitHub, or Facebook.
- `assets/prior_fb_candidates.csv`: prior candidates from conversation for additional exclusion, not a complete master history.
- Optional existing local CRM: `MultiHub_FB_Prospect_Engine_v1` with its own SQLite data; not a substitute for connected historical reads.
