---
name: geo-outreach-copy
description: Generate and review short evidence-grounded first-contact WhatsApp and Telegram messages for GEO / buyer-search visibility prospects.
---

# geo-outreach-copy

Use for first-contact WhatsApp/Telegram drafts only. Prospect OS stays at research → draft → human review; never send messages.

1. Read prospect-os-workflow1/system/outreach-message-policy.md and references/message-rules.md in this Skill.
2. Read only the supplied prospect record and cited evidence. Do not perform new research or add facts.
3. Determine channel, market language, Track A/B, and PRELOCK state. Apply the stricter PRELOCK_REVIEW gate whenever buyer-query and visibility proof are incomplete.
4. Draft two internal candidates: observation-first and buyer-query-first. Keep the exact tested query in metadata only when evidence supports it.
5. Review both against grounding, specificity, naturalness, compression, one CTA, friction, salesiness, jargon, and claim safety. Rewrite at most twice.
6. Output one recommended message, both candidates for debugging, and message_quality. If hard checks remain or the final score is below 80, output MESSAGE_REVIEW_REQUIRED.

Do not conflate message_quality with buyer_priority_score. Never send.
