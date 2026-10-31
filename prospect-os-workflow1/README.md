# Prospect OS Workflow 1 — Buyer-Intent Sprint

The default runner now prioritizes paid-prospect evidence rather than contact volume. It preserves
the existing company-first discovery, verification and deduplication foundation while adding a
strict buyer-intent mode. The current operating rules are in
[system/buyer-intent-sprint.md](system/buyer-intent-sprint.md).

The formal sample is exactly **30 companies: Track A 15 + Track B 15**, with
**24 WhatsApp + 6 direct Telegram human-reachable routes**. Vertical targets are
Web3 8, AI/software B2B 7, vape 5, alcohol/wine 5 and adult retail 5. Build at least
42 distinct eligible reserve companies first. Email and founder social evidence
remain useful for research, but do not fill the formal chat quotas.

Buyer-intent mode requires 5–10 human-reviewed non-brand buyer queries and at least five actually
tested query comparisons before P0. Every comparison records the platform, date, returned URLs,
prospect presence and competitors. Search results and third-party directories are never labelled
as ChatGPT, Gemini or Perplexity recommendations.

```bash
python workflow1_daily.py runs/reviewed-prospects.json --date 2026-09-10 \
  --mode buyer-intent --db data/prospects.db --output-dir outputs/buyer-intent --dry-run
python -m unittest discover -v
```

Dry-run uses an in-memory database and does not mutate the supplied database. Remove `--dry-run`
only after human review of evidence and contact routes.

This folder is the portable Prospect OS workflow. Buyer-intent mode supports the fixed B2B/local
split; the older Web3-only path remains available as legacy compatibility code. It is intentionally
isolated from the host application's existing files.

The lawful tobacco/alcohol prospect track is a separate, evidence-first
module. It does not change the Web3-only daily runner and does not send
outreach. See [system/tobacco-alcohol-track.md](system/tobacco-alcohol-track.md).

## Operating sequence

`Discover a company off-search → verify owner-operated + 1–2 locations + no chain/franchise → verify the independent website → inspect search distribution → score the prospect`

Google, Bing, SEO result pages, and AI search are diagnostic sources only. Every new candidate must include:

- `discovery_channel`
- `discovery_source_url`
- `discovery_source_note`
- `business_quality`
- `distribution_gap`
- one matching `discovery` evidence entry
- ownership model, exact location count, chain status, and a matching `ownership_locations` evidence entry

Search-only discovery channels are rejected, and the discovery source must be public and on a different domain from the company website. The full hard gate and quarantine behavior are documented in [system/off-search-discovery-policy.md](system/off-search-discovery-policy.md).

## Legacy v4 P0 rules

The rules below document `--mode legacy`; they are retained for compatibility and are no longer
the default buyer-intent qualification path.

- Web3 only; handmade and regulated/high-risk categories stay excluded.
- Owner-operated or independent small businesses only. Chains, franchises, branded branches, unknown ownership, and businesses with 3+ locations are rejected in code.
- No quota filling. A request for 30 means research up to 30 valid records; invalid or unverified records are not replaced with fillers.
- Legacy Telegram behavior remains capped at 3 retained records per run.
- P0 requires activity within 3 days, a team upper bound of 40, business quality `strong`, a `strong` or `moderate` distribution gap, observed public reply behavior, and a confirmed decision-maker contact.
- Ranking priority is reply probability → decision-maker access → real business quality → partnership openness → GEO/search gap.
- `Not found` Reply Behaviour is capped at 12/30 and `Inaccessible` is inferred only; neither can enter P0.
- No automatic outreach, publishing, or database mutation from the research step.

## Lawful tobacco/alcohol track

Run the independent track against records that were discovered from a structured
off-search source and then enriched with verification evidence:

```bash
python workflow1_tobacco_alcohol.py runs/tobacco-alcohol-records.json \
  --date 2026-08-30 --requested 16 --output outputs/tobacco-alcohol-review.json
python -m unittest test_tobacco_alcohol_track.py
```

