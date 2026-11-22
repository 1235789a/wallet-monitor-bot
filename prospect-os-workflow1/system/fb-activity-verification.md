# Facebook 30-day activity verification — MultiHub, 2026-11-22

The `main` Daily27 Python pipeline now rejects FB prospects lacking **two separate, real public activity proofs**. This does not sign into Facebook, scrape private data, validate Messenger delivery or auto-send.

**Evidence you must actually inspect**:
- Dated buyer-relevant business activity of the same company within the last 30 days (real specific update, not a homepage, evergreen undated services page or directory snippet).
- A **public business post by the same verified intended founder/business recipient** on Facebook, X, LinkedIn or Instagram, within the last 30 days. Exact post URLs, not profile or search pages; event appearances alone are supplemental. An FB Page posting does not prove that the founder is active. If the person has no public post, label HOLD, not inactive as a proven fact.

A reviewer records the *exact original post URL*, visible date, UTC check timestamp within the last 3 days, nonempty excerpt, confirmed actor identity, local screenshot (PNG/JPG/WebP) and SHA256 of the actual bytes. The checker recalculates SHA256 and checks date/window/URL specificity, but **cannot independently read image pixels or prove actor identity**; `subject_confirmed` means the reviewer performed that check. If a Facebook post cannot be read, use an exact attributed post on an approved alternate platform. If the personal Facebook route cannot be separately verified as reachable and suitable, keep FB HOLD and consider an independently verified alternate route with the same entity ID. Keep 72h/7d/14d/30d grading and existing weights.

## JSON manifest accepted by the CLI

Create a local file, for example `/data/fb_activity_evidence.json`:

```json
{
  "records": [{
    "original_prospect_id": "FB-EXAMPLE-001",
    "business_activity_proof": {
      "source_url": "https://example.com/news/verified-business-launch",
      "activity_date": "2026-11-12",
      "checked_at_utc": "2026-11-15T02:00:00+00:00",
      "excerpt": "Specific new product/service announcement seen in the article.",
      "subject_type": "COMPANY",
      "subject_confirmed": true,
      "capture_path": "/data/screenshots/business-post.png",
      "capture_sha256": "REPLACE_WITH_REAL_64_CHAR_SHA256"
    },
    "fb_activity_proof": {
      "source_url": "https://www.facebook.com/actual.founder/posts/123456789",
      "activity_date": "2026-11-13",
      "checked_at_utc": "2026-11-15T02:00:00+00:00",
      "excerpt": "Recent public post by the verified intended business recipient.",
      "subject_type": "CONTACT_PERSON",
      "subject_confirmed": true,
      "capture_path": "/data/screenshots/founder-public-post.png",
      "capture_sha256": "REPLACE_WITH_REAL_64_CHAR_SHA256"
    }
  }]
}
```

The example is a SCHEMA ONLY, not a real verified prospect. Replace URLs, dates and actual screenshot hashes with observed data.

Run (with actual local RAW/history/evidence sources):

```bash
python scripts/run_daily27_pipeline.py \
  --downloads-dir /data/raw \
  --history-dir /data/history \
  --fb-activity-manifest /data/fb_activity_evidence.json \
  --output-dir /data/daily27-results
```

The optional manifest can also be placed at `<downloads-dir>/fb_activity_evidence.json`. No proof file or missing capture -> zero FB activity-verified candidates, not falsely qualified. Legacy `recent_30d_activity_status=PASS_*` never grants FB activity approval. Required route, history, legal/policy and human consent gates remain independent and do not automatically pass.

The report adds `loss_breakdown.held_fb_activity_not_verified` and `funnel_metrics.fb_activity_verified`. FB HOLD prospects are not backfilled into quota as "qualified". A valid dated post is not proof of present Messenger online status.
