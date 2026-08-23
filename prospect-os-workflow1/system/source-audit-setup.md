# Prospect OS source audit add-on

This add-on is read-only and does not change workflow 1 scoring, SQLite data, or outreach behavior.

## Installed capability

- Playwright: already present in the workspace and used for browser/page checks.
- Trafilatura 2.2.0: installed in the active Python 3.14 user environment for main-text extraction.
- Existing workflow1_daily.py: remains the source of truth for canonical contact validation, P0 tiering, and database dedupe.

## Off-search discovery enforcement (v4)

Candidates must record `discovery_channel`, `discovery_source_url`, `discovery_source_note`, `business_quality`, and `distribution_gap`. The discovery source is audited alongside the website and must be a public URL on a different domain. Google/Bing/AI Search may appear only as final diagnostic evidence; a search-only discovery channel is rejected before import.

## Current controlled P0 relaxation

For the current deep-search pass only, P0 allows activity observed within 3 days and a conservative team upper bound of 40. The score threshold, direct-contact requirement, Web3-only rule, risk exclusions, GEO gap, and dedupe rules remain unchanged. This is at most a 2x team-size relaxation and is not a quota override.

## Run a source audit

```text
python workflow1_source_audit.py runs/2026-08-15-p0-large-search-candidates.json --output outputs/2026-08-15-source-audit.json
```

The audit fetches only URLs already present in the candidate JSON, including the off-search discovery source. It records HTTP status, extracted text length, a short snippet, company-token match and contact-token match. A failed fetch is recorded as failed/unknown and never becomes a verified fact.

## Deliberately not installed

- Scrapy: useful for a large, scheduled crawl, but not needed for the focused P0 batch and would increase crawl noise.
- dedupe: the current runner already canonicalizes domains, phone/Telegram handles, people and fuzzy company names. The package has no Python 3.14 binary on the configured index, so it is not added just for appearance.
- Microsoft Webwright: a long-horizon browser-agent framework requiring extra model/API configuration; not suitable for the evidence-first P0 gate.

These decisions preserve workflow 1 and avoid treating a tool's output as proof of a contact or business claim.

