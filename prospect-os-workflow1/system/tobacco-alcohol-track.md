# Lawful Tobacco/Alcohol Track

This track is isolated from the Web3-only daily runner. It is for lawful adult
tobacco and alcohol businesses with a physical location. It must not be used to
find or promote illegal drugs, cannabis, gambling, adult services, weapons,
money laundering, or age-restricted activity outside lawful adult retail and
hospitality.

## Non-negotiable order

`structured source pool -> identity/deduplication -> small-business gate -> official business/entity verification -> recent activity -> official contact -> crypto/USDT evidence -> public reply behaviour -> human reply test`

Google, Bing, SEO result pages, and AI-search answers are removed from the
discovery stage. If a candidate was first found through one of those channels,
the code quarantines it. A website or social page may only verify a name that
already exists in the structured source pool.

## Required record fields

Every record must preserve:

- `discovery_channel`, `discovery_source_url`, `discovery_source_note`;
- `company_name`, `website_url`, `official_business_type`;
- `business_type_verified`, `physical_location_verified`;
- `business_type_source_url`, `physical_location_source_url`;
- `ownership_model`, `location_count`, `chain_status`;
- `ownership_location_evidence_url` and matching `ownership_locations` evidence;
- `recent_activity_verified`, `recent_activity_at`, `recent_activity_source_url`;
- `contact_channel`, `contact_url`, `contact_verification`, `contact_source_url`;
- `payment_signal_type`, `usdt_status`, `usdt_source_url`, and payment evidence;
- `reply_behavior_status` and public reply evidence;
- `direct_reply_status`, which is recorded only after a human sends a message;
- `payment_intent_status`, which stays `unknown` until a real commercial signal;
- evidence entries with `observed`, `self_reported`, `inferred`, or `unknown` labels.

## Statuses

- `QUARANTINED`: forbidden discovery route, high-risk category, chain/franchise,
  more than two locations, or another hard contradiction.
- `REVIEW_REQUIRED`: potentially useful but a required fact is missing or only
  inferred. It must not be sent.
- `READY_FOR_REPLY_TEST`: business, physical entity, independent size, current
  activity, official contact route, and observable public reply behaviour are
  evidenced. A human may send one personalized test message; the module never
  sends it.

`READY_FOR_REPLY_TEST` does not mean the business accepts USDT, will reply to a
stranger, or will pay. Those are separate later states.

Public replies and direct replies are separate facts. A shop replying to a
customer comment is evidence that its public account is monitored; it is not
evidence that it replied to our message. Use `record_reply_test` after a human
operator sends a permitted, personalized test message.

## Payment wording

`XBT`, Bitcoin, and Lightning are not USDT proof. They are stored as a
`crypto_signal` and the first human message must ask whether USDT is accepted.
Only an explicit official USDT/Tether/Tron statement or a direct confirmation
may set `usdt_status=verified`.

## Quotas

The requested number is a ceiling, never a target that lowers evidence quality.
If ten records are requested and only three pass, the output is three plus a
shortfall of seven. Review and quarantine records remain visible for later
verification and are never silently substituted.
