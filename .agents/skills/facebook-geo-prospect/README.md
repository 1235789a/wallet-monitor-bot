# Facebook GEO Prospect — in-repository quick start

This skill is **research and draft only**. It does not connect to Facebook accounts or send messages.

## Codex
Open this repository in Codex, select the branch containing this skill, and invoke:

`$facebook-geo-prospect 从 Google Drive 历史记录排重，查找 8 家横跨至少 4 个行业的新 Facebook 企业候选。核验公司、决策人、官网与可公开联系的业务路径；输出来源、评分、HOLD/READY、可点击链接和自然英文私信草稿。不发任何消息，也不编造 AI 搜索结果。`

Codex's access to Google Drive must be separately connected or supplied via reviewed CSV exports. Without that data, report `HISTORY_UNVERIFIED` rather than claim global dedupe.

## Run local dedupe tests
`python -m unittest discover -s .agents/skills/facebook-geo-prospect/tests -v`

## Run with verified history exports
`python .agents/skills/facebook-geo-prospect/scripts/dedupe.py --candidates candidates.csv --history history.csv --history .agents/skills/facebook-geo-prospect/assets/prior_fb_candidates.csv --output deduped.csv`

Importantly, the public GitHub repository should contain only workflow definitions and public references, **not** client conversation logs, private CRM exports, credentials, or personal data.

The previous Facebook prospects in `assets/prior_fb_candidates.csv` are not confirmed contacted. The `PRIOR_BATCH_REVIEW` state indicates only that they were previously surfaced.
