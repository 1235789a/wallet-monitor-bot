"""Bounded, cached evidence collection for the precise gaps in PRELOCK_REVIEW."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .contact_enrichment import ContactPageParser, extract_contacts, fetch_html, robots_allows
from .contact_reachability import merge_contact_route, route_identity
from .sampling import classify_vertical, sampling_record_key, track_for_vertical
from .source_pool import USER_AGENT, canonical_domain, public_http_url


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_buyer_query(query):
    """Public Bing RSS test. Its limited returned set is recorded explicitly."""
    url = "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"})
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=8) as response:
        root = ET.fromstring(response.read(300_000))
    results = [{"title": item.findtext("title") or "", "url": item.findtext("link") or "",
                "snippet": item.findtext("description") or ""}
               for item in root.findall("./channel/item")]
    return {"query": query, "platform": "bing", "method": "direct_platform_test",
            "tested_at": _now(), "scope": "first 10 Bing RSS results; not an exhaustive ranking",
            "results": results[:10], "evidence_url": url}


class ReviewRepairer:
    def __init__(self, cache_dir, *, raw_rows=(), evidence_rows=(), max_pages=2,
                 max_queries=2, fetcher=fetch_html, query_tester=test_buyer_query,
                 respect_robots=True):
        self.cache_dir = Path(cache_dir)
        self.max_pages, self.max_queries = max_pages, max_queries
        self.fetcher, self.query_tester, self.respect_robots = fetcher, query_tester, respect_robots
        self.evidence = {sampling_record_key(row): row for row in evidence_rows}
        self.domain_locations = {}
        for row in raw_rows:
            domain = canonical_domain(str(row.get("website_url") or row.get("domain") or ""))
            raw = row.get("raw_source_record") or {}
            properties = raw.get("properties") if isinstance(raw, dict) else None
            record = properties if isinstance(properties, dict) else raw
            tags = (record.get("tags") or record) if isinstance(record, dict) else {}
            # Directory category labels may be a list; they are not OSM
            # address mappings and cannot establish a physical location.
            if not isinstance(tags, dict):
                tags = {}
            # Source point IDs establish a lower bound, never a complete count.
            location = row.get("location_id") or tags.get("addr:full") or tags.get("address")
            if domain and location:
                self.domain_locations.setdefault(domain, set()).add(str(location))
        self.usage = {"page_reads": 0, "query_tests": 0, "cache_hits": 0}
        self.seed_pages = {}

    def _cached(self, kind, key, fn):
        path = self.cache_dir / (kind + "-" + hashlib.sha256(key.encode()).hexdigest() + ".json")
        if path.exists():
            self.usage["cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            value = fn()
            value["status"] = "ok"
        except Exception as exc:
            value = {"status": "unavailable", "error": str(exc), "checked_at": _now()}
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return value

    def _page(self, url, website):
        if url.rstrip("/") in self.seed_pages:
            self.usage["cache_hits"] += 1
            return self.seed_pages[url.rstrip("/")]
        def collect():
            if self.respect_robots and not robots_allows(url, timeout=5):
                raise ValueError("robots_disallowed")
            self.usage["page_reads"] += 1
            body, final = self.fetcher(url)
            if canonical_domain(final) != canonical_domain(website):
                raise ValueError("redirected_outside_company_domain")
            parser = ContactPageParser()
            parser.feed(body)
            return {"url": final, "text": " ".join(parser.text_parts)[:60_000],
                    **extract_contacts(final, body), "checked_at": _now()}
        return self._cached("page", url, collect)

    def _query(self, query, website):
        def collect():
            self.usage["query_tests"] += 1
            result = self.query_tester(query)
            if not result.get("tested_at") or not result.get("scope") or not result.get("platform"):
                raise ValueError("query test must carry date, platform and bounded scope")
            return result
        return self._cached("query", query, collect)

    def __call__(self, row, action):
        # Import lazily to keep collection independent of gate implementations.
        from .prelock_preflight import preflight_record
        from .buyer_rating import rate_candidate
        result = json.loads(json.dumps(row))
        for page in row.get("page_evidence", []):
            if canonical_domain(page.get("url", "")) == canonical_domain(str(row.get("website_url") or "")):
                self.seed_pages[page["url"].rstrip("/")] = page
        before = json.dumps([result.get("prelock_assessment"), result.get("contacts")], sort_keys=True)
        assessment = result.setdefault("prelock_assessment", {})
        patch = self.evidence.get(sampling_record_key(row))
        if patch:
            result["review_input_sha256"] = hashlib.sha256(json.dumps(patch, sort_keys=True).encode()).hexdigest()
            if patch.get("company_name") != row.get("company_name"):
                raise ValueError("review evidence changed company identity")
            if patch.get("website_url") and canonical_domain(patch["website_url"]) != canonical_domain(row.get("website_url", "")):
                raise ValueError("review evidence changed company website")
            for key, value in (patch.get("prelock_assessment") or {}).items():
                if key not in assessment or assessment[key] in (None, "", []):
                    assessment[key] = value
            # External assessments may verify an existing route, never replace it.
            by_route = {(c.get("channel"), c.get("value")): c for c in patch.get("contacts", [])}
            for contact in result.get("contacts", []):
                evidence = by_route.get((contact.get("channel"), contact.get("value")))
                if evidence and isinstance(evidence.get("outreach_route"), dict):
                    contact["outreach_route"] = evidence["outreach_route"]
                if evidence and isinstance(evidence.get("human_reachability"), dict):
                    contact["human_reachability"] = evidence["human_reachability"]
                    if evidence.get("decision_maker_evidence"):
                        contact["decision_maker_evidence"] = evidence["decision_maker_evidence"]
                        contact["contact_belongs_to_decision_maker"] = evidence.get("contact_belongs_to_decision_maker") is True
            if patch.get("rating_assessment"):
                result["rating_assessment"] = patch["rating_assessment"]

        missing = set(preflight_record(result).get("prelock_missing_evidence", []))
        website = str(result.get("website_url") or "")
        page_gaps = missing - {"buyer_query_test_evidence", "buyer_query_test_metadata", "buyer_intent_evidence",
            "competitor_or_substitute_evidence", "buyer_query_evidence_url",
            "buyer_intent_competitor_evidence", "one_or_two_tested_buyer_queries", "visibility_gap_evidence"}
        pages = []
        if page_gaps and public_http_url(website):
            home = self._page(website, website)
            if home.get("status") == "ok":
                pages.append(home)
                links = home.get("internal_links") or []
                terms = ("location", "store", "loja") if any("location" in gap for gap in missing) else (
                    ("team", "about", "founder", "sobre") if any("team" in gap or "ownership" in gap for gap in missing)
                    else ("contact", "contato", "team", "founder", "partnership", "about"))
                relevant = sorted((url for url in links if any(term in urlsplit(url).path.casefold() for term in terms)),
                                  key=lambda url: (len(url), url))
                for url in relevant[:max(0, self.max_pages - 1)]:
                    captured = self._page(url, website)
                    if captured.get("status") == "ok":
                        pages.append(captured)
        for page in pages:
            text, url = page["text"], page["url"]
            ev = {"source_url": url, "checked_at": page["checked_at"], "label": "self_reported"}
            def add(key, value, claim, url_key=None):
                if key not in assessment or assessment[key] in (None, "", []):
                    assessment[key] = value
                    assessment.setdefault("field_evidence", {})[key] = {**ev, "claim": claim[:350]}
                    assessment.setdefault("evidence_urls", []).append(url)
                    if url_key:
                        assessment[url_key] = url
                elif assessment[key] == value and url_key and not public_http_url(str(assessment.get(url_key) or "")):
                    assessment[url_key] = url
                    assessment.setdefault("field_evidence", {})[key] = {**ev, "claim": claim[:350]}
            owner = re.search(r"[^.]{0,60}\b(?:independently owned|family[- ]owned|owner[- ]operated|founder[- ]led)\b[^.]{0,120}", text, re.I)
            if owner:
                add("ownership_type", "independent", owner.group(), "ownership_evidence_url")
                add("chain", False, owner.group(), "ownership_evidence_url")
            locations = re.search(r"\b(?:our (?:only|single) (?:store|shop|location)|(?:we (?:have|operate)|our)\s+(one|two|[0-9]+)\s+(?:stores|shops|locations))\b", text, re.I)
            if locations:
                value = locations.group(1)
                count = {"one": 1, "two": 2}.get(value, int(value) if value and value.isdigit() else 1)
                count = max(count, len(self.domain_locations.get(canonical_domain(website), set())))
                if count > 2:
                    assessment["locations"] = count
                    assessment["location_evidence_url"] = url
                else:
                    add("locations", count, locations.group(), "location_evidence_url")
            team = re.search(r"\b(?:team of|we (?:are|have))\s+(\d+)\s+(?:people|employees|members|developers|engineers)\b", text, re.I)
            if team and 1 <= int(team.group(1)) <= 49:
                add("small_team_evidence", team.group(), team.group(), "team_evidence_url")
                add("not_enterprise", True, team.group(), "team_evidence_url")
            b2b = re.search(r"\b(?:for businesses|business customers|b2b|corporate clients)\b", text, re.I)
            if b2b:
                add("is_b2b", True, b2b.group(), "b2b_evidence_url")
            service = re.search(r"\b(?:request (?:a )?quote|book (?:a )?consultation|pricing plans|buy now|add to cart|subscribe now)\b", text, re.I)
            if service:
                add("purchasable_service", True, service.group(), "service_evidence_url")
            if service and str(row.get("company_name") or "").casefold() in text.casefold():
                add("business_real", True, f"Official page names {row['company_name']} and offers {service.group()}", "business_evidence_url")
            stock = re.search(r"\b(?:in stock|available for delivery|now accepting orders)\b", text, re.I)
            if stock and service:
                add("active_business", True, "Live official commerce page states: " + stock.group(), "business_evidence_url")
            if classify_vertical({"description": text}) == classify_vertical(row):
                add("vertical_match", True, "Official page describes the discovered business vertical", "business_evidence_url")
            def contact_key(contact):
                return route_identity(str(contact.get("value") or "")) if contact.get("channel") in {"whatsapp", "telegram"} else (contact.get("channel"), contact.get("value"))
            existing = {contact_key(c): c for c in result.get("contacts", [])}
            for contact in page.get("contacts", []):
                key = contact_key(contact)
                existing[key] = merge_contact_route(existing[key], contact) if key in existing else contact
            result["contacts"] = list(existing.values())
        if pages:
            result["pages_checked"] = list(dict.fromkeys((result.get("pages_checked") or []) + [p["url"] for p in pages]))
            result["contact_enrichment_status"] = "completed"
            by_url = {p["url"]: p for p in result.get("page_evidence", [])}
            by_url.update({p["url"]: p for p in pages})
            result["page_evidence"] = list(by_url.values())

        pending = preflight_record(result)
        query_gaps = {"buyer_query_test_evidence", "buyer_query_test_metadata", "buyer_intent_evidence", "competitor_or_substitute_evidence",
                      "buyer_query_evidence_url", "buyer_intent_competitor_evidence",
                      "one_or_two_tested_buyer_queries", "visibility_gap_evidence"}
        if query_gaps & set(pending.get("prelock_missing_evidence", [])) and public_http_url(website):
            queries = pending.get("prelock_buyer_queries") or []
            tested = []
            for draft in queries[:self.max_queries]:
                if not isinstance(draft, dict) or not draft.get("query"):
                    continue
                if (draft.get("tested") is True and draft.get("competitor_evidence")
                        and draft.get("tested_at") and draft.get("platform") and draft.get("scope")
                        and draft.get("visibility_gap") is True):
                    tested.append(draft)
                    continue
                test = self._query(draft["query"], website)
                if test.get("status") != "ok":
                    tested.append(draft)
                    continue
                returned = [item for item in test.get("results", []) if public_http_url(item.get("url", ""))]
                relevance = {
                    "web3_blockchain": r"\b(?:blockchain|web3|defi|crypto|smart contract)\b",
                    "ai_software_b2b_agency": r"\b(?:software|saas|ai|machine learning|b2b)\b",
                    "vape_tobacco": r"\b(?:vape|vaping|tobacco|cigar|smoke shop)\b",
                    "alcohol_wine_bar": r"\b(?:wine|alcohol|liquor|spirits|bar|beer)\b",
                    "adult_retail": r"\b(?:adult|erotic|sex|sexual wellness|toy)\b",
                }.get(classify_vertical(row), r"(?!)")
                commercial = [item for item in returned if re.search(
                    r"\b(?:shop|buy|store|pricing|quote|service|provider|consultation|company|development)\b",
                    item.get("title", "") + " " + item.get("snippet", ""), re.I)
                    and re.search(relevance, item.get("title", "") + " " + item.get("snippet", ""), re.I)]
                competitors = [item for item in commercial if canonical_domain(item["url"]) != canonical_domain(website)]
                presence = any(canonical_domain(item["url"]) == canonical_domain(website) for item in returned)
                tested.append({**draft, "tested": True, "status": "tested",
                    "buyer_intent": True if competitors else None,
                    "competitor_evidence": [{"name": c["title"], "url": c["url"]} for c in competitors],
                    "evidence_urls": [test["evidence_url"]] + [c["url"] for c in competitors],
                    "tested_at": test["tested_at"], "platform": test["platform"], "scope": test["scope"],
                    "prospect_presence": "present" if presence else "not_in_returned_results",
                    "visibility_gap": bool(competitors and not presence)})
            if tested:
                assessment["buyer_queries"] = tested
        result = rate_candidate(preflight_record(result))
        after = json.dumps([result.get("prelock_assessment"), result.get("contacts")], sort_keys=True)
        result["review_evidence_changed"] = before != after
        result["review_repair_action"] = action
        result["review_repair_usage"] = dict(self.usage)
        if before == after and result["prelock_status"] == "PRELOCK_REVIEW":
            result["review_blocked_reason"] = "no_new_public_evidence; supply reviewed evidence or refresh the evidence cache"
        return result
