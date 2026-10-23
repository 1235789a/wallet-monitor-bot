# FB prospect customer-card / CSV contract

Each business one row, one stable entity. Prefer these columns:

`company,website,country,industry,source_url,checked_at,decision_maker,decision_role,role_evidence_url,facebook_page_url,facebook_person_url,fb_route_evidence_url,fb_route_status,history_status,match_source,lead_track,icp_score,buyer_task,buying_trigger,purchase_fit_evidence,outreach_mode,draft_message,next_step,status`

`fb_route_status`: `BUSINESS_CONTACT_CONFIRMED`, `FB_PAGE_ONLY`, `PERSON_PROFILE_UNVERIFIED`, `DM_AVAILABILITY_UNKNOWN`, `CONTACT_RESTRICTED`, `DECLINED`, `UNKNOWN`.

`history_status`: `HISTORY_CONTACTED_EXCLUDE`, `PRIOR_BATCH_REVIEW`, `DUPLICATE_REVIEW`, `NO_HISTORY_MATCH_FOUND`, `NOT_CHECKED`.

`status`: `RAW`, `HOLD`, `READY_FOR_HUMAN_REVIEW`, `USER_MARKED_SENT`, `REPLIED`, `TEST_PERMISSIONED`, `EVIDENCE_DELIVERED`, `QUOTED`, `PAID`, `DECLINED`.

`lead_track`: `DIRECT`, `PARTNER` or `RESEARCH_ONLY`.

READY requires current business evidence, an appropriate verified recipient and route, no history conflict, a specific purchasing rationale, industry research for a custom hook, and an approved honest draft. Score cannot override any hard gate. NO_HISTORY_MATCH_FOUND alone is *not* READY.

Every factual detail in the message must be backed by a cited URL or stored evidence id. No fabricated AI search results. Never assign `USER_MARKED_SENT` or `PAID` from imported claims without actual user/source confirmation.

If any dataset was unavailable, report which histories/timestamps were covered and mark other duplicates unverified. This schema is a target for the agent's outputs, not a claim that existing software implements every field.
