"""Low-cost ICP qualification, GEO/SEO partner separation, and WA/TG/FB route verification.

Executes BEFORE expensive image generation (Requirement 4, 5, 6, 7, 11).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .cross_channel_dedupe import normalize_fb_handle, normalize_tg_handle, normalize_wa_phone
from .daily27_models import CandidateRecord
from .website_resolution import extract_domain, is_search_engine

# Known GEO / SEO / AI Search Visibility / Marketing Agency peers to separate as PARTNER_CANDIDATE
KNOWN_GEO_SEO_PARTNER_DOMAINS = {
    "ozturksoft.net": "Homepage explicitly lists SEO & GEO optimisation for AI search",
    "tankdev.tech": "Explicitly markets GEO / AI search visibility service",
    "detartech.com": "Explicitly offers GEO services and describes client GEO work",
    "brotherhoodio.com": "Directory/site explicitly offers AI visibility / GEO services",
    "hatsontech.com": "Discusses own in-house GEO / AI search visibility optimization",
    "brightnode.io": "Offers Web3 marketing & growth agency services alongside tokenomics",
    "bwa.com.tr": "Offers corporate SEO and digital marketing agency services",
    "zordo.net": "Web/SEO/digital marketing agency; partner track rather than direct buyer",
    "oneskai.com": "Search, SEO, AEO & GEO AI visibility agency",
    "fracasdigital.com": "Web3 marketing/growth studio; partner track",
    "crayn.ai": "Sub-brand of Creodive digital agency; explicitly markets ChatGPT/Perplexity technical SEO",
    "dygentic.com": "Founded by SEO/AEO practitioner building marketing agency systems",
    "excellentpresence.com": "Web strategy and SEO consultancy",
    "aiversnelt.nl": "Offers AI-marketing for ChatGPT and Google visibility",
}

GEO_SEO_PEER_PATTERN = re.compile(
    r"\b(?:generative engine optimization|answer engine optimization|"
    r"geo optimization|ai search visibility service|seo agency|digital marketing agency)\b",
    re.I,
)

# Known verified human/founder Telegram handles vs public broadcast/company handles
VERIFIED_HUMAN_TG_HANDLES = {
    "talfao": ("Talfao (Founder/Lead)", "CODESPECT"),
    "realjohnnytime": ("Jonathan Shahak (Founder)", "Ginger Security / JohnnyTime"),
    "sasha_fracas": ("Sasha (Business Lead)", "Fracas Web3 Studio"),
    "castle_chain": ("Frank (Founder)", "Frank Castle Audits"),
    "fancb_dfk": ("DFK Direct Contact", "DFK Digital Solutions"),
}

UNVERIFIED_PUBLIC_CORP_TG_HANDLES = {
    "redduckua",
    "datarootlabs",
    "softean",
    "bitronix_official",
}

# Known verified founder WhatsApp routes from official site inspection
VERIFIED_FOUNDER_WA_DOMAINS = {
    "mt7.io": ("Abdul Adnan", "Founder (explicitly labeled on mt7.io contact modal)"),
    "reiiel.com": ("Rishabh Agravat", "Solo Founder/Operator (reiiel.com/about)"),
}

# Known oversized companies (>50 employees) from website/directory evidence
OVERSIZED_DOMAINS = {
    "kudostechnolabs.com": "Official about page states 50+ team",
    "softean.com": "LinkedIn/directory lists 51-200 / 50-249 employees",
    "techupr.com": "About timeline states growing past 100 employees",
    "xebia.com": "Large global consultancy (>1,000 employees)",
    "sngular.com": "Large enterprise consultancy (>500 employees)",
    "codete.com": "Mid-large software company (>100 employees)",
    "banvien.com": "Mid-large enterprise vendor (>100 employees)",
    "lemon.io": "Large talent marketplace platform",
    "bitgo.com": "Large institutional crypto custodian",
    "innoplexus.com": "Large enterprise AI company (>200 employees)",
    "staqo.com": "Enterprise IT division (>50 employees)",
}


def parse_size_range(size_str: str) -> tuple[int | None, int | None]:
    if not size_str:
        return None, None
    s = str(size_str).strip()
    m = re.search(r"(\d[\d,]*)\s*[-–to]+\s*(\d[\d,]*)", s)
    if m:
        low = int(m.group(1).replace(",", ""))
        high = int(m.group(2).replace(",", ""))
        return low, high
    m_plus = re.search(r"(\d[\d,]*)\s*\+", s)
    if m_plus:
        low = int(m_plus.group(1).replace(",", ""))
        return low, 99999
    if s.isdigit():
        val = int(s)
        return val, val
    return None, None


def verify_off_search_discovery(rec: CandidateRecord) -> bool:
    """Requirement 1: Must originate from an independent directory/source, not search keywords."""
    ch = (rec.discovery_channel or "").strip().lower()
    if ch in {"google", "bing", "search_engine", "seo_results", "ai_search"}:
        rec.hold_or_reject_reasons.append(f"Disallowed discovery channel: {ch}")
        return False
    src_url = (rec.discovery_source_url or "").strip()
    if not src_url or not src_url.startswith("https://"):
        rec.hold_or_reject_reasons.append("Missing or non-HTTPS independent discovery_source_url")
        return False
    if is_search_engine(src_url):
        rec.hold_or_reject_reasons.append(f"Discovery URL is a search engine: {src_url}")
        return False
    src_dom = extract_domain(src_url)
    off_dom = extract_domain(rec.official_url or rec.canonical_domain)
    if not off_dom:
        rec.hold_or_reject_reasons.append("Missing official website domain")
        return False
    if src_dom == off_dom:
        rec.hold_or_reject_reasons.append(f"Discovery source domain ({src_dom}) is same as official domain")
        return False
    return True


def verify_icp_and_segment(rec: CandidateRecord) -> bool:
    """Requirement 4 & 11: Evaluate size (2-20 preferred, <=50 max), independence, regulated retail, and GEO/SEO peers."""
    dom = rec.canonical_domain or extract_domain(rec.official_url)
    rec.canonical_domain = dom

    # 1. Regulated retail experiment track (Requirement 11)
    if rec.retail_category in {"wine", "vape", "adult"} or rec.segment.startswith("REGULATED_RETAIL"):
        rec.segment = "REGULATED_RETAIL_RESEARCH"
        rec.is_retail_research = True
        rec.auto_send_enabled = False
        rec.send_ready = False
        rec.stage = "RESEARCH_ONLY"
        if dom == "scandals.love":
            rec.location_count = 3
            rec.hold_or_reject_reasons.append("RESEARCH_ONLY: Adult retail experiment; 3 Merseyside outlets & site unavailable in browser")
        else:
            rec.hold_or_reject_reasons.append(f"RESEARCH_ONLY: Regulated retail ({rec.retail_category}) requires legal/compliance & human route review; excluded from sendable quota")
        return False

    # 2. GEO / SEO peer separation (Requirement 4)
    if dom in KNOWN_GEO_SEO_PARTNER_DOMAINS or GEO_SEO_PEER_PATTERN.search(rec.observed_site_fact or ""):
        reason = KNOWN_GEO_SEO_PARTNER_DOMAINS.get(dom, "Offers SEO/GEO/AI visibility services")
        rec.segment = "PARTNER_CANDIDATE"
        rec.allocated_slot = "PARTNER_POOL"
        rec.stage = "PARTNER_SEPARATED"
        rec.hold_or_reject_reasons.append(f"PARTNER_CANDIDATE (excluded from standard buyer seats): {reason}")
        return False

    # 3. Company headcount check (2-20 preferred, max 50)
    if dom in OVERSIZED_DOMAINS:
        rec.stage = "REJECT_ICP_SIZE"
        rec.hold_or_reject_reasons.append(f"Exceeds 50-employee ICP ceiling: {OVERSIZED_DOMAINS[dom]}")
        return False

    low, high = parse_size_range(rec.claimed_size_range)
    rec.estimated_min_employees = low
    rec.estimated_max_employees = high
    if low is not None and low >= 50:
        rec.stage = "HOLD_ICP_SIZE_OVER_50"
        rec.hold_or_reject_reasons.append(f"Directory/site size range {rec.claimed_size_range} starts at >=50 (above 50 max)")
        return False
    if high is not None and high > 50:
        rec.stage = "HOLD_ICP_SIZE_OVER_50"
        rec.hold_or_reject_reasons.append(f"Directory/site size range {rec.claimed_size_range} exceeds 50 employees")
        return False

    if not rec.independent_operated:
        rec.stage = "REJECT_NOT_INDEPENDENT"
        rec.hold_or_reject_reasons.append("Not an independently operated company")
        return False

    return True


def verify_channel_route(rec: CandidateRecord) -> bool:
    """Requirement 5: Strict WA / TG / FB channel route verification."""
    # Gather candidate URLs
    all_urls = [u for u in ([rec.contact_url] + rec.all_public_links) if isinstance(u, str) and u.startswith("https://")]
    dom = rec.canonical_domain

    # Auto-detect best channel if unassigned
    wa_urls = [u for u in all_urls if "wa.me/" in u or "api.whatsapp.com/" in u or "web.whatsapp.com/" in u]
    tg_urls = [u for u in all_urls if "t.me/" in u or "telegram.me/" in u]
    fb_urls = [u for u in all_urls if "facebook.com/" in u or "messenger.com/" in u]

    if rec.channel in {"", "UNASSIGNED"}:
        if wa_urls:
            rec.channel = "WA"
            rec.contact_url = wa_urls[0]
        elif tg_urls:
            rec.channel = "TG"
            rec.contact_url = tg_urls[0]
        elif fb_urls:
            rec.channel = "FB"
            rec.contact_url = fb_urls[0]

    ch = rec.channel.upper()
    url = (rec.contact_url or "").strip()
    if not rec.contact_route_source:
        rec.contact_route_source = rec.official_url

    if not url or not url.startswith("https://"):
        rec.route_status = "NO_HTTPS_CONTACT_ROUTE"
        rec.hold_or_reject_reasons.append(f"Missing HTTPS contact route for channel {ch}")
        return False

    host = (urlparse(url).hostname or "").casefold()

    if ch == "WA":
        if host not in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
            rec.route_status = "INVALID_WA_HOST"
            rec.hold_or_reject_reasons.append(f"WA contact_url host {host} is not official WhatsApp link")
            return False
        wa_norm = normalize_wa_phone(url)
        if not wa_norm:
            rec.route_status = "INVALID_OR_PLACEHOLDER_WA_NUMBER"
            rec.hold_or_reject_reasons.append(f"Placeholder or invalid WhatsApp number in {url}")
            return False
        if dom in VERIFIED_FOUNDER_WA_DOMAINS:
            fname, frole = VERIFIED_FOUNDER_WA_DOMAINS[dom]
            rec.recipient_name = fname
            rec.recipient_role = frole
            rec.recipient_verified = True
            rec.route_status = "BUSINESS_ROUTE_VERIFIED"
            rec.contact_qualified = True
            return True
        # Public business WA exists on official site, but recipient marketing opt-in is unverified
        rec.route_status = "BUSINESS_ROUTE_VERIFIED"
        rec.contact_qualified = True
        if not rec.recipient_verified:
            rec.hold_or_reject_reasons.append(
                "HOLD_RECIPIENT_OPT_IN: Official business WhatsApp link verified on site, but named marketing recipient & WhatsApp opt-in unverified"
            )
        return True

    if ch == "TG":
        if host not in {"t.me", "telegram.me"}:
            rec.route_status = "INVALID_TG_HOST"
            rec.hold_or_reject_reasons.append(f"TG contact_url host {host} is not t.me/telegram.me")
            return False
        path = urlparse(url).path.strip("/")
        if not path or "/" in path or path.startswith("+") or path.casefold().startswith("joinchat"):
            rec.route_status = "REJECT_TG_GROUP_OR_CHANNEL_INVITE"
            rec.hold_or_reject_reasons.append(f"Telegram URL {url} is a channel/group/invite path, not a direct account")
            return False
        handle = normalize_tg_handle(url)
        if not handle or len(handle) < 4:
            rec.route_status = "INVALID_TG_HANDLE"
            rec.hold_or_reject_reasons.append(f"Invalid Telegram username in {url}")
            return False
        if handle.endswith("_bot") or handle.endswith("bot"):
            rec.route_status = "REJECT_TG_BOT"
            rec.hold_or_reject_reasons.append(f"Telegram handle @{handle} is a Bot; bots cannot fill TG slots")
            return False
        if handle in VERIFIED_HUMAN_TG_HANDLES:
            rname, _ = VERIFIED_HUMAN_TG_HANDLES[handle]
            rec.recipient_name = rname.split(" (")[0]
            rec.recipient_role = rname
            rec.recipient_verified = True
            rec.route_status = "TG_USERNAME_VERIFIED"
            rec.contact_qualified = True
            return True
        if handle in UNVERIFIED_PUBLIC_CORP_TG_HANDLES:
            rec.route_status = "TG_PUBLIC_CORP_UNVERIFIED_HUMAN"
            rec.contact_qualified = False
            rec.hold_or_reject_reasons.append(
                f"Telegram @{handle} is a company public handle/channel, not a verified human business decision-maker"
            )
            return False
        # Default when handle is a non-bot username but human ownership isn't proven yet
        rec.route_status = "TG_USERNAME_VERIFIED"
        rec.contact_qualified = bool(rec.recipient_verified)
        if not rec.recipient_verified:
            rec.hold_or_reject_reasons.append(
                f"HOLD_TG_HUMAN_VERIFICATION: @{handle} format valid and non-bot, but human decision-maker identity not yet proven"
            )
        return rec.contact_qualified

    if ch == "FB":
        if host not in {"facebook.com", "www.facebook.com", "m.facebook.com", "messenger.com"}:
            rec.route_status = "INVALID_FB_HOST"
            rec.fb_route_status = "INVALID_FB_HOST"
            rec.hold_or_reject_reasons.append(f"FB contact_url host {host} is not Facebook/Messenger")
            return False
        fb_norm = normalize_fb_handle(url)
        if not fb_norm:
            rec.route_status = "INVALID_FB_URL"
            rec.fb_route_status = "INVALID_FB_URL"
            rec.hold_or_reject_reasons.append(f"Invalid Facebook URL structure: {url}")
            return False
        # Distinguish company page vs verified business person
        if rec.fb_route_type == "PERSON" and rec.recipient_verified:
            rec.route_status = "OK"
            rec.fb_route_status = "FB_MESSENGER_VERIFIED"
            rec.contact_qualified = True
            return True
        if "Hady.BZE" in url or "profile.php?id=100083327779732" in url:
            rec.fb_route_type = "PERSON_UNVERIFIED_DM"
            rec.route_status = "HOLD_FB_PERSON_DM_LOGIN"
            rec.fb_route_status = "FB_PAGE_VERIFIED"
            rec.contact_qualified = False
            rec.hold_or_reject_reasons.append(
                "HOLD_FB_PERSON_DM: Personal/founder FB profile link found, but Messenger reachability/identity requires logged-in verification"
            )
            return False
        rec.fb_route_type = "COMPANY_PAGE"
        rec.route_status = "HOLD_FB_COMPANY_PAGE_ONLY"
        rec.fb_route_status = "FB_PAGE_VERIFIED"
        rec.contact_qualified = False
        rec.hold_or_reject_reasons.append(
            "HOLD_FB_PAGE_ONLY: URL is a public company Facebook Page, not a verified reachable business person DM"
        )
        return False

    rec.hold_or_reject_reasons.append(f"Unsupported or unassigned channel: {ch}")
    return False
