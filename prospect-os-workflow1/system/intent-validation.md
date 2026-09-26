# Reply and purchase-intent validation

This layer combines external collectors but does not pretend that a model can
read a stranger's mind.

## Responsibilities

| Layer | Source | Evidence |
| --- | --- | --- |
| Public activity | Agent-Reach or manually audited official pages | Recent post, opening-hours update, public customer reply |
| Direct reply | Chatwoot on an official business channel, or a human-run test recorded in the OS | Delivered/read/replied/asked details/asked price |
| Owned-site intent | Mautic or PostHog | Preview, pricing, form, demo, checkout and invoice events |
| Transport | n8n | Webhooks and event routing only |
| Payment ground truth | wallet-monitor-bot | Observed USDT arrival |

## Interpretation rules

- A WhatsApp or Telegram button is `contact_open_only`, not a reply.
- A public comment reply is `publicly_active_only`, not a reply to our message.
- BTC, XBT and Lightning are crypto signals, not USDT proof.
- A price-page visit or checkout start is purchase-intent evidence, not a sale.
- `paid` is the only event that receives `observed_payment` ground truth.
- The scoring module caps pre-contact reply scores at 45 so public activity cannot
  silently become cold-outreach reply certainty.
- Unknown or unsupported webhook event names are discarded rather than guessed.

## Event contract

Generic/n8n/manual events use:

```json
{
  "event_type": "asked_price",
  "company_key": "shop-1",
  "occurred_at": "2026-08-31T12:00:00Z",
  "evidence_url": "https://example.invalid/conversation/1",
  "metadata": {"channel": "whatsapp"}
}
```

Run the read-only scorer:

```bash
python intent_signal_cli.py events.json --source generic --output outputs/intent-score.json
```

The output always includes both scores, states, evidence, ground-truth labels,
warnings, and `outreach_sent: false`.

## Deployment boundary

This repository contains adapters and scoring rules, not copies of Chatwoot,
Mautic, n8n or PostHog. Those applications are independently deployed and
connected through webhooks/API credentials. Use official WhatsApp Business and
Telegram bot/business integrations where applicable; do not use unofficial
WhatsApp session automation or scrape private conversations.
