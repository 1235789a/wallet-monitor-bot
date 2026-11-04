# MultiHub per-prospect QA rubric

| Gate | PASS | HOLD |
|---|---|---|
| History / duplicates | All relevant ledgers queried with explicit scope, ID stable | existing presented, declined, duplicate, partial historical coverage |
| Company | Real company, official site, exact matching identity | directory-only speculative entity or name conflict |
| Sector / buyer | Real buying workflow and externally purchased value | everyone needs SEO/GEO, ungrounded urgency |
| Evidence | Exact source URLs and dated real observation retained | sources unspecified, site claims guessed |
| Graphic | Company-specific original screenshot+truthful overlay; full hash; phone-legible | illustration mistaken as original screenshot, mismatch, invented result |
| Message | One source-grounded observation; transparent MultiHub role; natural one CTA; image *actually attached* | asks to send already attached file; empty flattery; generic sales boilerplate |
| Route | Official verified correct WA/TG/FB business recipient, not support bot; human decision maker | phone != WhatsApp, Telegram channel != person, route owner unknown |
| Outreach | Human check/approval, channel policy, sent-state unchanged before actual send | automatic sending without authorization or claimed reply |
| Pairing | Exact original ID joins PNG URL, caption, source; actual Drive links read back | zip contains image but CRM row points to wrong company |

Priority: A verified inconsistency > B clear optional improvement > C no reliable point. Never mark a B observation as an established defect; never describe a theoretical buyer worry as demonstrated revenue loss.

### Message review
Score grounding 25, specificity 15, naturalness 15, compression 10, single CTA 10, low friction 10, non-salesy 5, plain language 5, claim safety 5; review score under 80 or any hard fail => hold/rewrite twice max. Prefer 25–45 words, absolute <=60.

### Current Taksh batch exception example
On 2026-10-27, 13 mobile PNGs and associated messages were created from public text: `TEXT_EVIDENCE_CARD`. Original screenshot archiving and marketing recipient confirmation are not complete. They are shareable *draft assets*, not `SEND_READY`. Maticz Technologies was excluded as an old historical match; preserve the exclusion.

## Final chat acceptance gate (2026-11-05)

- [ ] All scoped original IDs are present exactly once, in requested WA/FB/TG grouping.
- [ ] Every company has its own *visible inline* image; image identity and original-ID mapping are confirmed. A Drive file viewer, ZIP, PDF, local path or bare URL is not an inline image.
- [ ] Every company has an adjacent clickable channel-specific contact link; WA links must be WhatsApp chat URLs, TG a person/business, FB Page must not masquerade as personal Messenger.
- [ ] Every block has copyable company-specific copy, actual source URLs, evidence grade and HOLD/READY rationale.
- [ ] Real AI recommendation tests are distinguished from source-backed illustration; original screenshots are not inferred.
- [ ] No SEND_READY without separate outreach QA; no sending or reply fabrication.
- [ ] Mobile display and link opening are claimed verified only when actually tested. Otherwise explicitly report unverified.
- [ ] Archive-only delivery is an automatic CHAT_DELIVERY_UNVERIFIED, regardless of asset count.
