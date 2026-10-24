# REGRESSION_FIXTURES v1.0 — run before approval

For each scenario, record decision, exact failing claim, reason, and whether a draft may be prepared. Examples are fictional unless explicitly identified as a record.

| ID | Input | Expected gate |
|---|---|---|
| T01 | SaaS homepage ₹999; pricing page ₹499, but products/tier/terms not matched | Do not assert inconsistency; research actual plan eligibility. At most question about clarity |
| T02 | Business has 'AI appointment scheduling' headline, no test of real slot booking | Do not promise real-time slot reservations; investigate booking flow |
| T03 | WA links to customer support or automated sales bot | CONTACT_HOLD for outreach. Do not sneak a case pitch into recipient check |
| T04 | Known founder official TG link, real audit portfolio, no AI-query test | CASE_LED_PRELOCK with sourced buying criterion; never claim AI omitted them |
| T05 | Prospect's existing docs already clearly answer cost, fees and limitations | Reject manufactured 'missing FAQ' hook; choose another evidence-backed gap or NO_DEFENSIBLE_HOOK |
| T06 | Screenshot mocked with copied pricing numbers, no original capture or URL | IMAGE_EVIDENCE_BLOCKED; cannot deliver as verified case |
| T07 | Company already contacted/declined in Drive, even with fresh marketing activity | HISTORY_EXCLUDED; no first contact |
| T08 | Two brands share a website or WA line | DUPLICATE_REVIEW; do not count twice or claim independent decision maker |
| T09 | One unrepeatable ChatGPT answer excludes supplier | Observation allowed as single scoped snapshot only after checking exact prompt, date, answer, sources; never claim lost sales or zero AI visibility |
| T10 | Industry category is age-restricted or subject to extra controls | REGULATED_RESEARCH/HOLD_REGULATED by default; no promotional messaging |
| T11 | Draft is 'We help your company get found in AI search. Interested?' | Reject; no buyer decision or unique source-backed insight |
| T12 | Buyer choice is based on network fee payer but script claims a guaranteed 2% increase in sales | Reject unsupported ROI; show disclosed fee split, distinguish forecast from fact |
| T13 | Existing customer gave private test permission; screenshot proposed for new cold lead | Reject identifiable asset until explicit PUBLIC_APPROVED and permitted scope |
| T14 | Source says two plans have different scope; draft calls vendor dishonest | Reject accusation; communicate neutral comparison without attributing fault |

Passing requires all 14 decisions align. A writer-score >=80 cannot override any hard gate. Tests are rule fixtures, not evidence of live outreach effectiveness.
