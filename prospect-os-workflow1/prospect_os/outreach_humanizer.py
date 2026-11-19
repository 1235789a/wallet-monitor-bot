"""High-signal outreach lint and conversation-stage guidance. Drafts only."""
from __future__ import annotations

import re

HUMANIZER_PROMPT = (
    " Apply the vendored Humanizer v4.0 skill (.codex/skills/humanizer/SKILL.md) "
    "and system/conversation-copy-policy.md. Read the actual skill at agent time. "
    "Write like one person texting another: concrete service, everyday words, no "
    "research-report framing, filler, flattery, invented findings or sales jargon. "
    "Read the draft aloud, rewrite anything templated, check the facts again. "
    "Return an idiomatic Chinese translation in chinese_translation, separate from "
    "the exact message to send. Never add Chinese to the prospect-facing message."
)

_PATTERNS = {
    "abstract_buyer_search": r"\bbuyer[- ]search check\b|\bbuyer[- ]query landscape\b",
    "research_report_pitch": r"\bgeo study card\b|\bi(?:'m| am) researching how\b|\bi prepared a short geo\b",
    "sales_cliche": r"\b(?:unlock your potential|elevate your brand|game[- ]changer|take your business to the next level|i hope this message finds you well)\b",
    "generic_opportunity": r"\b(?:ai visibility opportunity|leverage ai to drive|enhance your online presence)\b",
}
_PERMISSION = r"\b(?:would you like me to (?:share|send)|can i (?:share|send)|may i (?:share|send)|want me to (?:share|send)|shall i (?:share|send))\b"
_UNVERIFIED = r"\b(?:i (?:found|noticed|discovered) (?:a|your) (?:gap|ranking problem)|you (?:don't|do not) (?:show up|appear)|competitors? (?:rank|show up|appear) ahead|i (?:checked|tested|ran) (?:chatgpt|perplexity|the search|a search))\b"
_ATTACHED = r"\b(?:i(?:'ve| have) attached|attached (?:is|are)|see (?:the )?attachment|here(?:'s| is) the (?:screenshot|file|report))\b"
STAGES = {"first_touch", "permission_received", "sample_delivery", "followup",
          "quote_requested", "public_comment", "opt_out"}


def humanizer_issues(message: str) -> list[str]:
    """High-precision hard flags; passing is not proof of naturalness."""
    text = message.casefold().replace("’", "'")
    return [f"humanizer:{name}" for name, pattern in _PATTERNS.items()
            if re.search(pattern, text)]


def build_conversation_prompt(*, channel: str, stage: str, last_customer_message: str,
                              facts: list, evidence_ready: bool = False,
                              attachment_attached: bool = False) -> dict:
    if stage not in STAGES:
        raise ValueError("unknown conversation stage")
    return {
        "context": dict(channel=channel, stage=stage, last_customer_message=last_customer_message,
                        facts=facts, evidence_ready=evidence_ready,
                        attachment_attached=attachment_attached),
        "prompt": (
            "Use the real conversation stage and reply directly to the last message. "
            "First touch: one low-friction question. Permission received: deliver what "
            "was requested, no second permission request. If evidence is not ready, say "
            "so accurately; don't claim results. Sample delivery: explain one real finding "
            "in plain language. Followup: add one relevant fact, not a bump; no pressure. "
            "Public comment: answer the actual post; no unsolicited sales pitch. "
            "Quote requested: clarify scope or give verified terms only. Opt out: stop. "
            "For warm chat, zero or one question is fine. Never pretend an attachment "
            "was sent. Keep facts linked to supplied sources. Draft only, never send."
            + HUMANIZER_PROMPT
        ),
    }


def review_conversation_copy(message: str, *, stage: str,
                             evidence_ready: bool = False,
                             attachment_attached: bool = False) -> list[str]:
    """Return blockers for stage-aware drafts, before human semantic review."""
    if stage not in STAGES:
        raise ValueError("unknown conversation stage")
    text = message.casefold().replace("’", "'")
    issues = humanizer_issues(message)
    if stage == "opt_out":
        issues.append("conversation:stop_outreach")
    if not message.strip():
        issues.append("conversation:empty_draft")
    if len(message.split()) > (50 if stage == "public_comment" else 70):
        issues.append("conversation:too_long")
    if message.count("?") > 1 or (stage == "first_touch" and message.count("?") != 1):
        issues.append("conversation:question_count")
    if stage in {"permission_received", "sample_delivery"} and re.search(_PERMISSION, text):
        issues.append("conversation:permission_already_granted")
    if not evidence_ready and re.search(_UNVERIFIED, text):
        issues.append("conversation:unverified_result")
    if not attachment_attached and re.search(_ATTACHED, text):
        issues.append("conversation:attachment_not_attached")
    return issues
