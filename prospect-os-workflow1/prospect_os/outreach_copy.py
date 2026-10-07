"""Evidence-gated WhatsApp/Telegram first-message prompts and review.

This module prepares copy only. It never sends messages or performs prospect
research. Semantic judgements are delegated to the reviewer prompt; stable
structural and provenance gates are checked deterministically here.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit

SUPPORTED_LANGUAGES = {"en", "pt-BR", "pt-PT", "es"}
PRELOCK_REVIEW = "PRELOCK_REVIEW"
EVIDENCE_PASS = "EVIDENCE_PASS"

REVIEW_ONLY_CLAIMS = (
    "competitors are more visible", "competitors showed up ahead",
    "you are losing buyers", "losing customers", "i checked your visibility",
    "i found a geo problem", "your competitors are more visible",
    "buyers see your competitors first", "two competitors showed up",
    "descoberta organica", "presenca organica", "concorrentes apareceram antes",
    "concorrentes aparecem antes", "mais visiveis que voces", "mais visiveis que você",
    "encontrei um problema de geo", "seus concorrentes aparecem antes",
    "i tested this search", "we tested this search", "i checked this search",
    "testei essa busca", "testei esta busca", "testamos essa busca",
)
JARGON = (
    "generative engine optimization", "ai search visibility", "visibility distribution",
    "organic discovery", "buyer-query landscape", "discovery signal",
    "landscape de buscas", "distribuicao de visibilidade",
)
RESEARCHER_TONE = (
    "i am analyzing how buyers find", "i'm researching how companies",
    "i am researching how companies", "i am studying organic discovery",
    "estou analisando como compradores encontram",
    "estou pesquisando como empresas", "gostaria de compartilhar uma observacao",
    "observacao objetiva sobre a descoberta",
)
GENERIC_FLATTER = (
    "impressive", "amazing", "love what you're building", "great company",
    "innovative", "exciting", "cutting-edge", "parabens pela empresa",
)
GENERIC_PHRASES = (
    "innovative solutions", "great work", "your services", "your business",
    "solucoes inovadoras", "servicos de qualidade",
)
CUSTOMER_PRETENSE = (
    "i am looking to buy", "i'm looking to buy", "i’m looking to buy",
    "i want to buy from you", "as a customer", "i would like to order",
    "estou procurando comprar", "quero comprar de voces", "quero comprar de você",
    "sou cliente", "como cliente", "quiero comprar", "como cliente",
)
CTA_MARKERS = (
    "want me to", "can i send", "may i send", "would you like",
    "quer que eu", "posso te mandar", "posso enviar", "te mando",
    "quer que eu teste", "te envio",
)
NAME_PLACEHOLDERS = ("[your name]", "[name]", "{{sender_name}}")
MESSAGE_SCORE_WEIGHTS = {
    "grounded": 25,
    "specific": 15,
    "natural": 15,
    "compressed": 10,
    "single_cta": 10,
    "low_friction": 10,
    "not_salesy": 5,
    "plain_language": 5,
    "claim_safe": 5,
}
READY_SCORE = 90
REWRITE_SCORE = 80


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÿ'-]+\b", text, flags=re.UNICODE))


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def language_for(record: dict[str, Any]) -> str:
    explicit = str(record.get("outreach_language") or "").strip()
    if explicit in SUPPORTED_LANGUAGES:
        return explicit
    country = str(record.get("country") or "").casefold()
    if country in {"brazil", "brasil", "br", "pt-br"}:
        return "pt-BR"
    if country in {"portugal", "pt", "pt-pt"}:
        return "pt-PT"
    if country in {"spain", "mexico", "argentina", "colombia", "chile", "peru",
                   "uruguay", "ecuador", "es", "mx", "ar", "co", "cl", "pe"}:
        return "es"
    return "en"


def _direct_route(record: dict[str, Any]) -> tuple[bool, str]:
    channel = str(record.get("channel") or record.get("contact_channel") or "").casefold()
    route = str(record.get("contact_url") or record.get("contact_clickable_url") or "").strip()
    route_kind = str(record.get("route_kind") or record.get("contact_type") or "").casefold()
    if channel == "whatsapp":
        parsed = urlsplit(route)
        host = (parsed.hostname or "").casefold()
        path = parsed.path.casefold().strip("/")
        if host == "wa.me" and path:
            return True, ""
        if host == "api.whatsapp.com" and path.startswith(("send", "message")):
            return True, ""
        if host in {"whatsapp.com", "www.whatsapp.com"} and path.startswith(("send", "message")):
            return True, ""
        return False, "WhatsApp needs an explicit WhatsApp direct URL; a phone number or tel: URL is not enough"
    if channel == "telegram":
        parsed = urlsplit(route)
        host = (parsed.hostname or "").casefold()
        parts = [part.casefold() for part in parsed.path.strip("/").split("/") if part]
        if host != "t.me" or not parts:
            return False, "Telegram needs a direct t.me profile URL"
        if parts[0] in {"s", "c", "m", "joinchat", "addstickers", "share", "iv"} or parts[0].startswith("+"):
            return False, "Telegram group, channel, invite, or share URL is not a direct chat"
        if route_kind not in {"person", "business_account", "founder", "sales"}:
            return False, "Telegram profile must be verified as a direct person/business account, not a group, channel, or bot"
        if record.get("is_bot") is True or record.get("is_group") is True or record.get("is_channel") is True:
            return False, "Telegram bots, groups, and channels are not direct chat routes"
        return True, ""
    return False, "only a verified WhatsApp or direct Telegram route can receive a chat opener"


def _evidence_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = record.get("evidence") or record.get("research_evidence") or []
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("evidence_id") or index)
        result[key] = item
    return result


def build_generation_prompt(record: dict[str, Any]) -> dict[str, Any]:
    """Return an evidence-only prompt context and rules for two internal variants."""
    mode = PRELOCK_REVIEW
    tested = [
        q for q in (record.get("buyer_queries") or record.get("prelock_buyer_queries") or [])
        if isinstance(q, dict) and q.get("tested") is True
    ]
    visibility = [
        e for e in _evidence_map(record).values()
        if str(e.get("category") or e.get("evidence_type") or "").casefold()
        in {"visibility", "competitor", "search_result"}
        and str(e.get("status") or e.get("label") or "").casefold()
        in {"observed", "self_reported", "verified"}
        and e.get("source_url")
        and (e.get("checked_at") or e.get("verified_at"))
    ]
    if record.get("prelock_status") == "PRELOCK_PASS" and tested and visibility:
        mode = EVIDENCE_PASS

    facts = []
    for key, item in _evidence_map(record).items():
        if item.get("source_url") and (item.get("checked_at") or item.get("verified_at")) and str(item.get("status") or item.get("label") or "").casefold() in {
            "observed", "self_reported", "verified"
        }:
            facts.append({
                "evidence_id": key,
                "claim": item.get("claim") or item.get("text") or "",
                "source_url": item.get("source_url"),
                "checked_at": item.get("checked_at") or item.get("verified_at"),
                "evidence_type": item.get("status") or item.get("label") or "unknown",
            })
    context = {
        "company_name": record.get("company_name"),
        "country": record.get("country"),
        "language": language_for(record),
        "vertical": record.get("vertical") or record.get("sampling_vertical") or record.get("industry"),
        "track": record.get("track") or record.get("sampling_track"),
        "prelock_status": record.get("prelock_status") or "PRELOCK_REVIEW",
        "channel": record.get("channel") or record.get("contact_channel"),
        "direct_route": record.get("contact_url") or record.get("contact_clickable_url"),
        "evidence": facts,
        "tested_buyer_queries": tested if mode == EVIDENCE_PASS else [],
        "visibility_evidence": visibility if mode == EVIDENCE_PASS else [],
        "buyer_priority_grade": record.get("buyer_grade"),
        "buyer_priority_score": record.get("buyer_priority_score"),
    }
    return {
        "message_mode": mode,
        "context": context,
        "prompt": (
            "Use only the supplied prospect evidence. Do not research or infer new facts. "
            "Generate two internal WhatsApp/Telegram first-message candidates: "
            "observation-first and buyer-query-first. Select language from context.language. "
            "Keep each to 20–60 words (Portuguese/Spanish may use up to 65), one short "
            "paragraph or two, one CTA that can be answered Yes/Sure/Sim, and a transparent "
            "sender intro with the literal [Your Name] placeholder. Do not explain GEO/SEO, "
            "flatter, create urgency, or claim an untested search result. PRELOCK_REVIEW must "
            "only ask permission to check one real buyer search; omit competitors, buyer query "
            "and visibility-gap claims. EVIDENCE_PASS may state only the supplied tested query "
            "and observed comparison. Review both drafts using the geo-outreach-copy Skill; "
            "rewrite at most twice. Return MESSAGE_REVIEW_REQUIRED if either draft still has "
            "a hard failure. Never send."
        ),
    }


def _overlap_count(fact: str, message: str) -> int:
    tokens = {x.casefold() for x in re.findall(r"[\wÀ-ÿ]+", fact, flags=re.UNICODE) if len(x) >= 4}
    body = {x.casefold() for x in re.findall(r"[\wÀ-ÿ]+", message, flags=re.UNICODE) if len(x) >= 4}
    return len(tokens & body)


def review_candidate(record: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Deterministic checks plus an explicit semantic-review result."""
    message = str(candidate.get("message") or "").strip()
    lowered = _fold(message)
    mode = str(candidate.get("message_mode") or "")
    prelock = str(record.get("prelock_status") or "PRELOCK_REVIEW")
    errors: list[str] = []
    issues: list[str] = []
    evidence = _evidence_map(record)
    direct, route_error = _direct_route(record)
    if not direct:
        errors.append(route_error)
    if mode not in {PRELOCK_REVIEW, EVIDENCE_PASS}:
        errors.append("invalid_message_mode")
    if mode == EVIDENCE_PASS and prelock != "PRELOCK_PASS":
        errors.append("EVIDENCE_PASS requires PRELOCK_PASS")
    if mode == PRELOCK_REVIEW and prelock == "PRELOCK_PASS":
        # Review mode remains allowed if the requested action is still a preflight check.
        pass

    count = word_count(message)
    lang = language_for(record)
    if candidate.get("language") != lang:
        errors.append("message_language_does_not_match_market")
    language_markers = {
        "pt-BR": (" olá", " oi", " vi que", " quer que", " posso", " você", " vocês"),
        "pt-PT": (" olá", " vi que", " quer que", " posso", " vocês", " loja"),
        "es": (" hola", " vi que", " quieres", " puedo", " te envío", " ustedes"),
        "en": (" hi", " hey", " saw that", " want me", " can i", " would you"),
    }
    if not any(_fold(marker) in f" {lowered}" for marker in language_markers[lang]):
        issues.append("message_language_markers_not_observed")
    upper = 65 if lang in {"pt-BR", "pt-PT", "es"} else 60
    if not 20 <= count <= upper:
        errors.append(f"word_count_out_of_range:{count}")
    if message.count("?") != 1:
        errors.append("expected_exactly_one_question_cta")
    cta_text = str(candidate.get("cta") or "").strip()
    if not cta_text or cta_text not in message:
        errors.append("cta_field_must_match_the_single_message_question")
    if lowered.count("[your name]") + lowered.count("[name]") + lowered.count("{{sender_name}}") == 0:
        errors.append("transparent_sender_placeholder_missing")
    if re.search(r"\b(?:i am|i['’]m|my name is|here is|here's|this is|aqui é|aqui e|me chamo|soy|sou)\s+[A-ZÀ-Þ][\wÀ-ÿ'-]+", message):
        errors.append("sender_name_must_remain_a_placeholder")
    if any(_fold(phrase) in lowered for phrase in CUSTOMER_PRETENSE):
        errors.append("message_pretends_to_be_a_customer")
    if any(x in lowered for x in RESEARCHER_TONE):
        issues.append("researcher_tone")
    if any(x in lowered for x in JARGON):
        issues.append("unnecessary_jargon")
    if any(x in lowered for x in GENERIC_FLATTER):
        issues.append("unsupported_flattery")
    if any(x in lowered for x in REVIEW_ONLY_CLAIMS):
        if mode != EVIDENCE_PASS:
            errors.append("review_mode_contains_visibility_or_competitor_claim")
        elif not candidate.get("visibility_evidence_used"):
            errors.append("visibility_claim_without_visibility_evidence")

    fact = str(candidate.get("personalization_fact") or "").strip()
    fact_ids = [str(x) for x in candidate.get("personalization_evidence_ids") or []]
    if not fact or not fact_ids or not all(
        key in evidence
        and evidence[key].get("source_url")
        and (evidence[key].get("checked_at") or evidence[key].get("verified_at"))
        and str(evidence[key].get("status") or evidence[key].get("label") or "").casefold()
        in {"observed", "self_reported", "verified"}
        for key in fact_ids
    ):
        errors.append("personalization_fact_missing_evidence")
    if any(phrase in lowered for phrase in GENERIC_PHRASES):
        issues.append("generic_personalization")

    factual_claims = candidate.get("factual_claims") or []
    if not factual_claims:
        errors.append("factual_claims_need_evidence_links")
    for claim in factual_claims:
        if not isinstance(claim, dict):
            errors.append("invalid_factual_claim_record")
            continue
        refs = [str(x) for x in claim.get("evidence_ids") or []]
        if not refs or any(
            ref not in evidence
            or not evidence[ref].get("source_url")
            or not (evidence[ref].get("checked_at") or evidence[ref].get("verified_at"))
            or str(evidence[ref].get("status") or evidence[ref].get("label") or "").casefold()
            not in {"observed", "self_reported", "verified"}
            for ref in refs
        ):
            errors.append("unsupported_factual_claim")
        kind = str(claim.get("claim_type") or "").casefold()
        if mode == PRELOCK_REVIEW and kind in {"buyer_query", "competitor", "visibility_gap"}:
            errors.append("review_mode_claims_unresearched_buyer_intent")

    tested_queries = [
        q for q in (record.get("buyer_queries") or record.get("prelock_buyer_queries") or [])
        if isinstance(q, dict) and q.get("tested") is True
    ]
    query_used = candidate.get("buyer_query_used")
    if query_used:
        if mode != EVIDENCE_PASS or not any(str(q.get("query") or "") == str(query_used) for q in tested_queries):
            errors.append("buyer_query_not_tested_or_not_allowed")
        elif str(query_used).casefold() not in lowered:
            issues.append("tested_query_not_present_in_message")
    elif mode == EVIDENCE_PASS:
        errors.append("evidence_pass_requires_tested_query")
    if mode == PRELOCK_REVIEW and candidate.get("visibility_evidence_used"):
        errors.append("review_mode_cannot_claim_visibility_evidence")
    if mode == EVIDENCE_PASS:
        visible_items = [
            item for item in evidence.values()
            if str(item.get("category") or item.get("evidence_type") or "").casefold()
            in {"visibility", "competitor", "search_result"}
            and str(item.get("status") or item.get("label") or "").casefold()
            in {"observed", "self_reported", "verified"}
            and item.get("source_url")
            and (item.get("checked_at") or item.get("verified_at"))
        ]
        if not candidate.get("visibility_evidence_used") or not visible_items:
            errors.append("evidence_pass_requires_sourced_visibility_evidence")

    quality = candidate.get("semantic_review") or {}
    semantic_keys = ("grounded", "specific", "natural", "compressed", "single_cta",
                     "low_friction", "not_salesy", "plain_language", "claim_safe")
    missing_semantic = [key for key in semantic_keys if quality.get(key) is not True]
    if quality.get("grounded") is False or quality.get("claim_safe") is False:
        errors.append("semantic_review_rejected_claim_safety")
    if quality.get("single_cta") is False:
        errors.append("semantic_review_found_multiple_ctas")
    if missing_semantic:
        issues.extend(f"semantic_review:{key}" for key in missing_semantic)

    effective_quality = dict(quality)
    if "generic_personalization" in issues:
        effective_quality["specific"] = False
    if "researcher_tone" in issues or "message_language_markers_not_observed" in issues:
        effective_quality["natural"] = False
    if "unnecessary_jargon" in issues:
        effective_quality["plain_language"] = False
    if "unsupported_flattery" in issues:
        effective_quality["not_salesy"] = False
    score = sum(points for key, points in MESSAGE_SCORE_WEIGHTS.items()
                if effective_quality.get(key) is True)
    attempts = int(candidate.get("rewrite_attempts") or 0)
    if attempts > 2:
        errors.append("rewrite_limit_exceeded")
    if errors:
        status = "MESSAGE_REVIEW_REQUIRED"
    elif score >= READY_SCORE:
        status = "PASS"
    elif score >= REWRITE_SCORE and attempts >= 1:
        status = "PASS"
    elif score >= REWRITE_SCORE:
        status = "REWRITE_ONCE"
    else:
        status = "MESSAGE_REVIEW_REQUIRED"
    grounding_errors = [
        issue for issue in errors
        if any(token in issue for token in ("evidence", "claim", "query", "visibility"))
    ]
    return {
        "status": status,
        "score": score,
        "grounded": not grounding_errors,
        "specific": effective_quality.get("specific") is True,
        "natural": effective_quality.get("natural") is True,
        "single_cta": message.count("?") == 1,
        "word_count": count,
        "unsupported_claims": grounding_errors,
        "issues": list(dict.fromkeys(errors + issues)),
        "cta": candidate.get("cta"),
        "personalization_fact": fact,
        "buyer_query_used": query_used if query_used and mode == EVIDENCE_PASS else None,
        "visibility_evidence_used": bool(candidate.get("visibility_evidence_used")),
    }


