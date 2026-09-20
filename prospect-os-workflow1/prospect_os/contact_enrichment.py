"""Conservative contact enrichment for an already discovered company pool.

Only the supplied company website is crawled.  An explicit WhatsApp/Telegram
link is recorded as a route, but never promoted to owner access.  Plain phone
numbers remain phone numbers.  Generic inboxes remain gatekeeper routes.
"""

from __future__ import annotations

import html
import re
import ssl
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .source_pool import USER_AGENT, canonical_domain, public_http_url


GENERIC_EMAIL_LOCALS = {
    "admin", "business", "contact", "customerservice", "hello", "help", "info",
    "inquiries", "marketing", "office", "orders", "reception", "sales", "service",
    "support", "team",
}
PRIORITY_PATH_TERMS = (
    "contact", "about", "team", "founder", "owner", "leadership", "management",
)
SOCIAL_HOSTS = {
    "linkedin.com": "linkedin", "facebook.com": "facebook",
    "instagram.com": "instagram", "x.com": "x", "twitter.com": "x",
}
ROLE_PATTERN = re.compile(
    r"\b(founder|co-founder|owner|ceo|chief executive officer|head of marketing|marketing director|growth lead)\b",
    re.I,
)
EMAIL_PATTERN = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)


class ContactPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._href = ""
        self._anchor_text: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self._hidden += 1
        if tag == "a":
            self._href = str(dict(attrs).get("href") or "").strip()
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append({"href": self._href, "text": " ".join(self._anchor_text).strip()})
            self._href = ""
            self._anchor_text = []
        if tag in {"script", "style", "svg", "noscript"} and self._hidden:
            self._hidden -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden:
            return
        cleaned = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self._href:
            self._anchor_text.append(cleaned)


def _checked_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _host(url: str) -> str:
    return canonical_domain(url)


def _clean_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, ""))


def _evidence(claim: str, source_url: str) -> dict[str, Any]:
    return {
        "label": "observed",
        "claim": claim,
        "source_url": source_url,
        "checked_at": _checked_at(),
    }


def classify_email(address: str) -> str:
    local = address.split("@", 1)[0].casefold().replace("-", "").replace("_", "")
    if local in GENERIC_EMAIL_LOCALS or any(local.startswith(item) for item in GENERIC_EMAIL_LOCALS):
        return "GENERIC_BUSINESS"
    return "NAMED_EMPLOYEE"


def _email_contact(address: str, source_url: str) -> dict[str, Any]:
    address = address.strip().strip(".,;:()[]<>").casefold()
    email_type = classify_email(address)
    return {
        "channel": "email",
        "value": address,
        "email_type": email_type,
        "route_type": "generic_business" if email_type == "GENERIC_BUSINESS" else "named_employee",
        "generic_business_contact": email_type == "GENERIC_BUSINESS",
        "contact_belongs_to_decision_maker": False,
        "decision_access_confidence": "unknown",
        "evidence": _evidence("Email address is published on the supplied company website.", source_url),
    }


def _whatsapp_value(url: str) -> str:
    parsed = urlsplit(url)
    if _host(url) == "wa.me":
        return re.sub(r"\D", "", parsed.path)
    query = parse_qs(parsed.query)
    return re.sub(r"\D", "", (query.get("phone") or [""])[0])


def _route_contact(channel: str, url: str, source_url: str, anchor_text: str) -> dict[str, Any]:
    role_hint = ROLE_PATTERN.search(anchor_text or "")
    value = _clean_url(url)
    route_type = "business_chat" if channel == "whatsapp" else "unknown"
    if channel == "telegram":
        path = urlsplit(url).path.strip("/")
        if path.startswith(("joinchat/", "+", "s/")):
            route_type = "group_or_channel"
        elif path.casefold().endswith("bot"):
            route_type = "bot"
    return {
        "channel": channel,
        "value": value,
        "route_type": route_type,
        "generic_business_contact": True,
        "contact_belongs_to_decision_maker": False,
        "decision_access_confidence": "unknown",
        "role_hint": role_hint.group(1).casefold() if role_hint else "",
        "evidence": _evidence(
            f"Explicit {channel.title()} link is published on the supplied company website; ownership of the account is unverified.",
            source_url,
        ),
    }


