---
name: prospect-token-budget
description: Minimize token, tool, and review usage for prospect-os-workflow1. Use for raw company-pool expansion, contact screening, sampling, enrichment, buyer-intent research, GEO audits, and outreach preparation when Work/Codex usage must stay low.
---

# Prospect Token Budget

Optimize for **tokens per completed batch**, not tokens per message. Preserve the existing history-exclusion and Sample Lock guarantees.

## 1. Identify the stage before using tools

Choose exactly one stage and do not silently expand scope:

- `RAW_DISCOVERY`: build the large company pool.
- `PRELOCK_SCREEN`: check contact routes before sampling.
- `LOCKED_RESEARCH`: research only companies already present in `sampled-lock.json`.
- `OUTPUT`: format results only; do not research again.

## 2. RAW_DISCOVERY is deliberately cheap

For raw-pool expansion:

- Prefer directory/list/API/dataset pages that yield many companies per read.
- Collect only: `company_name`, `domain`, `source_url`, `vertical`, `country` plus IDs required by the existing pipeline.
- Do not research founders, owners, WhatsApp, Telegram, email, buyer queries, competitors, visibility gaps, audits, or outreach.
- Do not open each company website merely to validate a raw candidate.
- Normalize and deduplicate locally after batch collection.
- Reuse already fetched source pages and cached files.
- Stop when the requested unique raw-pool target is reached.

## 3. PRELOCK_SCREEN uses bounded website reads

For each eligible company:

- Read the homepage once.
- Read at most one contact/about page when needed.
- Extract only explicit website-linked WhatsApp, Telegram, or email evidence.
- Never convert a phone number into WhatsApp without an explicit link.
- Reuse `prelock-screen.jsonl` or equivalent cache and do not refetch unchanged companies.
- Do not perform buyer-query, competitor, founder, or GEO research here.

## 4. LOCKED_RESEARCH never expands the cohort

- Load `sampled-lock.json` first.
- Research only locked IDs.
- Batch search queries when one request can cover multiple buyer queries or companies.
- Reuse evidence already collected in earlier stages.
- Do not rediscover replacement companies.
- If a locked company fails research, record the failure instead of starting a new discovery loop.

## 5. Tool-call discipline

- Do not spawn sub-agents or separate tasks unless the user explicitly asks or a hard dependency requires it.
- Prefer one batched tool call over many per-record calls.
- Never re-open an unchanged URL already captured in the current run.
- Extract the minimum evidence needed; do not pass full webpages back into later model steps.
- Keep evidence snippets short and attributable. Prefer a relevant excerpt over whole-page text.
- Avoid narration between tool calls; write checkpoints to files and give one final summary.
- If a tool loop starts retrying the same source or company, stop and mark it for review.

## 6. Compact model-facing context

Canonical data may remain JSON on disk for compatibility, but model-facing context should contain only fields needed for the current decision.

For uniform record batches, prefer in this order:

1. TSV/CSV-style rows with one shared header.
2. Minified JSON when nested structure is required.
3. TOON only when an installed encoder is already available and the structure is a good fit.

Never convert canonical lock/history artifacts to a lossy format.

Before sending records to an LLM, drop unused fields, repeated descriptions, HTML, duplicate evidence, and long boilerplate. Keep source URLs or stable evidence IDs so details can be reopened only when necessary.

## 7. Budget guards

Before starting a stage, estimate the expensive unit:

- RAW_DISCOVERY: source/list reads.
- PRELOCK_SCREEN: website page reads.
- LOCKED_RESEARCH: search batches + evidence opens.

If the plan would require repeated deep browsing across the whole raw pool, redesign it into a batch-discovery pass first.

When the user asks to conserve Work/Codex quota, prefer:
- fewer external site transitions,
- fewer tool calls,
- smaller returned payloads,
- cache reuse,
- deterministic local transforms,
- low/standard reasoning for collection and filtering,
- high reasoning only for the final locked research where it materially changes quality.

## 8. Required end-of-run usage note

Report compactly:
- stage executed,
- records processed,
- unique records produced,
- cache hits if known,
- external page/tool calls if known,
- whether any deep research was deferred,
- next cheapest stage.

Do not claim this skill can disable or bypass platform Auto Review. It only reduces the number and size of operations likely to trigger expensive model/tool work.
