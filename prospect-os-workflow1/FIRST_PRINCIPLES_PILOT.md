# First-Principles Pilot: 10 WhatsApp + 2 Telegram
Opt-in read-only adapter on top of Growth Engine v2.1. The business outcome is **paid projects / net profit**, not an inflated count of companies with chat links. Pricing and purchase-fit remain hypotheses until an actual payment.

The new adapter imports `prospect_os.growth_engine_v21.audit_run` at execution time. All existing hard gates (source provenance, identity, historical exclusions, industry research, commercial fit, person/business-human channel, copy QA and regulated isolation) remain **mandatory**. It reports only v2.1 READY, enforcing the new 10/2 quota. Published `wa.me/message/...` deep links are recognized as **URL candidates** but do not get upgraded to v2.1 READY without underlying validated identity and contact evidence.

```bash
cd prospect-os-workflow1
python -m unittest -v test_first_principles_pilot
python first_principles_pilot.py PRIVATE_V21_INPUT.json NEW_OUTPUT_10WA2TG.json
```

Inputs and outputs should stay PRIVATE, outside the public repository. No auto messaging, no browser-side scraping or credential storage here. The user must review all candidates before any outreach. Retain rejected/HOLD, do not fill shortfall with old leads. Original v2.1 runner remains unchanged; this branch is reversible.

**Live run note (2026-10-22):** Independent agency-directory sample and official sites established several publicly linked WhatsApp/TG *route candidates*. Partner purchase fit, full history coverage, direct human reachability and detailed dossiers are not yet evidenced; consequently they cannot enter READY. A separate private Google Drive run report contains the real observed links and caveats. Never include live phone numbers or private CRM in this public repository.

## Critical history-sync gate (2026-10-23 correction)

**Do not treat** the 318 recorded history identities as proof that the user's manual WA/TG outbound log is complete. User reported repeated outreach despite Drive nonmatches. Before releasing *any* NEW outreach list, the private v2.1 JSON must contain:

```json
{
  "batch_started_at": "2026-10-23T10:00:00+00:00",
  "outbound_history_proof": {
    "review_status": "PASS",
    "reviewer": "human-reviewer",
    "private_evidence_ref": "private://path/to/reconciled-outbound-log",
    "covers_sent_through": "2026-10-23T10:00:00+00:00",
    "channels": {
      "whatsapp": {"reviewed": true, "source_id": "private-wa-export-id"},
      "telegram": {"reviewed": true, "source_id": "private-tg-export-id"}
    }
  }
}
```

Both channels require a real, documented human reconciliation of *actual sent/replied chats*; no fabricated attestation. Also normalize brand aliases, official domain, phone number across `wa.me`, `api.whatsapp.com`, and local/international punctuation, TG handles, and shared agency/client relationships for human review. The metadata check is deliberately insufficient to verify the private evidence itself; if reviewer cannot access logs or date coverage is stale, set `review_status="HOLD"`, **not** `PASS`. Without proof, `pilot_report` releases zero READY and lists `OUTBOUND_HISTORY_UNVERIFIED` instead. Never commit these exports to public GitHub.

The five original tests plus two new regression tests are present (7 test cases). These additional tests were **not executed via CI in the current connector session**; do not claim a full passing suite without running it.

