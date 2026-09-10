# Off-search discovery policy

This policy is a hard gate for Prospect OS Workflow 1. It prevents search-ranking bias from becoming the company-discovery method.

## Required sequence

`Discover a company off-search -> verify the business and small decision chain -> inspect the independent website -> verify activity and decision-maker contactability -> test buyer queries -> score`

Google, Bing, SEO result pages, and AI-search answers may be used only after a company is already in the raw pool. They are diagnostic evidence, never the primary discovery source.

## Accepted first-discovery sources

Use a public source that does not depend on the company ranking for its own industry terms:

- partner or ecosystem directories
- industry and vertical directories
- marketplaces and launch platforms
- YC/startup databases
- associations, trade-show exhibitor lists, and local business databases
- public social profiles, communities, forums, and GitHub ecosystem lists
- official company registries, chamber directories, and official/local business directories

Record the exact source URL and the channel in every candidate.

## Hard gate before Workflow 1

A candidate is formally eligible only when all of these are true:

1. `discovery_channel` is not `google`, `bing`, `search_engine`, `seo_results`, or `ai_search`.
2. `discovery_source_url` is public and on a different domain from `website_url`.
3. The independent website is live, owned by the company, and describes a real product or service.
4. Recent activity, a decision-maker route, business quality, and the search-distribution gap are separately evidenced.
5. Every key claim has a source URL and an evidence label: `observed`, `self_reported`, `inferred`, or `unknown`.
6. Local-business Track B requires `ownership_model` to be `owner_operated` or
   `independent_small_business`, `chain_status=no`, and an observed 1–2 locations. High-ticket B2B
   Track A instead requires a source-backed small-team/founder-led decision chain; office count is
   not treated as store count.

Website-only discovery is not silently promoted. Keep it in a re-verification queue as P2 until an independent source is added.

## Provenance fields

Each raw record must contain:

- `discovery_channel`
- `discovery_source_url`
- `discovery_source_note`
- `website_url`
- `business_quality`
- `distribution_gap`
- one `discovery` evidence item linking the independent source
- `ownership_model`, `location_count`, `chain_status`
- `ownership_location_evidence_url`, `ownership_location_evidence_note`
- one `ownership_locations` evidence item matching the ownership/location source URL

A missing or same-domain discovery source is a validation failure, not a reason to fill the batch with another weak record.

A local-business chain, franchise, branded branch, business with three or more stores, or a local
record whose independent ownership/store count is unknown is a hard rejection. A directory's
“small business” label alone is not ownership proof. For B2B agencies, an independently verified
small team and direct founder/decision-maker route satisfy the size gate.

## Quality guardrails

Do not infer activity, replies, decision-maker status, team size, clients, awards, capabilities,
USDT readiness, or search visibility from a directory listing alone. Public reply behaviour is a
useful activity signal but is not a P0 hard gate: only an actual reply to our outreach can become a
`REPLIED` funnel event. Lawful age-restricted retail may be researched for B2B outreach, but illegal
or unlicensed activity is excluded. No automatic outreach occurs during discovery.
