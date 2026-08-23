# Prospect OS Workflow 1 — Final v4

This folder is a portable snapshot of the current Web3-only Prospect OS workflow. It is intentionally isolated from the host application's existing files.

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

## Current P0 rules

- Web3 only; handmade and regulated/high-risk categories stay excluded.
- Owner-operated or independent small businesses only. Chains, franchises, branded branches, unknown ownership, and businesses with 3+ locations are rejected in code.
- No quota filling. A request for 30 means research up to 30 valid records; invalid or unverified records are not replaced with fillers.
- WhatsApp is preferred. Telegram is capped at 3 retained records per run.
- P0 requires activity within 3 days, a team upper bound of 40, business quality `strong`, a `strong` or `moderate` distribution gap, observed public reply behavior, and a confirmed decision-maker contact.
- Ranking priority is reply probability → decision-maker access → real business quality → partnership openness → GEO/search gap.
- `Not found` Reply Behaviour is capped at 12/30 and `Inaccessible` is inferred only; neither can enter P0.
- No automatic outreach, publishing, or database mutation from the research step.

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
- `workflow1_source_audit.py` and `prospect_os/source_tools.py`: read-only source auditing.
- `system/daily-task-prompt.md`: current operating prompt.
- `system/off-search-discovery-policy.md`: mandatory discovery provenance and same-domain quarantine rules.
- `system/source-audit-setup.md`: audit setup and limitations.
- `test_workflow1_v2.py`: safe fixture tests, including rejection of search-only discovery.

The code does not guarantee replies, rankings, traffic, sales, or conversions. Human review remains required before any message is sent.
