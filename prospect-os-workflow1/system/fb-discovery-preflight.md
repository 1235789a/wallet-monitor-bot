# FB discovery source preflight (activity-first, 2026-11-21)

Do not change the core ICP or the required personal FB activity gate.
The previous 50/49 research rounds demonstrated zero verified fresh personal 
posts; bulk company enrichment cannot fix an unavailable evidence source.

## Autonomous discovery sequence

1. Use an authorized public source: public business discussion/post links,
   founder interviews/event or association pages linking to business profiles,
   independent launch/partner communities. A search index is a navigation hint,
   never the independent source or proof. Use an available authorized browser
   for specific public pages if permitted; do not bypass login/access limits.
2. Before deep research, probe at most 10 distinct business-related profiles
   per source. Capture the specific personal post URL, visible date and
   excerpt, exact identity source, observed access status, original screenshot
   and SHA256. Record failures too; do not infer personal activity from
   company Page activity, LinkedIn posts, search snippets, or crawl dates.
3. Run the preflight:
   from prospect-os-workflow1, `python -m prospect_os.fb_discovery_preflight probes.json`.
   Input is {"probes":[...]}; see the module and synthetic test fixture for keys.
   At least 2 verified different people permits continuing that source.
   After 10 probes with fewer than 2 verified, switch public source or HOLD;
   do not research another 50 companies on a zero-yield source. If the provider
   explicitly denies access, stop that provider immediately.
4. For verified probes only, research the company, check the ICP and history,
   then supplement all public business contact routes. Preserve immutable IDs,
   actual source dates and the existing dual-evidence verification workflow.
   The preflight NEVER grants ICP_PASS, ASSET_READY or SEND_READY.
5. Keep unsuccessful FB candidates in a separate HOLD or cross-channel
   enrichment queue; do not count an alternative channel as an FB quota or
   duplicate a previously delivered company. Continue the existing WA/TG lanes.
6. Output per-source probes, verified distinct profiles, blocked/missing
   proofs, dated posts, full history coverage and qualified yield. Record the
   actual source-access result, not theoretical tool availability. No automatic
   sending, friend requests, or messages. User does not need to discover leads
   manually; if no authorized data source provides evidence, report the
   constraint and await the next source or authorized connection.

Existing fb-activity-verification.md remains binding, including separate
company activity evidence and fresh actual capture verification. The preflight
is only a source-capability screen; no private content is required.