def extract_contacts(page_url: str, page_html: str) -> dict[str, Any]:
    parser = ContactPageParser()
    parser.feed(page_html)
    page_text = " ".join(parser.text_parts)
    contacts: list[dict[str, Any]] = []
    internal_links: list[str] = []
    origin = _host(page_url)

    for address in EMAIL_PATTERN.findall(page_text):
        contacts.append(_email_contact(address, page_url))

    for link in parser.links:
        raw_href = link["href"].strip()
        absolute = urljoin(page_url, raw_href)
        lowered = raw_href.casefold()
        if lowered.startswith("mailto:"):
            address = unquote(raw_href[7:].split("?", 1)[0])
            if EMAIL_PATTERN.fullmatch(address):
                contacts.append(_email_contact(address, page_url))
            continue
        if lowered.startswith("tel:"):
            contacts.append({
                "channel": "phone",
                "value": unquote(raw_href[4:].split("?", 1)[0]),
                "route_type": "phone_only",
                "generic_business_contact": True,
                "contact_belongs_to_decision_maker": False,
                "decision_access_confidence": "unknown",
                "evidence": _evidence("Telephone link is published; WhatsApp is not inferred.", page_url),
            })
            continue
        host = _host(absolute)
        if host in {"wa.me", "api.whatsapp.com", "web.whatsapp.com", "whatsapp.com"}:
            item = _route_contact("whatsapp", absolute, page_url, link["text"])
            item["phone_hint"] = _whatsapp_value(absolute)
            contacts.append(item)
        elif host in {"t.me", "telegram.me"}:
            contacts.append(_route_contact("telegram", absolute, page_url, link["text"]))
        elif host in SOCIAL_HOSTS:
            contacts.append({
                "channel": "social",
                "platform": SOCIAL_HOSTS[host],
                "value": _clean_url(absolute),
                "route_type": "business_social",
                "generic_business_contact": True,
                "contact_belongs_to_decision_maker": False,
                "decision_access_confidence": "unknown",
                "evidence": _evidence("Social profile is linked from the supplied company website.", page_url),
            })
        elif host == origin and public_http_url(absolute):
            internal_links.append(_clean_url(absolute))

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for contact in contacts:
        key = (str(contact.get("channel")), str(contact.get("value")).casefold().rstrip("/"))
        unique.setdefault(key, contact)
    return {
        "contacts": list(unique.values()),
        "internal_links": list(dict.fromkeys(internal_links)),
        "decision_role_terms_observed": sorted({match.group(1).casefold() for match in ROLE_PATTERN.finditer(page_text)}),
    }


def fetch_html(url: str, timeout: int = 15, max_bytes: int = 1_500_000) -> tuple[str, str]:
    if not public_http_url(url):
        raise ValueError("website URL must be a public HTTP(S) URL")
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        content_type = response.headers.get_content_type() if response.headers else ""
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"unsupported content type: {content_type}")
        body = response.read(max_bytes)
        charset = response.headers.get_content_charset() if response.headers else None
        return body.decode(charset or "utf-8", errors="replace"), response.geturl()


def robots_allows(url: str, timeout: int = 10) -> bool:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        request = Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            parser.parse(response.read().decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        # A missing/unreachable robots file is not interpreted as a prohibition.
        return True


def enrich_record(
    record: dict[str, Any],
    *,
    max_pages: int = 5,
    delay_seconds: float = 0.5,
    respect_robots: bool = True,
    fetcher: Callable[[str], tuple[str, str]] = fetch_html,
) -> dict[str, Any]:
    result = dict(record)
    website = str(record.get("website_url") or "").strip()
    result.update({
        "contacts": [],
        "decision_maker_candidates": [],
        "contact_enrichment_status": "not_run",
        "contact_enrichment_errors": [],
        "pages_checked": [],
    })
    if not public_http_url(website):
        result["contact_enrichment_status"] = "no_public_website_hint"
        return result
    if respect_robots and not robots_allows(website):
        result["contact_enrichment_status"] = "robots_disallowed"
        return result

    queue = [website]
    seen: set[str] = set()
    contacts: dict[tuple[str, str], dict[str, Any]] = {}
    role_evidence: list[dict[str, Any]] = []
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen or _host(url) != _host(website):
            continue
        seen.add(url)
        try:
            body, final_url = fetcher(url)
            parsed = extract_contacts(final_url, body)
            result["pages_checked"].append(final_url)
            for contact in parsed["contacts"]:
                key = (str(contact.get("channel")), str(contact.get("value")).casefold().rstrip("/"))
                contacts.setdefault(key, contact)
            if parsed["decision_role_terms_observed"]:
                role_evidence.append({
                    "roles": parsed["decision_role_terms_observed"],
                    "source_url": final_url,
                    "status": "role_terms_only_name_and_route_unresolved",
                })
            candidates = sorted(
                (link for link in parsed["internal_links"] if any(term in urlsplit(link).path.casefold() for term in PRIORITY_PATH_TERMS)),
                key=lambda link: (0 if "contact" in link.casefold() else 1, len(link)),
            )
            for link in candidates:
                if link not in seen and link not in queue:
                    queue.append(link)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
            result["contact_enrichment_errors"].append({"url": url, "error": str(exc)})
        if queue and delay_seconds:
            time.sleep(delay_seconds)

    result["contacts"] = list(contacts.values())
    result["decision_maker_candidates"] = role_evidence
    result["contact_enrichment_status"] = "completed" if result["pages_checked"] else "fetch_failed"
    result["contact_enriched_at"] = _checked_at()
    result["decision_maker_identified"] = False
    result["direct_decision_maker_route"] = False
    result["decision_access_confidence"] = "unknown"
    return result


def enrich_records(records: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return [enrich_record(record, **kwargs) for record in records]
