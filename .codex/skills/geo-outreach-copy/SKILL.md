---
name: geo-outreach-copy
description: Research industry buying pain, verify a prospect-specific business finding, prepare an evidence-led mini-case, and draft/review first-contact WhatsApp or Telegram outreach for MultiHub. Research and drafts only; never send.
---

# MultiHub geo-outreach-copy v2.0 | industry-first first contact

## Mission
Optimize **qualified sales conversations and paid, deliverable work per human research hour**, not reply-bait, message volume, writing scores, or screenshots. A company's feature is not a pain point; a missing feature is not evidence of lost sales; an observed page issue is not proof of an AI-search ranking problem.

**Mandatory reading, in order**
1. `prospect-os-workflow1/system/outreach-message-policy.md` (contact gates and drafting policy)
2. `references/industry-research-gate.md` (before personalization)
3. `references/case-evidence-rules.md` (before calling anything a case or requesting visuals)
4. `references/message-rules.md` (final draft reviewer)
5. `references/regression-fixtures.md` (hard-fail examples)

## Two-stage architecture (do not collapse)
**A. Research preparer** may research *after* the prospect identity and history check, and saves a source-backed INDUSTRY_DOSSIER + CLIENT_CONTEXT + HOOK_CANDIDATES. Research both the buyer and the company; check disconfirming evidence. Do not fill missing data from intuition. Reuse dated industry facts across companies but independently verify company-specific claims.

**B. Message writer** reads only those prepared records and evidence IDs. Do **not** browse for new claims during message composition. If A is incomplete, return `INDUSTRY_RESEARCH_PENDING` instead of inventing an opener. This preserves the old evidence-contract restriction while fixing upstream input quality.

## Required execution order
0. **History + compliance + route.** Cross-check company/parent/brand/domain/WA/TG against accessible Drive Prospect OS, reconciliation ledger, Case Engine and contact status. Contacted, opted out or declined => `HISTORY_EXCLUDED`; ambiguous duplication => `DUPLICATE_REVIEW`. Respect channel/personal privacy and regional outreach law. Regulated/age-restricted categories remain `REGULATED_RESEARCH` / `HOLD_REGULATED` unless a separate approved process explicitly permits outreach; no promotional drafts by default. A valid link is not proof a human or decision-maker reads it.
1. **Industry buying mechanism.** Name the actual paying buyer and end user separately; trigger for purchase; top 3 decision criteria; implementation and switching constraints; alternative/competitor; procurement objections; what money/time/risk is at stake; why this specific prospect might pay MultiHub rather than fix it internally. Evidence statuses `FACT / WEB_OBSERVED / CUSTOMER_ASSERTED / AI_OBSERVED / HYPOTHESIS / UNKNOWN`. A generic vertical label does not pass.
2. **Source triangulation.** Minimum 1 primary or credible industry source; 1 relevant competitor/substitute or neutral comparison; 2 prospect-specific official pages. Seek at least one counterexample. For each claim: `claim_id, source_url, observed_at, published_at(if known), exact evidence excerpt/section, claim_type, confidence, contrary_evidence`. If unavailable, mark `UNKNOWN` and narrow the claim; do not turn a stale date into recent activity.
3. **Buying-journey diagnosis.** Map `buyer_query -> qualifying question -> source-backed prospect answer -> competitor/substitute answer -> information gap -> business consequence (hypothesis) -> smallest practical fix -> what would disprove it`. Distinguish **discovery gap**, **selection/understanding gap**, and **conversion/checkout gap**; do not label all three GEO. Compare equivalent plans, units, regions, taxes and dates before saying prices conflict. Do not claim lack of a page until navigation/site search confirms it.
4. **Choose ONE insight.** Require three tests: (a) is it actually important to a buyer choosing this provider? (b) is the finding verified and nontrivial? (c) is the proposed fix inside MultiHub's demonstrable scope, without promises of rankings or revenue? Reject weaker hooks. No meaningful hook => `NO_DEFENSIBLE_HOOK`. Never substitute a generic 'AI visibility' sentence.
5. **Proof stage.** `WEBSITE_PRE_DIAGNOSIS` can use dated site screenshots and comparison notes; `AI_QUERY_OBSERVED` requires actual query text, platform, date, answer, citations and limitations; `IMPLEMENTED_RESULT` requires authorized implementation + comparable follow-up measurements. A real one-page mini-case is an evidence artifact, not a stylized slide. Visual pack is **required when user asks for an image-led case**, not a pretext to fabricate or invent screenshots. Follow `case-evidence-rules.md`.
6. **Recipient gate and message mode.** Unverified/business inbox with unknown recipient => **recipient_check only**, no audit pitch or image. Service-only/bot/order-only => `CONTACT_HOLD`, no proposed outreach. Verified relevant human/business decision route + valid website observation => **case-led, observation-first** opener with one concrete purchasing implication and one easy question; clearly distinguish hypothesis from test. `EVIDENCE_PASS` only with PRELOCK_PASS and real scoped AI evidence, never a guessed ranking.
7. **Human first-contact copy.** Draft two alternatives (buyer-dilemma-first, observed-evidence-first). Use natural local language, normally 25–45 English words (60 hard cap), no name placeholder unless requested, 1 low-friction CTA. State identity/service without pretending to be a buyer. When an evidence image is legitimately attached, refer to exactly what is circled, not to a manufactured 'case study'. No brochure, overclaim, generic praise, repeated 'I help companies get found', long list of capabilities, or two CTAs.
8. **Independent QA.** Review with `message-rules.md`: facts/evidence IDs, industry accuracy, material buyer problem, counterexample, relevance of fix, rights/visual provenance, route, honest scope, wording. Any hard fail => `MESSAGE_REVIEW_REQUIRED`; status cannot be promoted by a good numeric writing score. At most 2 rewrites.
9. **Manual-ready handoff.** One compact card per *new eligible* prospect: company/vertical, verified recipient and clickable actual direct-chat URL, one-sentence buyer economics, selected observation and source URLs, alternate explanations, evidence status, one small proposed fix, linked screenshot(s) if captured, final copy in a copyable field, `READY_FOR_HUMAN_REVIEW / HOLD`, next action. Keep company priority score, insight confidence, message quality and **actual funnel outcomes** separate. Never mark sent, replied, paid, ranked or ready without evidence. Never send.

