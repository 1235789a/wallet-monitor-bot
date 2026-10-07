# Message rules

Follow prospect-os-workflow1/system/outreach-message-policy.md; these details guide drafting and the semantic review.

## Evidence contract

Use only facts present in the prospect record. Every prospect-specific factual sentence must include a matching factual_claims item with claim_type, evidence_ids, source URL, checked timestamp, and evidence status. Do not turn inferred or unknown into observed. Sender identity is transparent and uses the literal [Your Name] placeholder.

## Modes

### PRELOCK_REVIEW

The opener earns permission for one real buyer-search check. It may state one verified company fact and connect it to a relevant purchase/search scenario. buyer_query_used is null and visibility_evidence_used is false. It must not mention a discovered competitor gap, claim that a search was checked, imply lost leads, or imply an existing GEO problem.

### EVIDENCE_PASS

Use only if prelock_status is PRELOCK_PASS, the buyer query is marked tested, and the record has sourced competitor/visibility evidence. State one precise observation that the evidence actually supports; offer to send the exact query or comparison. Never exaggerate or imply causation.

## Draft construction

1. Short greeting/transparent intro.
2. One specific verified business fact.
3. A plain-language bridge to the buyer's buying scenario.
4. One low-friction question. REVIEW asks permission to run one check; PASS asks whether to send the observed query/comparison.

Adapt for the reader:

- Track A: services and high-intent provider searches; avoid declaring SEO is bad.
- Track B: nearby purchase, delivery, product/category queries; plain everyday language.
- WhatsApp: direct and conversational.
- Telegram: concise and technically literate when appropriate; no forced slang.
- Brazil/Portugal: native Portuguese phrasing; Spanish markets: natural Spanish; international Web3/SaaS: English unless record evidence points elsewhere.

## Reviewer scorecard (0–100)

Score grounding (25), specificity (15), naturalness (15), compression (10), single CTA (10), low friction (10), low salesiness (5), plain language/no jargon (5), and claim safety (5). The score is advisory only: any hard violation fails regardless of score.

Hard fail: unsupported claim; unverified/fabricated competitor or query; REVIEW claims a gap; >1 CTA; missing sender placeholder; pretending to be a customer; pretending a search was tested; unusable contact route. Generic company-name-only personalization is a rewrite.

Default to one short question, 20–60 words (Portuguese/Spanish up to 65), no more than 2–3 short paragraphs. Avoid generic “I am analyzing/researching…” language, “organic discovery”, “visibility optimization opportunity”, GEO/SEO exposition, ungrounded praise, fear, meeting asks, PDFs, and price pitches.

Try at most two rewrites after the initial draft. If hard failures remain or score is below 80, return MESSAGE_REVIEW_REQUIRED; never label the draft ready.