This track quarantines search-engine discovery, high-risk categories, chains,
franchises, and businesses with more than two locations. It keeps incomplete
records in `REVIEW_REQUIRED`, reports any quota shortfall, distinguishes USDT
from Bitcoin/XBT/Lightning, and requires observed public reply behaviour before
marking a record `READY_FOR_REPLY_TEST`.

## Run locally

```powershell
python workflow1_daily.py runs/candidates.json --date 2026-08-17 --db D:\BLTeam\BLTeam\ProspectOS\data\prospects.db --vault D:\BLTeam\BLTeam --dry-run
python workflow1_source_audit.py runs/candidates.json --output outputs/source-audit.json
python workflow1_company_screening.py btc-elements.json --minimum-reviewed 120 --require-owner-evidence --audit-cache runs/company-audits.json --output-dir outputs
python -m unittest test_workflow1_v2.py
```

The runner accepts `--db` and `--vault` overrides and can initialize a fresh compatible SQLite database. The Obsidian vault, real candidate lists, reports, and contact data are deliberately not included in this repository snapshot.

## Included files

- `workflow1_daily.py`: validation, scoring, dedupe, import and report generation.
- `workflow1_company_screening.py`: company-first raw-pool screening, website audit, 1–2-location/no-chain hard gate, and CSV/JSON/Markdown export.
- `workflow1_tobacco_alcohol.py` and `prospect_os/tobacco_alcohol_track.py`: isolated lawful tobacco/alcohol track with source provenance, business/entity/activity/contact gates, payment-state separation, reply-behaviour gate, and no quota filling.
- `intent_signal_cli.py` and `prospect_os/intent_signals.py`: read-only adapters for Agent-Reach, Chatwoot, Mautic, PostHog, n8n, and externally verified payment events. They score public activity, direct replies, owned-site buying signals, and actual payment separately; they never send outreach.
- `workflow1_source_audit.py` and `prospect_os/source_tools.py`: read-only source auditing.
- `system/daily-task-prompt.md`: current operating prompt.
- `system/off-search-discovery-policy.md`: mandatory discovery provenance and same-domain quarantine rules.
- `system/source-audit-setup.md`: audit setup and limitations.
- `test_workflow1_v2.py` and `test_tobacco_alcohol_track.py`: safe fixture tests, including rejection of search-only discovery and the tobacco/alcohol hard gates.
- `test_intent_signals.py`: tests that public activity cannot be upgraded to a direct reply, page behaviour cannot be upgraded to a payment, and unknown external events are discarded.

The code does not guarantee replies, rankings, traffic, sales, or conversions. Human review remains required before any message is sent.

## Source-first raw company pools

### Bounded selection and targeted REVIEW repair (recommended)

Use the existing RAW pool before collecting more companies. `expand_buyer_sprint.py`
persists outcomes and chooses mixed-source batches using vertical deficits, the
missing channel's observed human-route yield within each source/vertical/country
segment, country/source diversity and cached evidence. Surplus from one vertical
cannot fill another vertical's quota; dual-route companies count once. Country
diversity is a scheduling preference, not a new formal country quota.
An aggregate low-yield stop does not exhaust untested vertical/country segments:
they receive at most five exploratory records per batch, up to the 30-record
minimum screening window. Stopped tested segments and explicit empty/duplicate
source stops remain excluded.

```bash
python expand_buyer_sprint.py --source runs/discovery/raw.json \
  --initial-prelock runs/prelock-rated-candidates.json \
  --history runs/history/contacted.json --run-dir runs/selection \
  --batch-size 75 --max-records 100 --max-reviews 20 --max-cycles 3 --pages 2
# Resume using the same directory. Supply reviewed updates for the same company IDs:
python expand_buyer_sprint.py --source runs/discovery/raw.json \
  --initial-prelock runs/prelock-rated-candidates.json \
  --history runs/history/contacted.json --run-dir runs/selection \
  --review-evidence runs/reviewed-evidence.json
```

