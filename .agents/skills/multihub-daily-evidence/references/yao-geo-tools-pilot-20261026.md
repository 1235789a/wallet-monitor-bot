# 姚金刚工具适配试跑（2026-10-26）

> Experimental decision record; **no silent production switchover**. 2026-10-26 Google Doc: https://docs.google.com/document/d/1MN2zKZsvnrortGF0Tc8jHJIc7HsX5S64jPs6WDp1R7I/edit

## Decision

**Adopt Yao GEO method as the preferred analytical method; keep MultiHub's own lead sourcing, multi-source identity dedupe, WA/TG route gate, factual evidence-image generation, manual outreach, and CRM.**

Use official upstream code/docs:
- `yaojingang/yao-geo-skills`: `yao-geo-intent-miner`, `yao-geo-page-audit`, `yao-geo-effect-monitor`, `yao-geo-knowledge-base-builder`.
- `yaojingang/GEOHub`: v0.7 **Experimental**, `geo-site-diagnose` capped at 10 same-host pages; no live answer validation; keep optional sandbox only until a real CLI benchmark.
- `yaojingang/GEOFlow`: enterprise knowledge, AI quality, reviewed content, multi-site distribution & analytics; not a contact-verification or cold-outreach engine. Stable 3.1.0; source main 3.2 beta. PHP 8.3+, PostgreSQL, Redis, Docker; AGPL-3.0 licensing and associated obligations.

## Candidate pipeline (method + operational responsibilities)

0. **MultiHub / PRELOCK**: entity dedupe, route ownership, permitted recipient, buyer economics. Missing route => HOLD; stop costly research.
1. **Yao Knowledge Base**: source-first, company facts with source URL, accessed_at, exact excerpt, source quality, volatile-fact freshness and NO_EVIDENCE gaps. Facts must be about this company, never sourced from a sector-memory stereotype.
2. **Yao Intent Miner**: derive 3-5 buyer questions per prospect from observed products/market and plausible roles, keep `query_status=PROPOSED`; no fake search-volume or executed-answer claims. For western-market ICP adapt from domestic defaults to ChatGPT/Gemini/Perplexity, local-language/locale.
3. **Yao Page Audit**: investigate real page-specific inconsistencies, generic filler, missing extractable facts and citations. Diagnose onsite material only. A observed scoped contradiction/irrelevance; B reasonable improvement hypothesis, not diagnosis.
4. **Yao Effect Monitor**: where actual platform rights/tooling allow, perform controlled, logged platform queries, store original answer, citations, metadata and repeat count. Without this, `AI_TEST_PENDING` and NO visibility claims. ChatGPT crawler requires legitimate browser access; not a permission bypass.
5. **MultiHub Case Engine**: screenshot + raw HTML/text + SHA256 + visible source/capture date + annotated PNG + claim-scope + matching single-CTA message. No generated fake screenshot. Missing source image => `PNG_PENDING` not READY.
6. **MultiHub CRM**: quota WA12/TG2 is a *goal*; actual accepted counts must pass all gates, and `DELIVERED != SENT != REPLIED != PAID`.

## Live public-page trial — Fresa Gold / 2026-10-26

Target: https://fresatechnologies.com/products/fresa-gold/

Sourced observations from current publicly fetched page:
- `FRESA-OBS-01`: 'Customer Service' module's factual operation paragraph is followed by a generic definition of prospective customers and negotiations. Scope: that module's visible page text; not the product's actual service.
- `FRESA-OBS-02`: 'Documentation' module's concrete shipment-document description is followed by generic definitions of technical writers and corporate communications. Scope: that module's visible page text.
- `FRESA-OBS-03`: 'Management' description turns into general management hierarchy definitions rather than feature-specific evidence.

Buyer query proposal (NOT EXECUTED): 'Which freight forwarding ERP supports UAE e-invoicing, manifest EDI, and shipment-to-accounting workflows for a regional forwarder?'

Diagnosis: real content relevance opportunity, **not** proof of nonappearance in ChatGPT, AI hallucinations, business loss, or platform ranking. Suggested fix: remove generic filler, replace with concrete module inputs/outputs, region-specific rules and linked verifiable artifacts. `EVIDENCE_TYPE=onsite_observation`, `AI_TEST=NOT_TESTED`, `IMAGE=NOT_CREATED`, `OUTREACH=HOLD` until route/recipient and screenshot QA.

Prior template: generic 'check whether Fresa Gold appears in ChatGPT' without observed gap. New method gives a concrete testable claim.

## Evaluation gates for six-lead pilot

3 matched leads current v3 method, 3 Yao-method; log per lead actual minutes, hard-evidence pass, company-specific claim verification, buyer query quality, screenshot and PNG completion, route verification, human-reviewed message approval, and later independently observed response/conversion. Do not present response-rate significance from six samples. Roll back to original if QA falls, runtime cost dominates, or experimental tool can't supply source provenance.

## Trial limitations

This was a **manual application of upstream documented methodology** to live public HTML and not a downloaded/executed GEOHub or GEOFlow binary, not a browser-screenshot production run, and not an actual ChatGPT/Gemini answer test. Keep the production schedule unchanged while the method is evaluated.
