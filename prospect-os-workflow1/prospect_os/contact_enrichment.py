"""Conservative contact enrichment for an already discovered company pool.

Only the supplied company website is crawled. Explicit WhatsApp/Telegram links
are recorded as routes, never owner access. Only explicitly WhatsApp-labelled
international numbers may generate a candidate link; ordinary phones stay phone.
"""

from __future__ import annotations

import html
import re
import ssl
import time
from datetime import UTC, datetime
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .source_pool import USER_AGENT, canonical_domain, public_http_url
from .contact_reachability import (merge_contact_route, outreach_route, published_outreach_route,
                                   published_reachability, route_identity)


GENERIC_EMAIL_LOCALS = {
    "admin", "business", "contact", "customerservice", "hello", "help", "info",
    "inquiries", "marketing", "office", "orders", "reception", "sales", "service",
    "support", "team",
}
PRIORITY_PATH_TERMS = (
    "contact", "about", "team", "founder", "owner", "leadership", "management",
    "customer", "support", "booking", "reservation", "store", "shop", "location",
    "sales", "contact-us", "contactus", "contactos", "contactanos", "contáctanos",
    "contato", "contacto", "fale-conosco", "faleconosco", "atendimento", "pedidos",
    "encomendas", "loja", "lojas", "suporte", "orcamento", "orçamento", "whatsapp",
    "quem-somos", "sobre", "nosotros", "quienes-somos", "tienda",
    "kontakt", "impressum", "contate-nos",
)
CONTACT_PATH_TERMS = (
    "contact", "contact-us", "contactus", "contacto", "contactos", "contactanos",
    "contáctanos", "contato", "fale-conosco", "faleconosco", "atendimento",
    "support", "sales", "partnership", "business-development", "quote", "suporte", "pedidos", "encomendas", "orçamento",
    "orcamento", "whatsapp", "kontakt", "impressum", "contate-nos",
)
CONTACT_ANCHOR_TERMS = (
    "contact", "contact-us", "contacto", "contactos", "contactanos", "contáctanos",
    "contato", "fale conosco", "fale-conosco", "faleconosco", "atendimento",
    "support", "sales", "partnership", "business development", "quote", "suporte", "pedidos", "encomendas", "orçamento",
    "orcamento", "whatsapp", "about", "team", "founder", "owner", "store", "shop",
    "quem somos", "quem-somos", "sobre", "nosotros", "quienes somos",
    "quienes-somos", "tienda",
)
DIRECT_TG_ANCHOR = re.compile(
    r"\b(chat|message|contact|direct|dm|fale|contato|atendimento|parcerias?|commercial|sales)\b",
    re.I,
)
TG_GROUP_ANCHOR = re.compile(r"\b(news|channel|community|group|join|feed|updates|canal|grupo)\b", re.I)
CONTACT_ONLY_ANCHOR = re.compile(
    r"\b(?:contact(?:s|os|o|anos|us)?|contáctanos|contate|contato|kontakt|impressum|"
    r"support|sales|suporte|atendimento|whatsapp|fale[ -]?conosco|pedidos|encomendas|"
    r"orçamento|orcamento)\b", re.I,
)
EXPLICIT_CHAT_URL = re.compile(
    r"https?://(?:wa\.me|api\.whatsapp\.com|web\.whatsapp\.com|whatsapp\.com|t\.me|telegram\.me)/[^\s\"'<>\\]+",
    re.I,
)
WA_LABELLED_NUMBER = re.compile(r"\b(?:phone\s*/\s*)?whatsapp\s*(?:number|phone|tel\.?|号码)?\s*[:：]?\s*(\+\d[\d .()\-]{6,23}\d)", re.I)
WA_WIDGET_NUMBER = re.compile(r'''\bdata-whatsapp-(?:number|phone)\s*=\s*["'](\+\d[\d .()\-]{6,23}\d)["']''', re.I)
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
            values = dict(attrs)
            self._href = str(values.get("href") or "").strip()
            self._anchor_text = [str(values.get("aria-label") or ""),
                                 str(values.get("title") or "")]

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
        path = urlsplit(url).path.strip("/").casefold()
        if (path.startswith(("joinchat/", "+", "s/", "c/", "share/", "addlist/"))
                or path.casefold() == "share" or TG_GROUP_ANCHOR.search(anchor_text or "")):
            route_type = "group_or_channel"
        elif path.casefold().endswith("bot"):
            route_type = "bot"
        elif DIRECT_TG_ANCHOR.search(anchor_text or ""):
            route_type = "direct_chat"
        else:
            # A bare t.me username can identify a group/channel or user.
            # Keep it out of the direct-chat pool until the official site's
            # surrounding label makes the intended route clear.
            route_type = "unverified_telegram_route"
    evidence = _evidence(
        f"Explicit {channel.title()} link is published on the supplied company website; ownership of the account is unverified.",
        source_url,
    )
    return {
        "channel": channel,
        "value": value,
        "route_type": route_type,
        "generic_business_contact": True,
        "contact_belongs_to_decision_maker": False,
        "decision_access_confidence": "unknown",
        "role_hint": role_hint.group(1).casefold() if role_hint else "",
        "evidence": evidence,
        "human_reachability": published_reachability(anchor_text, evidence),
        "outreach_route": published_outreach_route(anchor_text, value, evidence),
        "route_label": anchor_text,
    }


