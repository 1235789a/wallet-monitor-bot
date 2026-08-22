"""Company-first screening for owner-operated, non-chain local businesses.

The script discovers businesses from a supplied BTC Map/OpenStreetMap snapshot,
never from a search-result page.  It then evaluates every company record, audits
the public website, rejects chains/franchises and identities with more than two
observed locations, and exports an evidence-labelled review pool.

It is intentionally a pre-P0 research stage.  An inferred ownership result must
still be confirmed before the record is promoted to Workflow 1 P0 or contacted.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import ssl
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


BTCMAP_API = "https://api.btcmap.org/v2/elements"
USER_AGENT = "ProspectOS-company-first-screening/1.0 (+read-only public audit)"
MAX_LOCATIONS = 2
SOCIAL_OR_AGGREGATOR_HOSTS = {
    "facebook.com", "instagram.com", "linktr.ee", "lnk.bio", "x.com",
    "twitter.com", "t.me", "wa.me", "youtube.com", "youtu.be",
}
DIRECT_CONTACT_KEYS = (
    "contact:whatsapp", "whatsapp", "contact:telegram", "contact:mobile",
    "mobile", "contact:phone", "phone", "contact:instagram", "contact:facebook",
)
WEBSITE_KEYS = ("website", "contact:website")
DISALLOWED_CATEGORIES = {
    "atm", "money_transfer", "bureau_de_change", "fuel", "casino", "gambling",
    "tobacco", "vape", "weapons", "adult", "nightclub",
}
CHAIN_WORDS = {
    "mcdonald", "starbucks", "subway", "burger king", "wendy", "kfc",
    "domino", "pizza hut", "walmart", "carrefour", "ikea", "shell",
    "bp ", "hilton", "marriott", "hyatt", "holiday inn", "best western",
    "radisson", "ibis ", "ace hardware", "seven eleven", "7-eleven",
}
CHAIN_PAGE_PATTERNS = (
    r"\bfranchis(?:e|ed|ing|es)\b",
    r"\bstore locator\b",
    r"\b(?:[3-9]|[1-9]\d+)\s+(?:stores?|shops?|branches?|locations?|offices?)\b",
    r"\b(?:stores?|shops?|branches?|locations?|offices?)\s+(?:in|across)\s+\d+\b",
)
INDEPENDENT_PAGE_PATTERNS = (
    r"\bfamily[- ]owned\b", r"\bindependently owned\b", r"\bowner[- ]operated\b",
    r"\bfounded by\b", r"\bour founder\b", r"\bsmall business\b",
    r"\bfamily business\b", r"\blocal business\b", r"\blocally owned\b",
    r"\bowned and operated by\b", r"\bmeet the owner\b", r"\bour owners?\b",
    r"\bsole proprietor\b", r"\bindependent business\b", r"\bmom and pop\b",
    r"\bhusband and wife\b", r"\bwoman[- ]owned\b", r"\bveteran[- ]owned\b",
    r"\bminority[- ]owned\b", r"\bestablished by\b", r"\bcreated by\b",
)
LOCATION_PAGE_PATTERNS = (
    r"\bone location\b", r"\bsingle location\b", r"\btwo locations\b",
    r"\b2 locations\b", r"\bour location\b",
)


class TextAndLinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self._hidden_depth += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            value = re.sub(r"\s+", " ", html.unescape(data)).strip()
            if value:
                self.text_parts.append(value)


@dataclass
class WebsiteAudit:
    status: str
    final_url: str
    pages: list[str]
    text_chars: int
    independent_signals: list[str]
    location_signals: list[str]
    chain_signals: list[str]
    has_local_business_schema: bool
    has_faq_schema: bool
    has_direct_message_link: bool
    error: str = ""


def public_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def host(value: str) -> str:
    try:
        parsed = urlsplit(value if "://" in value else f"https://{value}")
        return (parsed.hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def element_tags(row: dict[str, Any]) -> dict[str, str]:
    osm = row.get("osm_json") or {}
    tags = osm.get("tags") or {}
    return {str(k): str(v) for k, v in tags.items()}


def element_name(row: dict[str, Any]) -> str:
    tags = element_tags(row)
    return (tags.get("name:en") or tags.get("name") or "").strip()


def own_website(tags: dict[str, str]) -> str:
    for key in WEBSITE_KEYS:
        value = tags.get(key, "").strip()
        site_host = host(value)
        if public_url(value) and site_host not in SOCIAL_OR_AGGREGATOR_HOSTS:
            return value
    return ""


def company_key(row: dict[str, Any]) -> str:
    tags = element_tags(row)
    website = own_website(tags)
    if website:
        return f"web:{host(website)}"
    for key in ("contact:instagram", "contact:facebook", "contact:telegram"):
        value = tags.get(key, "").strip().casefold().rstrip("/")
        if value:
            return f"social:{key}:{value}"
    for key in ("contact:whatsapp", "whatsapp", "contact:mobile", "mobile", "contact:phone", "phone"):
        value = digits(tags.get(key, ""))
        if value:
            return f"phone:{value}"
    return f"name:{normalize_name(element_name(row))}"


def discovery_url(row: dict[str, Any]) -> str:
    raw = str(row.get("id", ""))
    if ":" not in raw:
        return BTCMAP_API
    osm_type, osm_id = raw.split(":", 1)
    if osm_type not in {"node", "way", "relation"} or not osm_id.isdigit():
        return BTCMAP_API
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"


def row_coordinates(row: dict[str, Any]) -> tuple[float | None, float | None]:
    osm = row.get("osm_json") or {}
    lat, lon = osm.get("lat"), osm.get("lon")
    if lat is None or lon is None:
        center = osm.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def direct_contact(tags: dict[str, str]) -> tuple[str, str, str]:
    for key in DIRECT_CONTACT_KEYS:
        value = tags.get(key, "").strip()
        if not value:
            continue
        if key in {"contact:whatsapp", "whatsapp"}:
            number = digits(value)
            return "whatsapp", value, f"https://wa.me/{number}" if number else value
        if key == "contact:telegram":
            handle = value.rsplit("/", 1)[-1].lstrip("@")
            return "telegram", value, f"https://t.me/{handle}"
        if key in {"contact:instagram", "contact:facebook"}:
            platform = key.split(":", 1)[1]
            if public_url(value):
                return platform, value, value
            base = "https://instagram.com/" if platform == "instagram" else "https://facebook.com/"
            return platform, value, base + value.lstrip("@")
        number = digits(value)
        return "mobile_or_phone", value, f"tel:+{number}" if number else value
    return "", "", ""


def payment_signal(tags: dict[str, str]) -> str:
    signals = []
    if tags.get("currency:USDT") == "yes":
        signals.append("USDT")
    if tags.get("payment:lightning") == "yes":
        signals.append("Bitcoin Lightning")
    if tags.get("payment:onchain") == "yes" or tags.get("currency:XBT") == "yes":
        signals.append("Bitcoin on-chain")
    return ", ".join(signals)


def candidate_category(tags: dict[str, str], row: dict[str, Any]) -> str:
    for key in ("shop", "amenity", "tourism", "craft", "office", "leisure"):
        value = tags.get(key)
        if value:
            return value
    return str((row.get("tags") or {}).get("category", "other"))


def fetch_html(url: str, timeout: int = 12) -> tuple[str, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        content_type = response.headers.get_content_type() if response.headers else ""
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"unsupported content type: {content_type}")
        body = response.read(1_500_000)
        charset = response.headers.get_content_charset() if response.headers else None
        return body.decode(charset or "utf-8", errors="replace"), response.geturl(), content_type


def parse_page(page_html: str, base_url: str) -> tuple[str, list[str]]:
    parser = TextAndLinksParser()
    parser.feed(page_html)
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    links = []
    base_host = host(base_url)
    for href in parser.links:
        absolute = urljoin(base_url, href)
        if public_url(absolute) and host(absolute) == base_host:
            links.append(absolute.split("#", 1)[0])
    return text, list(dict.fromkeys(links))


def audit_website(url: str) -> WebsiteAudit:
    pages: list[str] = []
    texts: list[str] = []
    raw_html_parts: list[str] = []
    try:
        home_html, final_url, _ = fetch_html(url)
        home_text, links = parse_page(home_html, final_url)
        pages.append(final_url)
        texts.append(home_text)
        raw_html_parts.append(home_html)
        useful = []
        for link in links:
            lowered = urlsplit(link).path.casefold()
            if any(token in lowered for token in ("about", "story", "contact", "location", "store")):
                useful.append(link)
        for link in useful[:2]:
            try:
                extra_html, extra_final, _ = fetch_html(link, timeout=10)
                extra_text, _ = parse_page(extra_html, extra_final)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, ssl.SSLError):
                continue
            pages.append(extra_final)
            texts.append(extra_text)
            raw_html_parts.append(extra_html)
        combined = " ".join(texts).casefold()
        raw_combined = " ".join(raw_html_parts).casefold()
        independent = [pattern for pattern in INDEPENDENT_PAGE_PATTERNS if re.search(pattern, combined)]
        locations = [pattern for pattern in LOCATION_PAGE_PATTERNS if re.search(pattern, combined)]
        chain = [pattern for pattern in CHAIN_PAGE_PATTERNS if re.search(pattern, combined)]
        return WebsiteAudit(
            status="ok",
            final_url=final_url,
            pages=list(dict.fromkeys(pages)),
            text_chars=len(combined),
            independent_signals=independent,
            location_signals=locations,
            chain_signals=chain,
            has_local_business_schema=any(
                token in raw_combined for token in ('"localbusiness"', '"organization"')
            ),
            has_faq_schema='"faqpage"' in raw_combined,
            has_direct_message_link=any(
                token in raw_combined for token in ("wa.me/", "whatsapp.com/", "t.me/")
            ),
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
        return WebsiteAudit("fetch_error", url, pages, 0, [], [], [], False, False, False, str(exc))


def load_countries(path: Path | None) -> list[tuple[str, str, tuple[float, float, float, float], Any]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        points: list[tuple[float, float]] = []
        stack = [coordinates]
        while stack:
            value = stack.pop()
            if isinstance(value, list) and len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
                points.append((float(value[0]), float(value[1])))
            elif isinstance(value, list):
                stack.extend(value)
        if not points:
            continue
        xs, ys = zip(*points)
        result.append((
            str(props.get("name", "")), str(props.get("ISO3166-1-Alpha-2", "")),
            (min(xs), min(ys), max(xs), max(ys)), geometry,
        ))
    return result


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[0], point[1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    for polygon in polygons:
        if not polygon or not point_in_ring(lon, lat, polygon[0]):
            continue
        if any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def country_for(lat: float | None, lon: float | None, countries: list[Any]) -> tuple[str, str]:
    if lat is None or lon is None:
        return "Unknown", ""
    for name, code, bbox, geometry in countries:
        min_lon, min_lat, max_lon, max_lat = bbox
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat and point_in_geometry(lon, lat, geometry):
            return name or "Unknown", code
    return "Unknown", ""


def freshness_days(value: str, run_day: date) -> int | None:
    if not value:
        return None
    try:
        return (run_day - datetime.strptime(value[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def prefilter(rows: list[dict[str, Any]], run_day: date) -> tuple[list[dict[str, Any]], Counter[str]]:
    active = [row for row in rows if not row.get("deleted_at") and element_tags(row)]
    key_counts = Counter(company_key(row) for row in active)
    reasons: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    for row in active:
        tags = element_tags(row)
        name = element_name(row)
        key = company_key(row)
        category = candidate_category(tags, row).casefold()
        risk_text = " ".join((name, category, tags.get("shop", ""), tags.get("amenity", ""))).casefold()
        website = own_website(tags)
        contact_type, contact_value, contact_url = direct_contact(tags)
        payment = payment_signal(tags)
        hard_chain_marker = any(tags.get(marker) for marker in ("brand", "brand:wikidata", "operator:wikidata", "franchise"))
        known_chain = any(token in f" {name.casefold()} " for token in CHAIN_WORDS)
        if not name:
            reasons["missing_name"] += 1
        elif not website:
            reasons["no_independent_website"] += 1
        elif not contact_type:
            reasons["no_public_direct_contact"] += 1
        elif not payment:
            reasons["no_public_crypto_payment_signal"] += 1
        elif category in DISALLOWED_CATEGORIES or any(token in risk_text for token in DISALLOWED_CATEGORIES):
            reasons["disallowed_or_financial_category"] += 1
        elif key_counts[key] > MAX_LOCATIONS:
            reasons["three_plus_observed_locations"] += 1
        elif hard_chain_marker or known_chain:
            reasons["chain_or_franchise_marker"] += 1
        else:
            check_date = tags.get("check_date:currency:XBT") or tags.get("check_date") or ""
            check_age = freshness_days(check_date, run_day)
            updated_age = freshness_days(str(row.get("updated_at", "")), run_day)
            score = 0
            score += 24 if contact_type == "whatsapp" else 16 if contact_type == "telegram" else 12
            score += 16 if tags.get("currency:USDT") == "yes" else 8
            score += 18 if check_age is not None and check_age <= 365 else 12 if check_age is not None and check_age <= 730 else 4
            score += 10 if updated_age is not None and updated_age <= 365 else 4
            score += 10 if key_counts[key] == 1 else 7
            score += 5 if tags.get("contact:instagram") or tags.get("contact:facebook") else 0
            score += 5 if tags.get("contact:mobile") or tags.get("contact:phone") else 0
            lat, lon = row_coordinates(row)
            candidates.append({
                "row": row,
                "tags": tags,
                "company_key": key,
                "company_name": name,
                "website_url": website,
                "category": category or "other",
                "contact_type": contact_type,
                "contact_value": contact_value,
                "contact_url": contact_url,
                "payment_signal": payment,
                "location_count": key_counts[key],
                "check_date": check_date,
                "check_age_days": check_age,
                "osm_updated_at": str(row.get("updated_at", "")),
                "latitude": lat,
                "longitude": lon,
                "prefilter_score": score,
            })
    candidates.sort(key=lambda item: (-item["prefilter_score"], item["company_name"].casefold()))
    return candidates, reasons


def screen(
    rows: list[dict[str, Any]],
    minimum_reviewed: int,
    audit_pool: int,
    countries_path: Path | None,
    run_day: date,
    require_owner_evidence: bool = False,
    audit_cache_path: Path | None = None,
) -> dict[str, Any]:
    candidates, prefilter_reasons = prefilter(rows, run_day)
    audit_targets = candidates[: max(audit_pool, minimum_reviewed * 2)]
    audit_cache: dict[str, dict[str, Any]] = {}
    if audit_cache_path is not None and audit_cache_path.exists():
        try:
            loaded = json.loads(audit_cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                audit_cache = loaded
        except (OSError, ValueError, TypeError):
            audit_cache = {}
    audits: dict[str, WebsiteAudit] = {}
    for item in audit_targets:
        cached = audit_cache.get(item["website_url"])
        if isinstance(cached, dict):
            try:
                audits[item["company_key"]] = WebsiteAudit(**cached)
            except TypeError:
                pass
    with ThreadPoolExecutor(max_workers=48) as executor:
        futures = {
            executor.submit(audit_website, item["website_url"]): item["company_key"]
            for item in audit_targets if item["company_key"] not in audits
        }
        completed_since_save = 0
        key_to_url = {item["company_key"]: item["website_url"] for item in audit_targets}
        for future in as_completed(futures):
            key = futures[future]
            audit = future.result()
            audits[key] = audit
            audit_cache[key_to_url[key]] = asdict(audit)
            completed_since_save += 1
            if audit_cache_path is not None and completed_since_save >= 25:
                audit_cache_path.parent.mkdir(parents=True, exist_ok=True)
                audit_cache_path.write_text(
                    json.dumps(audit_cache, ensure_ascii=False), encoding="utf-8"
                )
                completed_since_save = 0
    if audit_cache_path is not None:
        audit_cache_path.parent.mkdir(parents=True, exist_ok=True)
        audit_cache_path.write_text(json.dumps(audit_cache, ensure_ascii=False), encoding="utf-8")

    countries = load_countries(countries_path)
    selected: list[dict[str, Any]] = []
    web_rejections: Counter[str] = Counter()
    seen_keys: set[str] = set()
    for item in audit_targets:
        if item["company_key"] in seen_keys:
            continue
        seen_keys.add(item["company_key"])
        audit = audits[item["company_key"]]
        if audit.status != "ok":
            web_rejections["website_unreachable"] += 1
            continue
        if audit.chain_signals:
            web_rejections["website_chain_or_three_plus_locations_signal"] += 1
            continue
        if require_owner_evidence and not audit.independent_signals:
            web_rejections["owner_operated_not_explicitly_evidenced"] += 1
            continue
        tags = item["tags"]
        country_name, country_code = country_for(item["latitude"], item["longitude"], countries)
        city = tags.get("addr:city") or tags.get("addr:place") or "Unknown"
        ownership_certainty = "self_reported" if audit.independent_signals else "inferred"
        owner_contact_likelihood = (
            "high" if item["contact_type"] in {"whatsapp", "telegram"} and audit.has_direct_message_link
            else "medium-high" if item["contact_type"] in {"whatsapp", "telegram"}
            else "medium"
        )
        geo_gap = "strong" if not audit.has_local_business_schema and not audit.has_faq_schema else "moderate"
        final_score = item["prefilter_score"]
        final_score += 12 if ownership_certainty == "self_reported" else 4
        final_score += 6 if audit.location_signals else 0
        final_score += 5 if audit.has_direct_message_link else 0
        final_score += 5 if geo_gap == "strong" else 2
        discovery = discovery_url(item["row"])
        ownership_note = (
            f"BTC Map/OpenStreetMap shows {item['location_count']} listing(s) for the normalized business identity; "
            "no brand/franchise tag or 3+ location identity was observed. "
            + (
                "The audited website also uses independent/owner/family-business language."
                if ownership_certainty == "self_reported"
                else "Ownership remains an inference and must be confirmed before outreach."
            )
        )
        selected.append({
            "rank": 0,
            "company_name": item["company_name"],
            "country": country_name,
            "country_code": country_code,
            "city": city,
            "category": item["category"],
            "website_url": audit.final_url,
            "discovery_channel": "map_local_business_directory",
            "discovery_source_url": discovery,
            "discovery_note": "Company was discovered in BTC Map/OpenStreetMap before its website was audited; no search-result page was used for discovery.",
            "ownership_model": "independent_small_business",
            "ownership_certainty": ownership_certainty,
            "owner_contact_likelihood": owner_contact_likelihood,
            "location_count": item["location_count"],
            "chain_status": "no_observed_chain_signal",
            "ownership_location_evidence_url": discovery,
            "ownership_location_evidence_note": ownership_note,
            "contact_type": item["contact_type"],
            "contact_value": item["contact_value"],
            "contact_url": item["contact_url"],
            "payment_signal": item["payment_signal"],
            "last_payment_check_date": item["check_date"] or "Unknown",
            "osm_record_updated_at": item["osm_updated_at"],
            "website_pages_audited": audit.pages,
            "website_text_chars": audit.text_chars,
            "website_independent_signals": audit.independent_signals,
            "website_location_signals": audit.location_signals,
            "has_local_business_schema": audit.has_local_business_schema,
            "has_faq_schema": audit.has_faq_schema,
            "geo_gap": geo_gap,
            "geo_gap_note": (
                "Audited pages expose neither LocalBusiness/Organization schema nor FAQ schema."
                if geo_gap == "strong"
                else "The site has some structured entity/FAQ markup, but further AI-answer diagnostics are still needed."
            ),
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "screening_score": final_score,
            "decision": "qualified_for_manual_owner_confirmation",
            "manual_check_required": ownership_certainty != "self_reported",
            "individual_assessment": (
                f"Individually reviewed {item['company_name']} as a {item['category']} business. "
                f"The off-search directory shows {item['location_count']} location(s), the audited website "
                f"contains {len(audit.independent_signals)} independent/owner signal(s), no chain or 3+ "
                f"location signal was found, and the public contact route is {item['contact_type']}. "
                f"The preliminary GEO gap is {geo_gap}."
            ),
        })
    selected.sort(key=lambda item: (-item["screening_score"], item["company_name"].casefold()))
    selected = selected[:minimum_reviewed]
    for rank, item in enumerate(selected, 1):
        item["rank"] = rank
    if len(selected) < minimum_reviewed:
        raise RuntimeError(
            f"only {len(selected)} companies survived individual audits; requested {minimum_reviewed}"
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_day": run_day.isoformat(),
        "method": "company-first off-search discovery -> identity/location dedupe -> website audit -> no-chain gate -> GEO-gap screen",
        "discovery_dataset": BTCMAP_API,
        "raw_records": len(rows),
        "prefilter_candidates": len(candidates),
        "website_audits_attempted": len(audit_targets),
        "qualified_reviewed": len(selected),
        "prefilter_rejections": dict(prefilter_reasons),
        "website_rejections": dict(web_rejections),
        "companies": selected,
    }


def write_outputs(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result['run_day']}-company-first-no-chain-{result['qualified_reviewed']}"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    companies = result["companies"]
    headers = [
        "rank", "company_name", "country", "city", "category", "website_url",
        "discovery_source_url", "ownership_model", "ownership_certainty",
        "owner_contact_likelihood", "location_count", "chain_status",
        "ownership_location_evidence_note", "contact_type", "contact_value", "contact_url",
        "payment_signal", "last_payment_check_date", "geo_gap", "geo_gap_note",
        "screening_score", "manual_check_required", "individual_assessment",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(companies)
    rows = []
    for item in companies:
        rows.append(
            "| " + " | ".join([
                str(item["rank"]), item["company_name"].replace("|", "\\|"),
                f"{item['city']}, {item['country']}".replace("|", "\\|"),
                item["category"].replace("|", "\\|"),
                f"[{item['location_count']}]({item['ownership_location_evidence_url']})",
                item["ownership_certainty"], item["owner_contact_likelihood"],
                f"[{item['contact_type']}]({item['contact_url']})",
                item["payment_signal"].replace("|", "\\|"), item["geo_gap"],
                f"[官网]({item['website_url']})",
            ]) + " |"
        )
    md = f"""# Prospect OS：公司优先、非连锁小商家筛选 — {result['run_day']}

