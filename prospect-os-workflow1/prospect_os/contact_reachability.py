"""Human reachability is evidence separate from the existence of a chat link."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from .source_pool import public_http_url

HUMAN_DIRECT = "human_direct"
HUMAN_TRANSFER = "human_transfer"
AUTOMATED_WELCOME = "automated_welcome"
BOT_ONLY = "bot_only"
UNKNOWN = "unknown"
REACHABLE_STATES = {HUMAN_DIRECT, HUMAN_TRANSFER}
STATES = REACHABLE_STATES | {AUTOMATED_WELCOME, BOT_ONLY, UNKNOWN}


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
    return state if same_site or reviewed_reply else UNKNOWN


def route_summary(row: dict[str, Any], usable) -> dict[str, Any]:
    contacts = row.get("contacts") or []
    states = {}
    channels = []
    for channel in ("whatsapp", "telegram"):
        routes = [c for c in contacts if usable(c, channel, row.get("website_url"))]
        values = [reachability(c, str(row.get("website_url") or "")) for c in routes]
        order = (HUMAN_DIRECT, HUMAN_TRANSFER, AUTOMATED_WELCOME, UNKNOWN, BOT_ONLY)
        states[channel] = next((state for state in order if state in values), UNKNOWN)
        if any(state in REACHABLE_STATES for state in values):
            channels.append(channel)
    def decision_confirmed(contact):
        proof = contact.get("decision_maker_evidence") or {}
        if not isinstance(proof, dict) or not proof.get("name") or not proof.get("role"):
            return False
        verified = {**contact, "human_reachability": {"state": HUMAN_DIRECT, "evidence": proof}}
        return (contact.get("contact_belongs_to_decision_maker") is True
                and reachability(contact, str(row.get("website_url") or "")) == HUMAN_DIRECT
                and reachability(verified, str(row.get("website_url") or "")) == HUMAN_DIRECT)
    return {"contact_reachability": states, "reachable_contact_channels": channels,
            "decision_maker_reachability_confirmed": any(
                decision_confirmed(c)
                for c in contacts if c.get("channel") in channels)}