def whatsapp_labelled_route(number: str, page_url: str, label: str) -> dict[str, Any] | None:
    """Normalize only an explicitly labelled international business number.

    A valid E.164 phone number is not proof of a registered WhatsApp account,
    human ownership or marketing permission. Fail closed without the dependency.
    """
    try:
        import phonenumbers
    except ImportError:
        return None
    try:
        parsed = phonenumbers.parse(number, None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        digits = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164).lstrip("+")
    except (phonenumbers.NumberParseException, ValueError):
        return None
    item = _route_contact("whatsapp", f"https://wa.me/{digits}", page_url, label)
    item["phone_hint"] = digits
    item["route_verification_status"] = "OFFICIAL_LABEL_NUMBER_GENERATED_UNVERIFIED"
    item["evidence"] = _evidence(f"Official website explicitly labels number {number} as WhatsApp; link generated, account unverified.", page_url)
    return item


def extract_contacts(page_url: str, page_html: str) -> dict[str, Any]:
    parser = ContactPageParser()
    parser.feed(page_html)
    page_text = " ".join(parser.text_parts)
    contacts: list[dict[str, Any]] = []
    internal_links: list[str] = []
    internal_link_anchors: list[dict[str, str]] = []
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
            if re.search(r"\bwhatsapp\b", link["text"], re.I):
                labelled = whatsapp_labelled_route(unquote(raw_href[4:].split("?", 1)[0]), page_url, link["text"])
                if labelled:
                    contacts.append(labelled)
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
            clean = _clean_url(absolute)
            internal_links.append(clean)
            internal_link_anchors.append({"url": clean, "text": link["text"]})

    # Some official sites keep click-to-chat URLs in inline widgets rather than
    # ordinary anchors. Record only explicit WhatsApp/Telegram URLs present in
    # the supplied page; never infer a route from a phone number.
    for match in EXPLICIT_CHAT_URL.findall(html.unescape(page_html)):
        absolute = match.rstrip(".,;:!?)]}")
        host = _host(absolute)
        channel = "whatsapp" if host in {"wa.me", "api.whatsapp.com", "web.whatsapp.com", "whatsapp.com"} else "telegram"
        item = _route_contact(channel, absolute, page_url, "embedded official-site link")
        if channel == "whatsapp":
            item["phone_hint"] = _whatsapp_value(absolute)
        contacts.append(item)

    # Keep labelled phone candidates distinct from an actually published URL.
    for regex, source, label in ((WA_LABELLED_NUMBER, page_text, "WhatsApp labelled number"),
                                  (WA_WIDGET_NUMBER, page_html, "WhatsApp widget number")):
        for number in regex.findall(source):
            item = whatsapp_labelled_route(number, page_url, label)
            if item:
                contacts.append(item)

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for contact in contacts:
        key = route_identity(str(contact.get("value"))) if contact.get("channel") in {"whatsapp", "telegram"} else (str(contact.get("channel")), str(contact.get("value")).casefold().rstrip("/"))
        unique[key] = merge_contact_route(unique[key], contact) if key in unique else contact
    return {
        "contacts": list(unique.values()),
        "text": page_text[:12_000],
        "internal_links": list(dict.fromkeys(internal_links)),
        "internal_link_anchors": internal_link_anchors,
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


@lru_cache(maxsize=2048)
def _robots_parser(scheme: str, netloc: str, timeout: int) -> RobotFileParser | None:
    robots_url = urlunsplit((scheme, netloc, "/robots.txt", "", ""))
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        request = Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            parser.parse(response.read().decode("utf-8", errors="replace").splitlines())
        return parser
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        # A missing/unreachable robots file is not interpreted as a prohibition.
        return None


def robots_allows(url: str, timeout: int = 10) -> bool:
    parsed = urlsplit(url)
    parser = _robots_parser(parsed.scheme, parsed.netloc, timeout)
    return True if parser is None else parser.can_fetch(USER_AGENT, url)


def _is_explicit_direct_chat(contact: dict[str, Any]) -> bool:
    """Cheap early-stop check; never upgrades a phone or ambiguous TG URL."""
    channel = contact.get("channel")
    url = str(contact.get("value") or "")
    host = _host(url)
    path = urlsplit(url).path.strip("/").casefold()
    if channel == "whatsapp" and host in {
        "wa.me", "api.whatsapp.com", "web.whatsapp.com", "whatsapp.com",
    }:
        if contact.get("route_verification_status") == "OFFICIAL_LABEL_NUMBER_GENERATED_UNVERIFIED":
            return False
        digits = _whatsapp_value(url)
        if host == "wa.me" and path.casefold().startswith("message/"):
            return len(path.split("/", 1)[1]) >= 6
        return 7 <= len(digits) <= 15
    if channel == "telegram" and host in {"t.me", "telegram.me"}:
        return (contact.get("route_type") == "direct_chat" and bool(path)
                and not path.startswith(("joinchat/", "+", "s/", "c/", "share/", "addlist/"))
                and not path.casefold().endswith("bot"))
    return False


def enrich_record(
    record: dict[str, Any],
    *,
    max_pages: int = 5,
    delay_seconds: float = 0.5,
    respect_robots: bool = True,
    robots_timeout: int = 10,
    fetcher: Callable[[str], tuple[str, str]] = fetch_html,
    render_fetcher: Callable[[str], tuple[str, str, list[str]]] | None = None,
    max_render_pages: int = 2,
) -> dict[str, Any]:
    result = dict(record)
    website = str(record.get("website_url") or "").strip()
    result.update({
        "contacts": [],
        "decision_maker_candidates": [],
        "contact_enrichment_status": "not_run",
        "contact_enrichment_errors": [],
        "pages_checked": [],
        "page_evidence": [],
    })
    if not public_http_url(website):
        result["contact_enrichment_status"] = "no_public_website_hint"
        return result
    queue = [website]
    seen: set[str] = set()
    contacts: dict[tuple[str, str], dict[str, Any]] = {}
    role_evidence: list[dict[str, Any]] = []
    rendered_pages = 0
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen or _host(url) != _host(website):
            continue
        if respect_robots and not robots_allows(url, timeout=robots_timeout):
            result["contact_enrichment_errors"].append({"url": url, "error": "robots_disallowed"})
            continue
        seen.add(url)
        try:
            body, final_url = fetcher(url)
            if _host(final_url) != _host(website):
                result["contact_enrichment_errors"].append({
                    "url": url, "error": "redirected_outside_company_domain",
                })
                continue
            parsed = extract_contacts(final_url, body)
            if render_fetcher and rendered_pages < max_render_pages and not any(
                    c.get("channel") == "whatsapp" and _is_explicit_direct_chat(c)
                    and not c.get("route_verification_status") for c in parsed["contacts"]):
                rendered_pages += 1
                try:
                    rendered_html, rendered_url, qr_urls = render_fetcher(final_url)
                    if _host(rendered_url) == _host(website):
                        rendered = extract_contacts(rendered_url, rendered_html)
                        for item in rendered["contacts"]:
                            if item.get("channel") == "whatsapp":
                                item["route_evidence_kind"] = "RENDERED_PUBLIC_DOM"
                        parsed["contacts"].extend(rendered["contacts"])
                        parsed["internal_links"].extend(rendered["internal_links"])
                        parsed["internal_link_anchors"].extend(rendered["internal_link_anchors"])
                        for qr_url in qr_urls:
                            if _host(qr_url) in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
                                item = _route_contact("whatsapp", qr_url, rendered_url, "Official WhatsApp QR code")
                                item["route_evidence_kind"] = "PUBLIC_QR_CODE_DECODED"
                                parsed["contacts"].append(item)
                    else:
                        result["contact_enrichment_errors"].append({"url": url, "error": "render_redirected_outside_company_domain"})
                except RuntimeError as exc:
                    result["contact_enrichment_errors"].append({"url": url, "error": str(exc)})
            result["pages_checked"].append(final_url)
            result["page_evidence"].append({"url": final_url, "text": parsed["text"],
                "internal_links": parsed["internal_links"][:50], "contacts": parsed["contacts"],
                "checked_at": _checked_at(), "status": "ok"})
            for contact in parsed["contacts"]:
                key = route_identity(str(contact.get("value"))) if contact.get("channel") in {"whatsapp", "telegram"} else (str(contact.get("channel")), str(contact.get("value")).casefold().rstrip("/"))
                contacts[key] = merge_contact_route(contacts[key], contact) if key in contacts else contact
            if parsed["decision_role_terms_observed"]:
                role_evidence.append({
                    "roles": parsed["decision_role_terms_observed"],
                    "source_url": final_url,
                    "status": "role_terms_only_name_and_route_unresolved",
                })
            anchor_by_link: dict[str, str] = {}
            for item in parsed.get("internal_link_anchors", []):
                anchor_by_link.setdefault(item["url"], item.get("text", ""))

            def page_priority(link: str) -> tuple[int, int, int]:
                path = unquote(urlsplit(link).path).casefold()
                anchor = anchor_by_link.get(link, "").casefold()
                contact_path = any(term in path for term in CONTACT_PATH_TERMS)
                contact_anchor = bool(CONTACT_ONLY_ANCHOR.search(anchor))
                useful_path = any(term in path for term in PRIORITY_PATH_TERMS)
                useful_anchor = any(term in anchor for term in CONTACT_ANCHOR_TERMS)
                return (0 if contact_path or contact_anchor else 1,
                        0 if useful_path or useful_anchor else 1, len(link))

            candidates = sorted(
                (link for link in parsed["internal_links"]
                 if any(term in unquote(urlsplit(link).path).casefold() for term in PRIORITY_PATH_TERMS)
                 or any(term in anchor_by_link.get(link, "").casefold() for term in CONTACT_ANCHOR_TERMS)),
                key=page_priority,
            )
            for link in candidates:
                if link not in seen and link not in queue:
                    queue.append(link)
            # Some small business sites omit their contact page from the home
            # navigation. Try common local slugs only after discovered links.
            for slug in ("contact", "contato", "contacto", "fale-conosco",
                         "faleconosco", "atendimento", "sales", "partnership", "get-a-quote", "whatsapp", "support"):
                guessed = _clean_url(urljoin(website.rstrip("/") + "/", slug))
                if guessed not in seen and guessed not in queue:
                    queue.append(guessed)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
            result["contact_enrichment_errors"].append({"url": url, "error": str(exc)})
        # A footer/service WA does not end the search for a business recipient.
        # Probe one contact page, still bounded; don't deep-crawl a weak route.
        has_chat = any(_is_explicit_direct_chat(contact) for contact in contacts.values())
        has_business_route = any(_is_explicit_direct_chat(contact)
                                 and outreach_route(contact, website)["status"] == "ready"
                                 for contact in contacts.values())
        if has_business_route or (has_chat and len(seen) >= min(2, max_pages)):
            break
        if queue and delay_seconds:
            time.sleep(delay_seconds)

    result["contacts"] = list(contacts.values())
    result["contact_page_attempts"] = len(seen)
    result["decision_maker_candidates"] = role_evidence
    result["contact_enrichment_status"] = "completed" if result["pages_checked"] else "fetch_failed"
    result["contact_enriched_at"] = _checked_at()
    result["decision_maker_identified"] = False
    result["direct_decision_maker_route"] = False
    result["decision_access_confidence"] = "unknown"
    return result


def enrich_records(records: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return [enrich_record(record, **kwargs) for record in records]
