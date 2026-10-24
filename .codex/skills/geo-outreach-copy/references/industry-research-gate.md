# INDUSTRY_RESEARCH_GATE v1.0 — understand how this market buys before writing

This is an evidence contract, not a fill-in-the-blank pitch generator. Research may be expensive; cache industry-level findings with a `checked_at` date, then verify each company's own facts separately. No research data => NO message.

## Required industry dossier
1. **Actual decision:** market/country/language; economic buyer, technical evaluator and end customer; whether they differ.
2. **Job to be done:** what immediately triggers them to shop; situation when urgency matters; whether purchase is recurring or one-off.
3. **Shortlisting:** list 3 explicit screening criteria with cited evidence, e.g. exact integrations, fee basis, security review scope, booking semantics; distinguish must-have from differentiator.
4. **Risk and friction:** onboarding/migration time, pricing exposure, failed payment/lost booking risk, trust proof, comparison substitutes, human handoff and procurement objections.
5. **Money bridge:** whose cost or potential revenue is affected? what can be estimated from public sources versus UNKNOWN? Do not invent conversion losses or ROI percentages.
6. **Supplier's operating constraint:** is this team small? already has a search agency or full documentation? can MultiHub plausibly implement a bounded fix? If not => partner/park.
7. **Search intent only after above:** capture 3 buyer questions: problem-aware, option comparison, pre-purchase verification. Write in the buyer's words, not invented GEO terms.
8. **Grounding:** two official prospect URLs + one neutral/primary industry source + one relevant competitor/substitute, access timestamp, exact content excerpt. Capture latest publication separately from observation date. Inspect counterevidence and conflicting price tiers.
9. **Confidence:** `INDUSTRY_RESEARCH_PASS` only if buyer, qualifying criteria, supplier-specific finding, counterevidence, fix, and enough evidence exist. Missing crucial detail => `INDUSTRY_RESEARCH_PENDING`.

## Examples of buyer mechanisms (hypotheses to test, NOT claims about a named prospect)

| Vertical | Trigger / what buyer compares | Valid initial diagnostic | What NOT to assert |
|---|---|---|---|
| WhatsApp CRM / AI agent SaaS | Business needs more qualified conversations without high staff cost; checks 24h support window, official API access, template categories, total cost including BSP/Meta, shared inbox, live handoff and integrations | Compare exact same plan and locality, published add-on fees, human-handoff workflow, service window and booking demo | 'Higher pricing is a mistake' or 'your WhatsApp API fees are wrong' without same-plan comparison |
| Booking / clinic appointment SaaS | Practice/merchant needs fewer no-shows and correctly reserved slots; checks calendar sync, real-time capacity, double-booking, rescheduling, staff handoff and data handling | Does 'appointment booking' actually lock a calendar slot vs only capture a preferred time? Verify product demo or docs | Claims of patient privacy certification, automatic booking, or lost clinics without proof |
| Smart-contract / DeFi security audits | Protocol team faces launch deadline, code/upgrade and economic design exposure; compares chain expertise, scope, auditor credibility, publication, re-test policy and economic modeling | Match actual audited stack, reports, oracle/logic/upgrade risk scope and post-audit remediation terms | 'Code audit eliminates economic risk', invented bugs, 'your competitor outranks you' |
| Crypto merchant payments | Merchant needs settleable transactions with manageable fees and operational risks; checks supported chains/tokens, net received, which side pays network fees, confirmations, refund/chargeback differences, API integration and support | Make a documented example distinguishing processor fee, network fee, exchange/spread, payout schedule and refund limitations | Present stablecoins as universally reversible/irreversible, zero-cost, anonymous or compliant everywhere |
| Ecommerce recovery | Store operator needs net contribution from recovered orders; checks attribution window, recovered margin, platform fee, shipping/return cost and whether contacts opted in | Show illustrative break-even math with stated assumptions, clarify attribution and messaging permissions | 'Recovery percentage equals incremental sales' without holdout experiment |

Industry references to validate on use (examples, not permanent truth):
- Meta/WhatsApp pricing mechanics: https://www.twilio.com/en-us/whatsapp/pricing and https://faq.whatsapp.com/1022626499062292/ ; check current jurisdiction, partner and latest pricing conditions.
- OWASP Smart Contract Top 10: https://scs.owasp.org/sctop10/ ; risk taxonomy does not prove a target has a vulnerability.
- Baymard abandonment research: https://baymard.com/lists/cart-abandonment-rate ; population stats do not prove a specific shop's conversion loss.
- OWASP API Security: https://owasp.org/www-project-api-security/ ; standards create buyer evaluation criteria, not a breach diagnosis.

## Company-specific 6-question falsification protocol
Q1. Can we identify a buyer and a purchase event *more specific than 'needs more leads'*?
Q2. What exact question can stop that buyer from shortlisting or purchasing this solution?
Q3. Where on the **official** site is the answer, and is it up to date?
Q4. Do at least 2 suitable competitors explain this better? If not, why is the difference significant?
Q5. Is this truly missing/wrong, or explained by different tiers, dates, currency, regions or access level?
Q6. Would one bounded change realistically help the buyer decide? Or is a bigger technical/compliance/operational issue outside MultiHub's scope?

## Insight grading (NOT purchase probability)
- **A — PROVEN OBSERVATION:** exact prospect page and relevant comparison, contradictory interpretation tested, likely buyer criterion supported. Still no causal loss or AI ranking claim.
- **B — PLAUSIBLE WITH EVIDENCE:** sourced public fact and relevant buyer worry, but direct buying impact not shown. Use conditional wording.
- **C — SPECULATIVE:** generic industry trend or feature overview, no business-specific buying hurdle. Reject for case-led outreach.

A hook needs grade A or grounded B, verified relevant recipient, and feasible fix. C may justify further research, not a personalized case.