Default invocation limits: 100 new RAW, 20 REVIEW attempts, three cycles;
contact screening uses at most two website pages. REVIEW collects at most two
official pages and two buyer-query tests per attempt, reusing captured page
evidence and cached tests. Reaching a budget saves `PROGRESS`; it does not mean
the sources are exhausted. The RAW source file is never expanded by this command.

Chat outreach additionally checks the purpose of the exact selected route.
`contacts[].outreach_route` distinguishes decision-maker, partnerships, sales,
customer-service and demo-bot routes. A dated, attributable business-recipient
proof plus human reachability is required to count toward formal chat quotas;
support, bookings and bot routes remain in the inventory but cannot fill the
quota. Sales-only and unknown routes need recipient review. Activity evidence
never substitutes for recipient evidence. Screening checks at most one extra
contact page after finding a generic WA, rather than stopping at the first link.
REVIEW accepts `outreach_route` proof for the original route and merges cached
contact evidence conservatively; conflicting uses remain in review.
Source scheduling uses `outreach_whatsapp_found` / `outreach_telegram_found`,
which count business-route candidates, not actual replies. Reply rates require
observed sending and response records and are not inferred from website activity.

`contacts[].human_reachability` has five states: `human_direct`, `human_transfer`,
`automated_welcome`, `bot_only`, `unknown`. Positive states require dated,
route-specific official evidence or an explicitly reviewed owned reply export.
A transfer route is distinct from confirmed decision-maker access. Automated
welcome and unknown routes stay in REVIEW; a company with only bot routes is
rejected. The original links remain in `contacts` for audit.

REVIEW follows the actual missing evidence: ownership/location pages, team size,
official contact labels, or one/two representative buyer-query comparisons.
The default query adapter captures a bounded Bing RSS result set with platform,
date, scope, returned URLs and named competitors. Its absence observation applies
only to that returned set; it is never an AI recommendation or ranking guarantee.
Failed tests remain untested and are cached. Statements, names and team sizes
are collected only when explicit. Unsupported facts stay missing. No new evidence
parks the record immediately rather than replaying the same assessment three times.

Reviewed evidence files are JSON arrays preserving `source_id`/identity,
`company_name` and official website. Put structured updates in `prelock_assessment`
and match each contact by channel plus its original `value` to add
`human_reachability` evidence. Buyer query evidence includes `tested_at`,
`platform`, `scope`, `evidence_urls`, `competitor_evidence`, `prospect_presence`
and a bounded `visibility_gap`. Rating points still need their own traceable
`rating_assessment`; missing points never earn a grade.

Reports separate `this_run` (fresh RAW, REVIEW attempts and transitions),
`current_totals` (current PASS/REVIEW/PARKED/REJECT inventory), and
`cumulative_fresh_raw_scanned`. Expansion source conversion uses distinct screened
companies as its denominator and updates after REVIEW transitions, including
joint source/vertical/country segments. Raw pool size and screening coverage
are reported separately. Historical aggregate reports remain separate priors.

Formal selection solves industry quotas and the exact 24/6 assignment together,
retaining the hard city cap and deterministic quality/source-diversity preferences.
An existing Sample Lock is replayed without replacing its company identities.

### Contact-first dual pools (single-batch runner)

The 1,000+ RAW records are a discovery pool, not the final prospect list. A new
run excludes history, resolves missing official websites only from explicit
outbound links on RAW source/profile pages, and checks those sites for explicit
contact routes. Contact checks inspect the home page and the strongest contact
page first. A qualified business chat route stops the contact check; a generic
or customer-service chat gets one additional contact-page probe within the
configured page budget. With no valid chat, checks continue up to five
same-domain pages (including Portuguese `/contato`,
`/contacto`, `/fale-conosco`, `/atendimento`, `/loja` and `/whatsapp`). Robots
rules and same-domain limits remain in force. Search engines are never used to
discover companies or resolve their websites. The run writes pre-lock files
beside `enriched.json`:

