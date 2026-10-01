# Buyer sprint source-first expansion, 2026-09-24

- Branch: `agent/buyer-intent-sprint`; module: `prospect-os-workflow1`.
- RAW: 1,222 deduplicated company records. Includes 1,000 wine shop source records from [`openwinemap`](https://github.com/openhistorymap/openwinemap/tree/af92e371f323894b7e9a3db2449146fa65a4df9b/data/countries), which republishes [OpenStreetMap data under ODbL](https://www.openstreetmap.org/copyright); three additional vape shop source records with website hints from [`west-yorkshire-mapping-old`](https://github.com/open-innovations/west-yorkshire-mapping-old/tree/08a7c2b3e33643d307bba6c6bc36956b4e3db85c/data). Original source identifiers, links, tags, and snapshot hashes are preserved in `../discovery/west-yorkshire-2026-09-24/raw-expanded.json`.
- Selection of the 1,000 wine shop records was deterministic, round-robin by country with unique website domains. All source records had a tagged city and website, neither independently verified at RAW stage. The source contains no tagged WhatsApp route among these 1,000 records. The geography and one-vertical focus are sampling biases, not evidence of qualification.
- History sources: prior `runs/buyer-sprint/enriched.json` (30), a prior 20-company export, and five known previously contacted names. Their minimal matching fields are bundled in `history-used-minimal.json` so this run can be reproduced without the earlier exports. The history filter result is in `excluded-history.json`.
- `sampled-lock.json` freezes 30 selected identities. Enrichment retains failed websites without substitutions. `sampling-summary.json` lists 15 Track A / 15 Track B, including three vape and twelve alcohol records; adult retail has a five-record quota shortfall. `sample_lock_verified` is true for all downstream rows.
- `enriched.json` contains sampled website research; `contacts-from-cached.json` conservatively parses matching cached HTML snapshots with source URLs. The only explicit WhatsApp links found are on the official pages for Vinarija Kozlović and Tonel Privado. Both are business chat routes; ownership by a decision maker is unverified. No AI visibility gap, decision maker access, purchase intent, or sales reply has been established. These 30 records are a research sample, **not** a 30-company outreach-ready list or 24 verified WhatsApp leads.

To repeat the 30-company selection, use the committed RAW and history inputs with a new run directory:

```sh
cd prospect-os-workflow1
python research_buyer_batch.py --source ../runs/buyer-sprint/discovery/west-yorkshire-2026-09-24/raw-expanded.json --history-used ../runs/buyer-sprint/2026-09-24-1222/history-used-minimal.json --limit 30 --sample-lock ../runs/buyer-sprint/replay/sampled-lock.json --output ../runs/buyer-sprint/replay/enriched.json
```
