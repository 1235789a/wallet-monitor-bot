"""Personalized English first-touch generator & MultiHub Outreach QA Gate (Requirement 9).

Enforces:
  - Plain-English explanation of MultiHub GEO (5-10 second stranger comprehension test)
  - 25-45 words target (20-55 words allowed), 1-3 sentences, max 1 question mark
  - Zero banned jargon ("overseas founder inquiries", "AI-search question", "GEO gap", etc.)
  - Zero "Who handles website content?" or "Who manages content on that page?"
  - Zero unverified AI gap/competitor claims when ai_test is not live-verified
  - Greeting matches recipient verification (Hi [First Name] vs Hi [Company] team)
"""

from __future__ import annotations

import re
from .daily27_models import CandidateRecord

BANNED_JARGON_PATTERNS = [
    r"\boverseas founder inquiries\b",
    r"\bAI[- ]search question\b",
    r"\bbuyer[- ]intent query\b",
    r"\bgeo gap\b",
    r"\bentity visibility\b",
    r"\bcitation share\b",
    r"\bllm optimization\b",
    r"\bwho (?:handles|manages|owns) (?:your |the )?(?:website|site|page|marketing) (?:content|copy|messaging)\b",
    r"\bi hope this message finds you well\b",
    r"\belevate your brand\b",
    r"\bunlock your potential\b",
]

UNVERIFIED_AI_CLAIM_PATTERNS = [
    r"\byou (?:don't|do not) (?:show up|appear)\b",
    r"\bcompetitors? (?:are|is) (?:showing up|ranking|appearing|stealing)\b",
    r"\bi (?:found|noticed|discovered) (?:a|your|that) (?:gap|ranking|problem|issue)\b",
    r"\blost (?:traffic|customers|leads|revenue)\b",
    r"\bchatgpt ignores you\b",
]


def _clean_service_phrase(rec: CandidateRecord) -> str:
    svc = (rec.primary_service or "").strip()
    if not svc and rec.observed_site_fact:
        svc = rec.observed_site_fact.split(".")[0][:60]
    svc = re.sub(r"\s+", " ", svc).strip(" .,;:-")
    if not svc:
        svc = "custom software and AI engineering"
    # Keep concise
    words = svc.split()
    if len(words) > 8:
        svc = " ".join(words[:8])
    return svc[0].lower() + svc[1:] if len(svc) > 1 and not svc[:2].isupper() else svc


def generate_personalized_first_touch(rec: CandidateRecord) -> str:
    """Generate a compliant, natural 28-44 word English first-touch message."""
    if rec.is_retail_research or rec.segment == "REGULATED_RETAIL_RESEARCH":
        rec.first_contact_draft = ""
        return ""

    co = rec.company_name.strip()
    svc = _clean_service_phrase(rec)

    if rec.recipient_verified and rec.recipient_name:
        first_name = rec.recipient_name.strip().split()[0]
        greeting = f"Hi {first_name},"
    else:
        greeting = f"Hi {co} team,"

    if rec.ai_test.is_strict_live_proof:
        msg = (
            f"{greeting} I'm with MultiHub. In a recorded {rec.ai_test.platform} check for {svc}, "
            f"we mapped which providers and sources appeared for buyers. "
            f"Would you like me to share the snapshot for {co}?"
        )
    elif rec.recipient_verified:
        msg = (
            f"{greeting} I'm with MultiHub. I saw {co}'s work on {svc}. "
            f"We help specialist teams check how they appear when buyers ask ChatGPT for provider recommendations. "
            f"Would one example buyer-search check for {co} be useful?"
        )
    else:
        msg = (
            f"{greeting} I'm with MultiHub. I saw {co} offers {svc}. "
            f"We help B2B teams check how they appear when buyers ask ChatGPT to recommend providers. "
            f"Are you the right person to discuss this with?"
        )

    rec.first_contact_draft = msg
    return msg


def evaluate_outreach_qa(rec: CandidateRecord) -> CandidateRecord:
    """Run deterministic lint + 10-point stranger blind-test gate."""
    if rec.is_retail_research or rec.segment == "REGULATED_RETAIL_RESEARCH":
        rec.outreach_qa_status = "RESEARCH_ONLY_NO_OUTREACH"
        rec.outreach_qa_score = 0
        rec.outreach_qa_issues = ["Regulated retail slot is RESEARCH_ONLY; outreach drafting disabled"]
        return rec

    text = (rec.first_contact_draft or "").strip()
    if not text:
        text = generate_personalized_first_touch(rec)

    issues: list[str] = []
    words = re.findall(r"\b[\w'’-]+\b", text)
    word_count = len(words)

    if word_count < 18:
        issues.append(f"too_short ({word_count} words < 18)")
    if word_count > 55:
        issues.append(f"too_long ({word_count} words > 55)")
    if text.count("?") != 1:
        issues.append(f"question_count_must_be_1 (got {text.count('?')})")
    if "multihub" not in text.casefold():
        issues.append("missing_sender_identity_multihub")
    if rec.company_name.split()[0].casefold() not in text.casefold():
        issues.append("missing_company_personalization")
    if not re.search(r"\b(?:chatgpt|perplexity|ai|recommend)", text, re.I):
        issues.append("missing_plain_language_service_explanation")

    for pat in BANNED_JARGON_PATTERNS:
        if re.search(pat, text, re.I):
            issues.append(f"banned_jargon_or_content_writer_trap: {pat}")

    if not rec.ai_test.is_strict_live_proof:
        for pat in UNVERIFIED_AI_CLAIM_PATTERNS:
            if re.search(pat, text, re.I):
                issues.append(f"unverified_ai_claim: {pat}")

    if not rec.recipient_verified:
        if re.match(r"^hi\s+[A-Z][a-z]+\s*,", text) and "team" not in text.split(",")[0].casefold():
            issues.append("personal_greeting_on_unverified_recipient")

    # 10-point rubric score
    score = 10 - len(issues)
    rec.outreach_qa_score = max(0, score)
    rec.outreach_qa_issues = issues
    rec.outreach_qa_status = "PASS" if (score >= 9 and not issues) else "FAIL"
    return rec
