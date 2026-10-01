# Buyer-Intent GEO Sprint operating policy

## Commercial outcome

The five-month target is RMB 100,000 in cumulative GEO revenue. Contact and scraping counts are
diagnostics. The outcome funnel is Qualified Prospect → Audit Sent/Viewed → Sales Conversation →
Offer → Paid → Delivered → Case Study → Recurring/Referral.

The formal cohort target is exactly 30 companies. A shortfall must be diagnosed at the failed funnel
stage, then used to direct the next source-first batch. A low-yield batch or PRELOCK_REVIEW never
ends the expansion run.

## Fixed formal 30-company mix

- Track A (15 of 30): small, founder-reachable Web3/blockchain/token/exchange/DeFi, AI/software or
  high-ticket B2B digital-service companies.
- Track B (15 of 30): lawful independent tobacco/vape, alcohol/bar or adult-retail businesses with
  one or two locations and an independent site. Count locations across the complete source pool by
  normalized domain/brand and reconcile that count to the official identity; one map point alone is
  not proof. Three or more locations is a hard failure.
- Vertical targets: Web3 8, AI/software B2B 7, vape 5, alcohol/wine 5, adult retail 5.
- Formal chat mix: exactly 24 verified WhatsApp and 6 verified direct Telegram accounts. One track
  or vertical never fills another's shortfall. Chains, franchises and do-not-contact records are
  excluded. Never lower evidence requirements to fill any quota.

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
4. Before Sample Lock, a light preflight uses one or two representative buyer queries to establish
   a plausible purchase scenario and competitor/substitute.
5. After Sample Lock, complete five to ten manually reviewed queries and at least five tested query
   samples with platform/date/scope, returned URLs, prospect presence and named competitors.
6. Three source-backed, page-specific gaps and one bounded first fix.
7. An official public email, direct WhatsApp/TG business route or verified founder social profile.
8. A specific, permission-based opener. Generate and review it with
   [outreach-message-policy.md](outreach-message-policy.md) and the
   [geo-outreach-copy Skill](../.codex/skills/geo-outreach-copy/SKILL.md). No outreach is sent automatically.

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

- Build a 42-company `PRELOCK_PASS` reserve pool before formal selection. It is only a reserve;
  it does not alter the final 30 or weaken an ICP gate.
- Process batches of 50–100 RAW, recompute required Track/vertical/channel slots each time, and
  prefer sources with higher recent `PRELOCK_PASS` and direct-chat yield. Reuse website/contact
  caches; never re-fetch completed records without an explicit refresh reason.
- Route every `PRELOCK_REVIEW` into a priority queue. Repair only missing evidence, at most three
  attempts. Park unresolved records and continue the next candidate/source.
- Stop a single source after 30–50 fresh records with no valid direct chat, website resolution below
  15% after 50, zero `PRELOCK_PASS` after 50, or a majority of stale/closed/chain/non-ICP records.
  Record the reason and switch to another permitted off-search source.
- `SAMPLE_READY` requires a feasible exact 30-company selection from `PRELOCK_PASS` only, with
  Track A/B 15/15, all vertical quotas, exactly 24 WhatsApp and 6 direct Telegram, and existing
  history/city/source constraints. Only then may the existing Sample Lock be created.
- `SOURCE_EXHAUSTED` requires at least 1,000 fresh RAW across eight sources and three consecutive
  batches of at least 100 with at most one new `PRELOCK_PASS` each. Otherwise save `PROGRESS`
  and resume. `EXECUTION_BLOCKED` is reserved for an actual technical or permission failure.