- `prelock-chat.json`: official website links to WhatsApp or Telegram. A formal
  30-company sample requires exactly 24 verified WhatsApp and 6 verified direct
  Telegram routes. A company chat link does not establish decision-maker ownership.
- `prelock-email.json`: email-only candidates **with an explicit human quality
  review**. This pool never fills chat quotas and is not sent automatically.
- `prelock-email_review.json`: email-only candidates awaiting the quality review.
- `prelock-review.json`: no verified chat/email route, unavailable website,
  secondary vertical or another preliminary exclusion.
- `prelock-icp-pass.json`, `prelock-icp-review.json` and
  `prelock-icp-reject.json`:
  cheap ICP and buyer-intent outcomes for chat candidates. Only `PRELOCK_PASS`
  rows can enter the stratified sampler. Supply evidence in `prelock_assessment`
  (including 1–2 actually tested buyer queries, a purchase scenario, a named
  competitor/substitute and evidence URLs); missing evidence stays in review.
- `source-yield.json`: counts and WhatsApp/chat yield rates grouped by source,
  dataset/domain, country and sampling vertical. This helps prioritize source
  collection only; it never changes ICP qualification.
- `prelock-rating-summary.json`: PRELOCK status and buyer-grade totals, exact
  WhatsApp/Telegram shortfalls, and quota-aware `required_slots` by vertical.
  Buyer priority scores use the centralized `prospect_os/buyer_rating.py`
  `RATING_CONFIG` (`buyer-rating-v1`, 0–100). Each positive category score needs
  a scored assessment and traceable source URL, timestamp, evidence label and
  claim; missing rating inputs earn no points. PRELOCK hard gates are evaluated
  first and are never overridden by grade.

For an email-only record to enter the quality-reviewed email pool, supply
`prelock_quality_review: {"reviewed": true, "rating": "high", "claim": "...",
"source_url": "https://..."}` in its RAW record. A title or score alone is not
proof. The pre-lock website checks start with Web3, AI/B2B and vape/tobacco,
then alcohol/adult retail, and resume from `prelock-screen.jsonl`; use
`--refresh-prelock` in a **new run directory** to revisit changed websites.
These are route candidates, not P0 sales qualifications: the existing owner,
activity, buyer-query, competitor and first-fix gates still apply afterward.

The sampler sees only `PRELOCK_PASS` rows, ranks S → A → B inside each existing
vertical bucket, and excludes C from a formal 30-company sample. It preserves
the vertical mix, 15/15 Track split, city cap, source diversity and seed tie-break.
If a prospect publishes both routes, WhatsApp is the default; Telegram is selected
only when needed to meet the exact 24/6 quota, and both original routes remain in
the record. If any vertical or channel quota is short, the run writes the pre-lock
files and summary but does not freeze a partial formal sample. Email does not
substitute for chat. `--allow-shortfall-lock` remains diagnostic-only and must not
be used for the formal run.
Never call a phone number WhatsApp without an explicit link. No bulk
email tool or automatic message sending is part of this workflow.

Use `--pool-mode legacy` only to replay the older RAW-first selection procedure
with a **new** lock path. An existing lock always replays its original frozen
cohort, regardless of changes to RAW, history files or contact screening.

### Sample Lock for a buyer sprint

After source-first discovery, supply the previous used-company and contacted
JSON exports plus prior sample locks before the first run. History exclusion
matches `identity_key`, `source_id`, normalized website domain and a normalized
company-name SHA-256. The excluded RAW rows are listed in
`excluded-history.json` with the matched history file and reason. Contact-first
screening then separates the remaining eligible records into the chat and email
pools before sampling. Missing or malformed supplied
history inputs stop the run before a lock is created.

Run the sampler once per run directory. The first
step writes `sampled-lock.json` with the seed, timestamp, requested limit,
ordered IDs, source/identity keys, verticals, tracks and frozen RAW records.
Reusing the same path with a different sample fails; use a new directory for a
new run. A rerun reads the frozen RAW records and original sampling summary
from the lock even if discovery/raw.json changes. The enrichment output is
written only after all locked company IDs pass the final check. Pass the same
lock to every later step:

```bash
python research_buyer_batch.py --source runs/buyer-sprint/discovery/raw.json \
  --history-used runs/history/used-companies.json \
  --previous-contacted runs/history/contacted.json \
  --previous-sample-lock runs/previous-sprint/sampled-lock.json \
  --sample-lock runs/buyer-sprint/sampled-lock.json \
  --output runs/buyer-sprint/enriched.json \
  --sampling-summary runs/buyer-sprint/sampling-summary.json
python enrich_company_contacts.py runs/buyer-sprint/enriched.json \
  --sample-lock runs/buyer-sprint/sampled-lock.json \
  --output runs/buyer-sprint/contact-enriched.json
# Gate each externally prepared JSON before passing it to the next stage;
# repeat with --stage contact-discovery, audit and outreach where applicable.
python prepare_locked_stage.py runs/buyer-sprint/buyer-query-draft.json \
  --stage buyer-query --sample-lock runs/buyer-sprint/sampled-lock.json \
  --output runs/buyer-sprint/buyer-query-locked.json
# After human evidence and outreach preparation, the reviewed JSON must keep
# all locked records and their immutable identity fields.
python workflow1_daily.py runs/buyer-sprint/reviewed.json --date 2026-09-23 \
  --mode buyer-intent --sample-lock runs/buyer-sprint/sampled-lock.json \
  --output-dir outputs/buyer-intent --dry-run
```

Each history flag may be repeated for multiple files. The four counts
`raw_pool`, `history_excluded`, `eligible_after_history_filter` and `sampled`
are saved in `sampling-summary.json`. History is checked when a new sample is
created; rerunning an existing lock preserves that run's original exclusions
and sample. Start a new run directory to apply newly added history sources.

The buyer-intent runner reads the lock before qualification, audits, funnel
events or shortlist preparation. `decisions.json` is the full locked cohort in
sample order; `top20.json` and `top5.json` are P0 views of that cohort. A
missing row stays in `decisions.json` with `research_failed` and
`contact_missing` status. Unlocked or spoofed company identities are written
to `rejected-not-in-sample-lock.json` and fail the run before sales outputs.
Each enriched/decision record and the summaries include
`sample_lock_verified`. The generic source-pool builder remains a pre-sampling
discovery tool, so it does not consume a lock.

Build the company pool before doing any search or AI-visibility work. The native adapters implement
the useful parts of the evaluated OSM lead-pool and website-contact projects without installing
overlapping crawler applications as opaque runtime dependencies.

```bash
# Fetch high-value local categories from a bounded OSM/Overpass geography.
python build_source_pool.py overpass --bbox 25.70,-80.35,25.90,-80.10 \
  --sector regulated_retail --sector automotive_high_value \
  --output runs/miami-raw.json
# `--place "Miami, Florida"` may replace `--bbox`; place geocoding only resolves
# the boundary and is not used to discover businesses.

# Or normalize an already downloaded OSM, public GeoJSON or registry CSV snapshot.
python build_source_pool.py osm-json runs/overpass.json --output runs/osm-raw.json
python build_source_pool.py geojson runs/licenses.geojson \
  --dataset-url https://data.example.gov/business-licenses \
  --source-name city-business-licenses --output runs/licenses-raw.json
python build_source_pool.py merge runs/osm-raw.json runs/licenses-raw.json \
  --output runs/combined-raw.json

# Next, sample and lock this RAW pool as shown above before contact enrichment.
```

Each raw-pool run writes both the JSON records and a `.manifest.json` with source names, input URLs,
record count and a SHA-256 snapshot hash. OSM records retain the original object URL and all observed
locations. A missing source `website` tag is recorded as unknown, not as proof that no website
exists. Contact enrichment respects robots by default, never turns a phone into WhatsApp, and never
equates a business account with a decision maker.

See [system/source-pool-integrations.md](system/source-pool-integrations.md) for evaluated upstream
projects, enabled adapters and deliberately disabled integrations.
