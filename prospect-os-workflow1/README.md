# Prospect OS Workflow 1 — Buyer-Intent Sprint

The default runner now prioritizes paid-prospect evidence rather than contact volume. It preserves
the existing company-first discovery, verification and deduplication foundation while adding a
strict buyer-intent mode. The current operating rules are in
[system/buyer-intent-sprint.md](system/buyer-intent-sprint.md).

The first production mix is fixed at **10 high-ticket B2B + 10 independent local businesses**.
Neither side may fill the other side's shortfall. WhatsApp, Telegram, email and verified founder
social profiles are valid routes; no channel quota is a success metric.

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
- WhatsApp is preferred. Telegram is capped at 3 retained records per run.
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
- `intent_signal_cli.py` and `prospect_os/intent_signals.py`: read-only adapters for Agent-Reach, Chatwoot, Mautic, PostHog, n8n, and the wallet monitor. They score public activity, direct replies, owned-site buying signals, and actual payment separately; they never send outreach.
- `workflow1_source_audit.py` and `prospect_os/source_tools.py`: read-only source auditing.
- `system/daily-task-prompt.md`: current operating prompt.
- `system/off-search-discovery-policy.md`: mandatory discovery provenance and same-domain quarantine rules.
- `system/source-audit-setup.md`: audit setup and limitations.
- `test_workflow1_v2.py` and `test_tobacco_alcohol_track.py`: safe fixture tests, including rejection of search-only discovery and the tobacco/alcohol hard gates.
- `test_intent_signals.py`: tests that public activity cannot be upgraded to a direct reply, page behaviour cannot be upgraded to a payment, and unknown external events are discarded.

The code does not guarantee replies, rankings, traffic, sales, or conversions. Human review remains required before any message is sent.