## Output contract (minimal structured example)
```yaml
entity_id: ...
dedupe_status: HISTORY_CLEAR | HISTORY_EXCLUDED | DUPLICATE_REVIEW | UNKNOWN
route_status: VERIFIED_BUSINESS_DECISION_ROUTE | RECIPIENT_CHECK_ONLY | CONTACT_HOLD
industry_dossier: {buyer: ..., purchase_trigger: ..., decision_criteria: [], objections: [], sources: []}
buyer_situation: {question: ..., existing_alternatives: [], prospect_evidence: []}
insight: {kind: DISCOVERY|SELECTION|CONVERSION, statement: ..., counterevidence: ..., why_money_at_stake: "HYPOTHESIS: ...", smallest_fix: ..., evidence_ids: []}
proof: {level: WEBSITE_PRE_DIAGNOSIS|AI_QUERY_OBSERVED|IMPLEMENTED_RESULT|NONE, links: [], image_provenance: []}
outreach: {mode: RECIPIENT_CHECK|CASE_LED_PRELOCK|EVIDENCE_PASS|HOLD, recommended_first_message: ..., channel: ..., url: ..., message_quality: ..., reason: ...}
next_action: ...
```

## Non-negotiable acceptance tests
- If swapping the company name makes the message equally valid => FAIL.
- If the industry buyer cannot be described without buzzwords => research again.
- If 'AI didn't recommend you' lacks actual test provenance => FAIL.
- If a 'different price' could be explained by different plans/conditions => do not call it an error.
- If the case has no verifiable evidence or its graphic is simulated => never call it a verified case.
- If recipient is not the relevant business contact => recipient_check/HOLD, not a disguised sales pitch.
- If the client already has robust answer content => identify the actual missing *buyer decision* or say `NO_DEFENSIBLE_HOOK`.