## 运行摘要

- 原始目录记录：{result['raw_records']}
- 进入公司级预筛：{result['prefilter_candidates']}
- 实际逐站审计：{result['website_audits_attempted']}
- 输出：{result['qualified_reviewed']} 家
- 发现方法：先从 BTC Map/OpenStreetMap 商家目录取得公司，再逐家公司审计；未用搜索结果页发现候选。
- 硬排除：已观察到连锁/加盟标记、同一身份3家及以上、无独立官网、无公开直接联系方式、金融ATM/高风险类别。
- 重要限制：`ownership_certainty=inferred` 仍需在发送前人工确认老板身份；它不会被冒充成已确认事实。

## 候选名单

| # | 商家 | 地区 | 类别 | 目录观察地点数 | 所有权证据 | 老板直达概率 | 联系 | 加密支付证据 | GEO缺口 | 官网 |
|---:|---|---|---|---:|---|---|---|---|---|---|
{chr(10).join(rows)}
"""
    md_path.write_text(md, encoding="utf-8")
    return json_path, csv_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Company-first non-chain Prospect OS screening")
    parser.add_argument("source", type=Path, help="BTC Map v2 elements JSON snapshot")
    parser.add_argument("--minimum-reviewed", type=int, default=120)
    parser.add_argument("--audit-pool", type=int, default=320)
    parser.add_argument("--countries-geojson", type=Path)
    parser.add_argument("--require-owner-evidence", action="store_true")
    parser.add_argument("--audit-cache", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    try:
        run_day = datetime.strptime(args.date, "%Y-%m-%d").date()
        rows = json.loads(args.source.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("source must contain a JSON array")
        result = screen(
            rows, args.minimum_reviewed, args.audit_pool,
            args.countries_geojson, run_day, args.require_owner_evidence, args.audit_cache,
        )
        paths = write_outputs(result, args.output_dir)
        print(json.dumps({
            "complete": True,
            "qualified_reviewed": result["qualified_reviewed"],
            "json": str(paths[0]), "csv": str(paths[1]), "markdown": str(paths[2]),
            "prefilter_rejections": result["prefilter_rejections"],
            "website_rejections": result["website_rejections"],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
