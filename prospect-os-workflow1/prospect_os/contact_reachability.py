"""Human reachability is evidence separate from the existence of a chat link."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .source_pool import public_http_url

HUMAN_DIRECT = "human_direct"
HUMAN_TRANSFER = "human_transfer"
AUTOMATED_WELCOME = "automated_welcome"
BOT_ONLY = "bot_only"
UNKNOWN = "unknown"
REACHABLE_STATES = {HUMAN_DIRECT, HUMAN_TRANSFER}
STATES = REACHABLE_STATES | {AUTOMATED_WELCOME, BOT_ONLY, UNKNOWN}


def route_identity(url: str) -> tuple[str, str]:
    """Different click-to-chat templates for one account are still one route."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = parsed.path.strip("/")
    if host == "wa.me" and path.casefold().startswith("message/"):
        return "whatsapp", "message:" + path.split("/", 1)[1].casefold()
    if host in {"wa.me", "api.whatsapp.com", "web.whatsapp.com", "whatsapp.com"}:
        number = path if host == "wa.me" else (parse_qs(parsed.query).get("phone") or [""])[0]
        return "whatsapp", re.sub(r"\D", "", number)
    if host in {"t.me", "telegram.me"}:
        return "telegram", path.casefold()
    return host, url.casefold()


def published_outreach_route(anchor: str, url: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Route purpose is distinct from activity and whether a human answers."""
    # Use this link's label and prefilled text only, never a site's product copy.
    label = anchor + " " + " ".join(parse_qs(urlsplit(url).query).get("text", []))
    rules = (
        ("demo_bot", r"\b(?:try|test|demo)\b.{0,30}\b(?:bot|ai|assistant)\b|\b(?:bot|ai|assistant)\b.{0,20}\bdemo\b"),
        ("customer_service", r"\b(?:customer service|customer support|support|after.sales|order tracking|refunds?|returns?|reservations?|bookings?|suporte|pedidos|encomendas|soporte|reservas|kundendienst)\b"),
        ("decision_maker", r"\b(?:founder|co-founder|owner|ceo|marketing director|head of marketing|growth lead|propriet[aá]rio|fundador|due[nñ]o|gerente|inhaber)\b"),
        ("partnerships", r"\b(?:partnerships?|business development|parcerias?|alianzas?|合作|商务)\b"),
        ("sales", r"\b(?:sales|comercial|commercial|ventas|vendas|wholesale|or[cç]amento|quote)\b"),
    )
    purpose = next((purpose for purpose, pattern in rules if re.search(pattern, label, re.I)), UNKNOWN)
    return {"purpose": purpose, "evidence": ({**evidence, "label": "self_reported",
            "route": url, "claim": f"Official contact label/prefill: {label[:240]}"}
            if purpose != UNKNOWN else None)}


def outreach_route(contact: dict[str, Any], website: str) -> dict[str, str]:
    """Fail closed: a service desk or an unlabeled WA is not a sales-ready lead."""
    assessment = contact.get("outreach_route") or {}
    assessment = assessment if isinstance(assessment, dict) else {}
    purpose = assessment.get("purpose", UNKNOWN)
    proof = assessment.get("evidence") or {}
    # Reuse the existing provenance validator, including exact-route reply checks.
    verified = {**contact, "human_reachability": {"state": HUMAN_DIRECT, "evidence": proof}}
    if reachability(verified, website) != HUMAN_DIRECT:
        purpose = UNKNOWN
    human = reachability(contact, website)
    if contact.get("outreach_route_conflict") is True:
        return {"purpose": UNKNOWN, "status": "review", "reason": "conflicting_route_purposes"}
    if human == BOT_ONLY or purpose in {"demo_bot", "customer_service"}:
        return {"purpose": purpose, "status": "blocked", "reason": "bot_or_customer_service_route"}
    if purpose not in {"decision_maker", "partnerships"}:
        return {"purpose": purpose, "status": "review", "reason": "business_recipient_not_verified"}
    if human not in REACHABLE_STATES:
        return {"purpose": purpose, "status": "review", "reason": "human_reachability_not_verified"}
    return {"purpose": purpose, "status": "ready", "reason": "official_business_route_with_human_evidence"}


def merge_contact_route(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Retain better route evidence; incompatible uses require review."""
    merged = dict(existing)
    left = (existing.get("outreach_route") or {}).get("purpose", UNKNOWN)
    right = (incoming.get("outreach_route") or {}).get("purpose", UNKNOWN)
    if incoming.get("outreach_route_conflict") is True or (left != UNKNOWN and right != UNKNOWN and left != right):
        merged["outreach_route_conflict"] = True
    if left == UNKNOWN and right != UNKNOWN:
        merged["outreach_route"] = incoming["outreach_route"]
    old_human = (existing.get("human_reachability") or {}).get("state", UNKNOWN)
    new_human = (incoming.get("human_reachability") or {}).get("state", UNKNOWN)
    if old_human == UNKNOWN and new_human != UNKNOWN:
        merged["human_reachability"] = incoming["human_reachability"]
    if BOT_ONLY in {old_human, new_human}:
        merged["human_reachability"] = (incoming if new_human == BOT_ONLY else existing)["human_reachability"]
    return merged


def published_reachability(anchor: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Classify only the label attached to this route; generic labels prove nothing."""
    rules = (
        (HUMAN_TRANSFER, r"transfer.*(?:human|agent)|(?:human|live agent).*transfer|falar com (?:um )?atendente|hablar con (?:un )?agente"),
        (BOT_ONLY, r"bot[- ]only|automated (?:support|chat|menu)|chatbot|menu (?:bot|autom[aá]tico)|somente bot"),
        (AUTOMATED_WELCOME, r"auto(?:mated|matic)? (?:welcome|greeting)|mensagem autom[aá]tica|bienvenida autom[aá]tica"),
        (HUMAN_DIRECT, r"(?:chat|message|contact|whatsapp|talk|speak)\b.{0,40}\b(?:founder|owner|ceo|human|live agent)\b"),
    )
    state = next((state for state, pattern in rules if re.search(pattern, anchor, re.I)), UNKNOWN)
    return {"state": state, "evidence": ({**evidence, "label": "self_reported",
            "claim": f"Official route label: {anchor[:240]}"} if state != UNKNOWN else None)}


def reachability(contact: dict[str, Any], website: str) -> str:
    """Positive reachability needs dated evidence attributable to this exact route."""
    assessment = contact.get("human_reachability") or {}
    if not isinstance(assessment, dict):
        return UNKNOWN
    state = assessment.get("state", UNKNOWN)
    evidence = assessment.get("evidence") or {}
    if state not in STATES or not isinstance(evidence, dict):
        return UNKNOWN
    source = str(evidence.get("source_url") or evidence.get("url") or "")
    if not (public_http_url(source) and evidence.get("checked_at") and evidence.get("claim")
            and evidence.get("label") in {"observed", "self_reported"}):
        return UNKNOWN
    if evidence.get("route") and route_identity(str(evidence["route"])) != route_identity(str(contact.get("value") or "")):
        return UNKNOWN
    try:
        datetime.fromisoformat(str(evidence["checked_at"]).replace("Z", "+00:00"))
    except ValueError:
        return UNKNOWN
    # Owned reply exports may reference an externally hosted evidence artifact;
    # they must identify the exact route and carry an explicit human review.
    same_site = (urlsplit(source).hostname or "").casefold().removeprefix("www.") == (
        urlsplit(str(website)).hostname or "").casefold().removeprefix("www.")
    reviewed_reply = (evidence.get("kind") == "owned_reply_export"
                      and evidence.get("reviewed") is True
                      and evidence.get("route") == contact.get("value"))
    if evidence.get("kind") == "owned_reply_export" and not reviewed_reply:
        return UNKNOWN
    return state if same_site or reviewed_reply else UNKNOWN


def route_summary(row: dict[str, Any], usable) -> dict[str, Any]:
    contacts = row.get("contacts") or []
    states = {}
    channels = []
    outreach_channels = []
    assessments = []
    for channel in ("whatsapp", "telegram"):
        routes = [c for c in contacts if usable(c, channel, row.get("website_url"))]
        values = [reachability(c, str(row.get("website_url") or "")) for c in routes]
        order = (HUMAN_DIRECT, HUMAN_TRANSFER, AUTOMATED_WELCOME, UNKNOWN, BOT_ONLY)
        states[channel] = next((state for state in order if state in values), UNKNOWN)
        if any(state in REACHABLE_STATES for state in values):
            channels.append(channel)
        for contact in routes:
            assessment = outreach_route(contact, str(row.get("website_url") or ""))
            assessments.append({"channel": channel, "value": contact.get("value"), **assessment})
        if any(item["channel"] == channel and item["status"] == "ready" for item in assessments):
            outreach_channels.append(channel)
    def decision_confirmed(contact):
        proof = contact.get("decision_maker_evidence") or {}
        if not isinstance(proof, dict) or not proof.get("name") or not proof.get("role"):
            return False
        verified = {**contact, "human_reachability": {"state": HUMAN_DIRECT, "evidence": proof}}
        return (contact.get("contact_belongs_to_decision_maker") is True
                and reachability(contact, str(row.get("website_url") or "")) == HUMAN_DIRECT
                and reachability(verified, str(row.get("website_url") or "")) == HUMAN_DIRECT)
    return {"contact_reachability": states, "reachable_contact_channels": channels,
            "outreach_contact_channels": outreach_channels, "outreach_route_assessments": assessments,
            "decision_maker_reachability_confirmed": any(
                decision_confirmed(c)
                for c in contacts if c.get("channel") in channels)}


def select_outreach_route(row: dict[str, Any], channel: str) -> dict[str, str]:
    """Export the qualified route, never the first footer link in its channel."""
    from .contact_pools import _usable_contact
    ready = [c for c in row.get("contacts", []) if _usable_contact(c, channel, row.get("website_url"))
             and outreach_route(c, str(row.get("website_url") or ""))["status"] == "ready"]
    if not ready:
        return {}
    ready.sort(key=lambda c: ((c.get("outreach_route") or {}).get("purpose") != "decision_maker",
                              str(c.get("value") or "")))
    return {"selected_contact_value": ready[0]["value"],
            "selected_contact_source_url": ready[0]["evidence"]["source_url"]}
