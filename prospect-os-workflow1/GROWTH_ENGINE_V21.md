# Growth Engine v2.1: opt-in research release gate

Legacy sheets and the existing 30-company pipeline can call a line READY despite
missing source records, external-purchase evidence or a verified direct contact.
This additive runner evaluates explicit evidence and preserves unknown states;
it does not modify old ledgers, send messages or publish case content.

Run from `prospect-os-workflow1`:

```sh
python3 run_growth_v21.py INPUT.json NEW_OUTPUT.json
python3 -m unittest test_growth_engine_v21 test_source_pool test_buyer_rating test_contact_pools -q
```

The input contains `run_id`, `rows`, `history`, `dossiers`. A row references an
independent source ID/record/hash, official website evidence, attributed human
WA/TG route, reviewed ICP, external-purchase evidence, client context and an
industry dossier. Each evidence object uses `url`, `claim`, `grade`, `evidence_id`
and a timezone-bearing `retrieved_at`. Use UNKNOWN rather than an invented claim.
The test fixtures are synthetic regression inputs, never real prospects.

The independent 10-point priority dimensions are ICP value (3), buyer search (2),
direct role (2), purchase fit (2), recent activity (1). A score cannot override a
failed gate. Industry research needs a reviewed score >=8, verified critical
facts, four sources and at least two source types. Passing a structural check
does not prove the researcher read a source: semantic review is still required.

History matches on names/explicit aliases, domains, verified person aliases,
WA numbers and TG handles. A supplied registrable domain may join subdomains;
the code deliberately does not guess public suffixes from the last two labels.
Shared numbers are an entity-association warning, never proof of ownership.
No historical match means only no match in the supplied scope. Historical sends,
replies and refusals exclude a new-customer release. Prior unsent batches remain
review rather than new discovery. `allocate()` deduplicates again at release.

The fixed capacities remain 12 WA/3 TG daily, 48/12 for four days, 16/4 reserve,
64/16 total. The release report includes exact channel gaps. A zero qualified
yield has undefined minutes per qualified customer, never zero cost.

Positive AI results are accepted. v2.1 does not call the legacy
`visibility_gap_evidence` requirement; the old workflow remains intact for
rollback. Negative marketing claims require complete actual test records, and
human claim review remains mandatory. Test completion needs query/platform/model
(UNKNOWN allowed when not exposed), timestamps, locale, full raw text and evidence
artifact. Free-check permission never becomes public permission. Regulated
records remain isolated from this ordinary sales runner even after a separate
manual compliance review; regulated outreach needs its own explicit workflow.

Migration boundary: this PR is an opt-in module, not an unattended production
rollout. Convert one real run to the input contract, inspect the hold reasons,
attach missing evidence, rerun to a new filename and review the final queue.
No credentials, customer records or private conversation data belong in this
public repository. Private run artifacts remain in the authorized Drive folder.

Verification: 16 new regression cases plus 32 existing source/rating/contact
tests. Covers cross-batch duplicates, shared phone brands, fake WA, TG channels/
bots, internal DIY, legacy 80 READY claims, unsupported negative claims, sector
misreading, missing copy, permissions, regulated isolation, research gaps,
purchase-fit unknown, release dedup and undefined source cost.
