# MultiHub conversation copy — Humanizer v4.0

Mandatory for new and previously prepared case captions, WA/TG/FB and X first
touches, public comments, replies, followups and quote conversations. This
extends existing evidence, route, deduplication and no-send gates; it does
not replace them.

Read the complete vendored `.codex/skills/humanizer/SKILL.md` before drafting.
Upstream: https://github.com/blader/humanizer, v4.0 pinned at
a48c60c2a3f7a0f6ecc8f9b8d2b1ef71c7927155 (MIT license included).

## How to write

- Start from the customer's actual post, service, or last message. One concrete
  reason to care, in their vocabulary. No fake friendliness, generic praise,
  report introductions, GEO jargon, or repeating the same pitch to everyone.
- First touch: identify MultiHub honestly; one easy next step. Unknown recipient:
  ask who owns new-customer enquiries, without pitching a search check.
- Permission received (e.g. "Please share"): deliver the promised case or
  verified piece of evidence. Do not greet from scratch, repeat the pitch, or
  ask to send it again. If the image or live test is not ready, say that plainly.
- Sample delivered: explain one relevant verified finding, connect it to an
  actual buyer decision, then stop or ask one specific question if useful.
- No reply: only follow up if there is new relevant information. Respect opt-outs.
- X comments: reply to the actual post; no generic compliments or DM bait.
- Quote requested: use the approved product, pricing and scope; no invented
  terms, outcomes or urgency. Do not jump to price before the customer is ready.

## Quality gates

Use Humanizer's read/rewrite pass, then check sources and actual stage again.
Use the runtime `outreach_humanizer.py` functions to lint drafts and stage-specific
claims. A clear lint is not a semantic Humanizer pass. Human review is still
required before sending. Rework at most twice before holding a draft for review.
Zero questions is often right in a warm reply; first touch keeps one CTA.
Do not call onsite facts a live AI test, invent rankings or imply a screenshot
was sent. Never expose private chats or case records in public output.
Return only the best prospect-facing draft, with a separate idiomatic Chinese
translation for the operator (never append it to the outbound text).
No auto-sending, posting, or changes to the current acquisition quota.
