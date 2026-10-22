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
