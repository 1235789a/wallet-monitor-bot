# Source-pool integrations

The source-pool layer exists to reduce search-engine survivorship bias. It creates a frozen RAW
company set before website, contact, buyer-query or visibility research begins.

## Enabled in this repository

### OpenStreetMap / Overpass raw-pool adapter

`build_source_pool.py overpass` queries OSM by bounded geography and explicit high-value sector
tags. The design takes the useful source-first pattern from
[osm-lead-scraper](https://github.com/sophiamaybea/osm-lead-scraper),
[local-prospect](https://github.com/spencer-life/local-prospect),
[No-website-scraper](https://github.com/tkarman-singh/No-website-scraper) and
[trendradar](https://github.com/Artaeon/trendradar), but uses a small native adapter instead of installing four
overlapping crawlers. Every record retains the OSM object URL, raw object, retrieval timestamp and
SHA-256 snapshot hash.

OSM coverage depends on contributor tagging. A missing `website` tag means only
`website_absence_status=unknown`; it never proves that the company has no website. OSM object
timestamps are dataset-change evidence, not recent marketing evidence. Use and redistribution of
OSM data must retain the required OpenStreetMap attribution and comply with ODbL.

### Public GeoJSON and CSV adapters

The same command imports public company registries, licensing datasets, chamber exports and local
open-data files. The operator must provide the public dataset URL and an approved off-search
channel. Google/Bing/search/AI-search channels are rejected. This is the extensible route for
city/state licensing lists and sector-specific registries without coupling Prospect OS to a single
provider.

### Official-site contact enrichment

`enrich_company_contacts.py` adapts the useful extraction pattern from
[website-email-contact-scraper](https://github.com/omkarcloud/website-email-contact-scraper). It crawls only the already supplied website, respects robots by
default, and records the exact page for every email, phone, WhatsApp, Telegram or social link.

- Plain phone never becomes WhatsApp.
- `info@`, `sales@`, `support@` and similar inboxes are `GENERIC_BUSINESS`.
- A named employee email is `NAMED_EMPLOYEE`, not automatically a decision maker.
- A company WA/TG/social link remains a generic route until separate evidence ties it to an owner,
  founder, CEO, marketing lead or growth decision maker.
- No message is sent.

## Evaluated but not enabled by default

- [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper): mature enrichment coverage, but Google Maps is a ranked platform and
  unauthorized scraping may conflict with platform terms. It is not a primary company source and
  no runtime dependency is installed.
- [OpenCorporatesCLI](https://github.com/skickar/OpenCorporatesCLI): useful for registry verification, but the examined CLI cannot supply officer
  data and current API access is rate/credential dependent. Public registry CSV/GeoJSON imports are
  supported without adding this dependency.
- [cdx-index-client](https://github.com/ikreymer/cdx-index-client): useful for Common Crawl history, but the examined client targets old Python.
  Website-history lookup is not required to form the raw company pool.

These exclusions are deliberate: “installed” means an adapter improves the evidence chain, not
that every discovered repository is copied into production.

## Required sequence

1. Freeze a RAW pool from OSM or a public registry/directory dataset.
2. Preserve the source snapshot and coverage-bias note.
3. Merge exact identities while preserving all location observations.
4. Enrich the supplied website and contact routes.
5. Verify ownership, activity, buyer value and direct decision-maker access.
6. Run buyer-query and competitor visibility tests only for preflight survivors.

Search results may diagnose visibility after step 1. They may not add companies to that frozen raw
pool.