def review_and_select(record: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep both internal variants for traceability; expose one recommended message."""
    reviewed = []
    for candidate in candidates[:2]:
        score = review_candidate(record, candidate)
        reviewed.append((score, candidate))
    accepted = [(score, candidate) for score, candidate in reviewed if score["status"] == "PASS"]
    outreach = {
        "language": language_for(record),
        "channel": record.get("channel") or record.get("contact_channel"),
        "message_mode": "EVIDENCE_PASS" if record.get("prelock_status") == "PRELOCK_PASS"
                        and any(c.get("message_mode") == EVIDENCE_PASS for c in candidates)
                        else PRELOCK_REVIEW,
        "message_candidates": [
            {**candidate, "message_quality": score} for score, candidate in reviewed
        ],
    }
    if not accepted:
        outreach.update(recommended_first_message=None, cta=None,
                        personalization_fact=None, buyer_query_used=None,
                        visibility_evidence_used=False,
                        message_quality={"status": "MESSAGE_REVIEW_REQUIRED",
                                         "score": max((s["score"] for s, _ in reviewed), default=0),
                                         "issues": [issue for s, _ in reviewed for issue in s["issues"]]})
        return {"company_name": record.get("company_name"), "outreach": outreach}
    score, winner = max(accepted, key=lambda pair: pair[0]["score"])
    outreach.update(
        message_mode=winner.get("message_mode"),
        recommended_first_message=winner.get("message"),
        cta=winner.get("cta"),
        personalization_fact=winner.get("personalization_fact"),
        buyer_query_used=score["buyer_query_used"],
        visibility_evidence_used=score["visibility_evidence_used"],
        message_quality=score,
    )
    return {"company_name": record.get("company_name"), "outreach": outreach}


def validate_legacy_first_message(item: dict[str, Any], message: str) -> tuple[list[str], dict[str, Any]]:
    """Compatibility checks for workflow1_daily's existing first_message field."""
    errors: list[str] = []
    issues: list[str] = []
    lower = _fold(message)
    count = word_count(message)
    if not any(x in lower for x in ("[your name]", "[name]", "{{sender_name}}")):
        errors.append("first message needs the [Your Name] sender placeholder")
    if re.search(r"\b(?:i am|i['’]m|my name is|here is|here's|this is|aqui é|aqui e|me chamo|soy|sou)\s+[A-ZÀ-Þ][\wÀ-ÿ'-]+", message):
        errors.append("sender name must remain a placeholder")
    if any(_fold(phrase) in lower for phrase in CUSTOMER_PRETENSE):
        errors.append("message pretends to be a customer")
    if not 20 <= count <= 60:
        errors.append(f"first message has {count} words, expected 20-60")
    if message.count("?") != 1:
        errors.append("first message must contain exactly one CTA question")
    lang = language_for(item)
    language_markers = {
        "pt-BR": (" olá", " oi", " vi que", " quer que", " posso", " você", " vocês"),
        "pt-PT": (" olá", " vi que", " quer que", " posso", " vocês", " loja"),
        "es": (" hola", " vi que", " quieres", " puedo", " te envío", " ustedes"),
        "en": (" hi", " hey", " saw that", " want me", " can i", " would you"),
    }
    if not any(_fold(marker) in f" {lower}" for marker in language_markers[lang]):
        errors.append(f"first message language does not match prospect market ({lang})")
    if any(x in lower for x in REVIEW_ONLY_CLAIMS):
        errors.append("first message makes an unsupported visibility/competitor claim")
    if any(x in lower for x in JARGON):
        issues.append("first message uses unnecessary GEO/search jargon")
    if any(x in lower for x in RESEARCHER_TONE):
        issues.append("first message uses abstract researcher phrasing")
    if any(x in lower for x in GENERIC_FLATTER):
        issues.append("first message uses unsupported flattery")
    if any(x in lower for x in ("our service", "our website", "pricing", "price",
                                "book a call", "schedule a call", "partnership opportunity")):
        issues.append("first message moves into pitch, pricing, or meeting request")
    name = str(item.get("company_name") or "").casefold()
    hook = str(item.get("personalization_hook") or "")
    if name not in lower and _overlap_count(hook, message) < 2:
        errors.append("first message needs a specific, evidence-backed business fact")
    if any(x in lower for x in ("http://", "https://", "www.", " usdt", " aeo ", " llm ")):
        errors.append("first message jumps ahead of the reply-first sequence")
    state = str(item.get("prelock_status") or "PRELOCK_REVIEW")
    if any(x in lower for x in REVIEW_ONLY_CLAIMS):
        if state != "PRELOCK_PASS":
            errors.append("PRELOCK_REVIEW message contains a PASS-only visibility claim")
        else:
            queries = [q for q in item.get("buyer_queries", [])
                       if isinstance(q, dict) and q.get("tested") is True]
            query = str(item.get("buyer_query_used") or "")
            visible = any(
                str(ev.get("category") or ev.get("evidence_type") or "").casefold()
                in {"visibility", "competitor", "buyer_query", "search_result"}
                and ev.get("source_url")
                and str(ev.get("status") or ev.get("label") or "").casefold()
                in {"observed", "self_reported", "verified"}
                for ev in item.get("research_evidence", []) if isinstance(ev, dict)
            )
            if not query or query not in {str(q.get("query") or "") for q in queries} or not visible:
                errors.append("PASS-only visibility claim lacks a tested query or sourced comparison")
    if "contact_channel" in item:
        route_record = {
            "channel": item.get("contact_channel"),
            "contact_url": item.get("contact_clickable_url"),
            "route_kind": item.get("contact_type"),
            "is_bot": item.get("is_bot"),
            "is_group": item.get("is_group"),
            "is_channel": item.get("is_channel"),
        }
        route_ok, route_issue = _direct_route(route_record)
        if not route_ok:
            errors.append(route_issue)
    specific = name in lower or _overlap_count(hook, message) >= 2
    natural = not any(x in lower for x in (*RESEARCHER_TONE, *JARGON))
    single_cta = message.count("?") == 1
    low_friction = any(_fold(marker) in lower for marker in CTA_MARKERS)
    # Keep the score weights aligned with the new candidate reviewer.
    legacy_quality = {
        "grounded": not bool(errors),
        "specific": specific,
        "natural": natural,
        "compressed": count <= 45,
        "single_cta": single_cta,
        "low_friction": low_friction,
        "not_salesy": not any(x in lower for x in ("pricing", "price", "book a call", "schedule a call")),
        "plain_language": not any(x in lower for x in JARGON),
        "claim_safe": not bool(errors),
    }
    score = sum(points for key, points in MESSAGE_SCORE_WEIGHTS.items() if legacy_quality[key])
    status = "MESSAGE_REVIEW_REQUIRED" if errors or score < REWRITE_SCORE else "PASS" if score >= READY_SCORE else "REWRITE_ONCE"
    quality = {
        "status": status,
        "score": score,
        "grounded": not bool(errors),
        "specific": specific,
        "natural": natural,
        "single_cta": single_cta,
        "compressed": count <= 45,
        "low_friction": low_friction,
        "not_salesy": legacy_quality["not_salesy"],
        "plain_language": legacy_quality["plain_language"],
        "claim_safe": not bool(errors),
        "word_count": count,
        "unsupported_claims": list(errors),
        "issues": list(issues),
    }
    return errors, quality
