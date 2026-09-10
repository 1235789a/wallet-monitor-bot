"""Conservative intent evidence adapters for the local-business prospect track.

The external projects used with this module are collectors, not truth machines:

* Agent-Reach supplies public activity/reply evidence;
* Chatwoot supplies actual conversation events when an official channel is
  connected;
* Mautic and PostHog supply owned-site/email behaviour;
* n8n transports events between systems;
* the existing wallet monitor supplies actual payment evidence.

This module never sends a message, infers a reply from a contact button, or
turns a crypto signal into payment intent.  Scores are ranking aids.  Ground
truth is an observed direct reply or an observed payment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable


DIRECT_REPLY_EVENTS = {
    "direct_reply",
    "meaningful_reply",
    "asked_details",
    "asked_price",
    "trial_requested",
    "not_interested",
}

REPLY_WEIGHTS = {
    "public_activity_recent": 12,
    "public_reply": 18,
    "contact_route_opened": 5,
    "message_delivered": 5,
    "message_read": 10,
    "direct_reply": 30,
    "meaningful_reply": 12,
    "asked_details": 15,
    "asked_price": 22,
    "trial_requested": 22,
    "sent_no_response": -5,
    "read_no_response": -10,
    "not_interested": -35,
}

PURCHASE_WEIGHTS = {
    "public_crypto_signal": 4,
    "usdt_signal": 8,
    "preview_page_view": 5,
    "pricing_page_view": 15,
    "repeat_page_view": 10,
    "form_submitted": 18,
    "demo_requested": 24,
    "asked_details": 8,
    "asked_price": 20,
    "trial_requested": 24,
    "payment_method_asked": 28,
    "checkout_started": 22,
    "invoice_created": 32,
    "paid": 100,
    "not_interested": -40,
}


@dataclass(frozen=True)
class IntentEvent:
    """A normalized observation from one permitted source."""

    event_type: str
    source: str
    occurred_at: str = ""
    company_key: str = ""
    evidence_url: str = ""
    metadata: dict[str, Any] | None = None


def _clean(value: Any) -> str:
    return str(value or "").strip().casefold()


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _event(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    *,
    evidence_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> IntentEvent:
    return IntentEvent(
        event_type=_clean(event_type),
        source=_clean(source) or "manual",
        occurred_at=str(_first(payload, "occurred_at", "timestamp", "created_at", "date")),
        company_key=str(_first(payload, "company_key", "company", "contact_id", "contactId")),
        evidence_url=evidence_url or str(_first(payload, "evidence_url", "url", "source_url")),
        metadata=metadata or {},
    )


def normalize_event(raw: dict[str, Any], source: str = "generic") -> IntentEvent:
    """Normalize the generic event contract used by n8n and manual imports."""
    if not isinstance(raw, dict):
        raise ValueError("event must be an object")
    metadata = _as_mapping(raw.get("metadata") or raw.get("properties"))
    event_type = _first(raw, "event_type", "type", "event", "name")
    return _event(str(event_type), source, raw, metadata=metadata)


def normalize_external_event(source: str, payload: dict[str, Any]) -> list[IntentEvent]:
    """Map conservative subsets of external webhook/report payloads.

    Unknown events are dropped instead of being guessed.  Each adapter accepts
    a small stable subset so upgrades in the external applications cannot turn
    arbitrary text into a positive commercial signal.
    """
    source_name = _clean(source)
    if not isinstance(payload, dict):
        return []

    if source_name in {"agent_reach", "agent-reach"}:
        raw_type = _clean(_first(payload, "event_type", "type", "status", "label"))
        mapping = {
            "activity": "public_activity_recent",
            "public_activity": "public_activity_recent",
            "recent_activity": "public_activity_recent",
            "public_reply": "public_reply",
            "reply": "public_reply",
            "comment_reply": "public_reply",
        }
        event_type = mapping.get(raw_type)
        return [_event(event_type, "agent_reach", payload)] if event_type else []

    if source_name == "chatwoot":
        # Chatwoot webhooks distinguish incoming/outgoing message types.
        # Only incoming messages count as a direct reply from the prospect.
        raw_event = _clean(_first(payload, "event", "event_type", "type"))
        message = _as_mapping(payload.get("message"))
        message_type = _clean(_first(message, "message_type") or _first(payload, "message_type"))
        if raw_event in {"message_created", "message.updated", "message_created_v2"}:
            if message_type in {"incoming", "contact", "received"}:
                event_type = "direct_reply"
            elif message_type in {"outgoing", "agent", "sent"}:
                event_type = "message_sent"
            else:
                return []
            return [_event(event_type, "chatwoot", payload, metadata={"message_type": message_type})]
        if raw_event in {"conversation_created", "conversation.created"} and message_type in {"incoming", "contact"}:
            return [_event("direct_reply", "chatwoot", payload)]
        return []

    if source_name == "mautic":
        raw_event = _clean(_first(payload, "event", "event_type", "type", "name"))
        mapping = {
            "email.open": "email_opened",
            "email_open": "email_opened",
            "email.click": "email_clicked",
            "email_click": "email_clicked",
            "email.reply": "direct_reply",
            "email_reply": "direct_reply",
            "page.visit": "preview_page_view",
            "pricing_page_view": "pricing_page_view",
            "form.submit": "form_submitted",
            "form_submitted": "form_submitted",
        }
        event_type = mapping.get(raw_event)
        return [_event(event_type, "mautic", payload)] if event_type else []

    if source_name == "posthog":
        raw_event = _clean(_first(payload, "event", "event_type", "name"))
        mapping = {
            "preview_page_view": "preview_page_view",
            "pricing_page_view": "pricing_page_view",
            "repeat_page_view": "repeat_page_view",
            "demo_requested": "demo_requested",
            "payment_method_asked": "payment_method_asked",
            "checkout_started": "checkout_started",
            "invoice_created": "invoice_created",
            "paid": "paid",
        }
        event_type = mapping.get(raw_event)
        return [_event(event_type, "posthog", payload)] if event_type else []

    # n8n is intentionally a transport layer.  Its payload is accepted only
    # when it already uses the explicit generic event contract.
    if source_name in {"n8n", "generic", "manual"}:
        event = normalize_event(payload, source_name)
        known = set(REPLY_WEIGHTS) | set(PURCHASE_WEIGHTS) | {"message_sent"}
        return [event] if event.event_type in known else []

    return []


def _unique_event_types(events: Iterable[IntentEvent]) -> set[str]:
    return {event.event_type for event in events}


def _evidence(event: IntentEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "source": event.source,
        "occurred_at": event.occurred_at,
        "evidence_url": event.evidence_url,
        "metadata": event.metadata or {},
    }


def _score(events: Iterable[IntentEvent], weights: dict[str, int]) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    evidence: list[dict[str, Any]] = []
    seen_singletons: set[str] = set()
    for event in events:
        weight = weights.get(event.event_type)
        if weight is None:
            continue
        # Repeated page views are useful, but repeated webhook delivery must
        # not inflate the score indefinitely.  Count each event type once.
        if event.event_type in seen_singletons:
            continue
        seen_singletons.add(event.event_type)
        total += weight
        evidence.append({**_evidence(event), "weight": weight})
    return max(0, min(100, total)), evidence


def _reply_state(event_types: set[str]) -> str:
    if "not_interested" in event_types:
        return "not_interested"
    if "paid" in event_types or "invoice_created" in event_types:
        return "commercial_signal"
    if "asked_price" in event_types or "trial_requested" in event_types:
        return "commercial_reply"
    if "asked_details" in event_types or "meaningful_reply" in event_types or "direct_reply" in event_types:
        return "direct_replied"
    if "read_no_response" in event_types:
        return "read_no_response"
    if "sent_no_response" in event_types:
        return "sent_no_response"
    if "public_reply" in event_types:
        return "publicly_active_only"
    if "contact_route_opened" in event_types:
        return "contact_open_only"
    return "not_tested"


def _purchase_state(event_types: set[str]) -> str:
    if "paid" in event_types:
        return "paid"
    if "invoice_created" in event_types or "payment_method_asked" in event_types:
        return "payment_qualified"
    if {"asked_price", "checkout_started", "trial_requested", "demo_requested"} & event_types:
        return "commercial_interest"
    if {"pricing_page_view", "form_submitted", "repeat_page_view"} & event_types:
        return "engaged"
    if {"preview_page_view", "public_crypto_signal", "usdt_signal"} & event_types:
        return "weak_signal"
    return "unknown"


def score_events(events: Iterable[IntentEvent]) -> dict[str, Any]:
    """Return separate reply and purchase scores with explicit limitations."""
    materialized = list(events)
    event_types = _unique_event_types(materialized)
    reply_score, reply_evidence = _score(materialized, REPLY_WEIGHTS)
    purchase_score, purchase_evidence = _score(materialized, PURCHASE_WEIGHTS)

    has_direct_reply = bool(event_types & DIRECT_REPLY_EVENTS)
    has_payment = "paid" in event_types
    warnings: list[str] = []
    if not has_direct_reply:
        reply_score = min(reply_score, 45)
        warnings.append("没有真实直接回复；回复分数只是公开行为/联系方式代理指标")
    if not has_payment:
        warnings.append("没有真实付款；消费分数只是访问、问价、试用或付款流程代理指标")
    if "public_crypto_signal" in event_types and "usdt_signal" not in event_types:
        warnings.append("Bitcoin/XBT/Lightning 不是 USDT 接受证明")

    return {
        "reply_willingness_score": reply_score,
        "reply_state": _reply_state(event_types),
        "reply_ground_truth": "observed_direct_reply" if has_direct_reply else "not_observed",
        "purchase_intent_score": 100 if has_payment else purchase_score,
        "purchase_state": _purchase_state(event_types),
        "purchase_ground_truth": "observed_payment" if has_payment else "not_observed",
        "event_types": sorted(event_types),
        "reply_evidence": reply_evidence,
        "purchase_evidence": purchase_evidence,
        "warnings": warnings,
    }


def events_from_payloads(payloads: Iterable[dict[str, Any]], source: str = "generic") -> list[IntentEvent]:
    """Normalize a batch of webhook/report payloads without network access."""
    events: list[IntentEvent] = []
    for payload in payloads:
        events.extend(normalize_external_event(source, payload))
    return events


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
