# Buyer-Intent GEO Sprint operating policy

## Commercial outcome

The five-month target is RMB 100,000 in cumulative GEO revenue. Contact and scraping counts are
diagnostics. The outcome funnel is Qualified Prospect → Audit Sent/Viewed → Sales Conversation →
Offer → Paid → Delivered → Case Study → Recurring/Referral.

The formal prospect cohort is exactly 30 companies. A shortfall must be diagnosed at the failed
funnel stage and then used to direct the next expansion batch; it must not end after one low-yield
batch or one PRELOCK_REVIEW. Expansion must stay inside the evidence and ICP gates below.

## Fixed formal 30-company mix

- Track A (15 of 30): small, founder-reachable Web3/blockchain/token/exchange/DeFi, AI/software or
  high-ticket B2B digital-service companies.
- Track B (15 of 30): lawful independent tobacco/vape, alcohol/bar or adult-retail businesses with
  one or two locations and an independent site. Count locations across the complete source pool by
  normalized domain/brand and reconcile that count to the official identity; one map point alone is
  not proof. Three or more locations is a hard failure.
- Vertical targets: Web3 8, AI/software B2B 7, vape 5, alcohol/wine 5, adult retail 5. The
  official contact mix is exactly 24 verified WhatsApp and 6 verified direct Telegram routes.
- One track or vertical never fills another's shortfall. Chains, franchises and do-not-contact
  records are excluded. Never lower evidence requirements to fill a quota.

Discovery is company-first from structured directories, registries, maps or datasets. Search is
permitted only after discovery to resolve and verify that named company, its contacts, buyer-query
visibility and competitors. Every raw-pool report must state the source's coverage and placement
bias; source-first discovery reduces but does not eliminate survivor bias.

## P0 evidence gate

Each P0 must have:

1. Independent discovery provenance and an official website.
2. Evidence of a real small business/non-chain identity.
3. Buying-pain evidence such as current service/content investment, public acquisition activity or
   another dated commercial growth signal.
4. Before Sample Lock, only a light preflight: one or two representative, service-relevant,
   non-brand buyer queries that establish a plausible purchase scenario and competitor/substitute.
5. After Sample Lock, complete five to ten manually reviewed queries and at least five tested
   query result samples with platform/date/scope, returned URLs, prospect presence and named
   competitors.
6. Three source-backed, page-specific gaps and one bounded first fix.
7. An official public email, direct WhatsApp/TG business route or verified founder social profile.
8. A specific, permission-based opener. No outreach is sent automatically.

Weights: acquisition investment 25, buyer value 15, tested visibility gap 25, decision access 15,
delivery fit 10, recent activity 8 and USDT 2. USDT is a bonus only. A score is a review priority,
not a reply or purchase probability.

## Evidence boundaries

- Missing schema alone is not an AI/search visibility gap.
- A published phone number is not a verified WhatsApp account.
- Delivered, read and no-response events are not replies.
- Public activity is not response willingness; actual replies are recorded only from owned message
  exports/integrations.
- Paid requires an attributed unique invoice/payment record with amount and currency.
- Only a directly tested platform may be named. Ordinary web search and directories are evidence
  sources, not AI recommendations.

## Offer and tracking

The free mini audit creates demand. The initial offer is a bounded USD 149 founder-price AI
Visibility Sprint: technical/crawler checks, entity consistency, structured data, priority service
pages, buyer-question answer blocks, internal linking, baseline query/competitor tracking and an
authority/citation plan. It promises implementation and fixed-query before/after testing, never a
guaranteed AI ranking. After 3–5 real case studies, target USD 299–399+ and USD 99–199/month
monitoring.

Persist the required funnel stages and controlled lost reasons. `AUDIT_SENT`, `AUDIT_VIEWED`,
`SALES_CONVERSATION` and `REFERRAL` are separate touchpoints. Report observed cohort conversion
rates; leave individual reply/audit/purchase probabilities null until enough labelled outcomes
exist for honest calibration.

## Continuous prelock expansion

- Maintain a persistent reserve target of 42 `PRELOCK_PASS` companies before selecting the formal
  30. The reserve is not a partial Sample Lock and does not weaken any qualification gate.
- Process new RAW in batches of 50–100. After each batch, write `required_slots.json`,
  `source-yield.json` and `expansion-state.json`; target the actual missing Track, vertical and
  chat channel.
- A `PRELOCK_REVIEW` enters a prioritized repair queue. Retry only its missing evidence, at most
  three times. Then mark it `PRELOCK_PARKED` and continue with the next candidate/source. REVIEW,
  REJECT, a website failure, or one weak batch is never a task-completion condition.
- Pause an individual source when 30–50 fresh rows produce no valid direct chat route, website
  resolution remains below 15% after 50 rows, no PRELOCK_PASS appears after 50 rows, or at least
  half its screened rows are stale, closed, chain or non-ICP. Preserve the stop reason and switch
  to another legal off-search source.
- Use `SAMPLE_READY` only when the existing sampler can select exactly 30 PRELOCK_PASS records
  meeting the 15/15 Track split, all vertical targets, exactly 24 WhatsApp and 6 direct Telegram,
  history exclusion, city cap and source constraints.
- Use `SOURCE_EXHAUSTED` only after at least 1,000 fresh RAW rows across at least eight sources
  and three consecutive batches of at least 100 rows each yield at most one new PRELOCK_PASS.
  Otherwise retain a resumable `PROGRESS` checkpoint. `EXECUTION_BLOCKED` is reserved for a
  genuine technical or permission failure.
