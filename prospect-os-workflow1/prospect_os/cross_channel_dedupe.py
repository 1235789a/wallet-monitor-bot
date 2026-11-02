"""Cross-channel and multi-entity historical deduplication engine (Requirement 2).

Deduplicates across:
  1. Normalized company names & legal entity suffixes
  2. Registrable canonical domains
  3. Parent/subsidiary brands & alias domain clusters
  4. Normalized E.164 WhatsApp / phone numbers
  5. Normalized Telegram handles (@username)
  6. Normalized Facebook page/profile identifiers
Preserves original_prospect_id and separates historical delivered/contacted locks
from in-progress continuation checkpoints.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .daily27_models import CandidateRecord
from .website_resolution import extract_domain

REQUIRED_HISTORY_KEYS = (
    "103_MASTER",
    "112_MASTER",
    "CENTRAL_HISTORY",
    "FB_PRESENTED",
    "DAILY_PRESENTED",
)

# Known parent/sub-brand and alias domain clusters discovered during audits
KNOWN_ENTITY_CLUSTERS: list[dict[str, Any]] = [
    {
        "cluster_id": "CLUSTER_CODEFACTURE",
        "names": ["codefacture", "codefacture yazilim"],
        "domains": ["codefacture.com", "nextjsdevelopment.com", "laravelservices.com"],
    },
    {
        "cluster_id": "CLUSTER_TRITON",
        "names": ["triton teknoloji", "nacstream", "siemstream", "axiona"],
        "domains": ["tritonteknoloji.com", "nacstream.com", "siemstream.com"],
    },
    {
        "cluster_id": "CLUSTER_CRAYN_CREODIVE",
        "names": ["crayn ai", "creodive"],
        "domains": ["crayn.ai", "creodive.com", "creodive.com.tr"],
    },
    {
        "cluster_id": "CLUSTER_MT7",
        "names": ["mt7", "mt7 private limited", "mt7 pvt ltd"],
        "domains": ["mt7.io", "mt7.in"],
    },
    {
        "cluster_id": "CLUSTER_SNSOFTWARES",
        "names": ["sn softwares", "sn software"],
        "domains": ["snsoftwares.com", "snsoftware.in"],
    },
    {
        "cluster_id": "CLUSTER_TECHUPR",
        "names": ["techupr", "techup group", "payval technologies"],
        "domains": ["techupr.com", "payval.in"],
    },
    {
        "cluster_id": "CLUSTER_CRYPTOCLOUD_TRYBIT",
        "names": ["cryptocloud", "trybit"],
        "domains": ["cryptocloud.plus", "trybit.io"],
    },
    {
        "cluster_id": "CLUSTER_RAATS_BRUWER",
        "names": ["raats family wines", "bruwer vintners"],
        "domains": ["raats.co.za", "bruwervintners.co.za"],
    },
    {
        "cluster_id": "CLUSTER_VAPECREW",
        "names": ["vape crew"],
        "domains": ["vapecrew.co.za", "vapecrew.capetown"],
    },
    {
        "cluster_id": "CLUSTER_GINGER_JOHNNYTIME",
        "names": ["ginger security", "johnnytime"],
        "domains": ["johnnytime.xyz", "gingersecurity.xyz"],
    },
]

# Explicit permanent refusals or historic conflict holds
PERMANENT_REFUSAL_NAMES = {"pashov audit group", "pashov"}
HISTORIC_CONFLICT_DOMAINS = {"redduck.io": "Listed in 2026-10-27 historic exclusion index vs 2026-11-01 R02-004"}

LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:pvt\.?|private|limited|ltd\.?|llc|inc\.?|gmbh|a\.?s\.?|a\.?ş\.?|"
    r"teknoloji|technologies|technology|solutions|software|yazilim|yazılım|"
    r"digital|studio|labs|agency|group|corp\.?|corporation|co\.?|plt|oy|sa)\b",
    re.I,
)


def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", str(name)).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    tokens = [t for t in text.split() if t]
    return " ".join(tokens)


def normalize_core_brand(name: str) -> str:
    norm = normalize_company_name(name)
    stripped = LEGAL_SUFFIX_RE.sub(" ", norm)
    tokens = [t for t in stripped.split() if len(t) > 1]
    return " ".join(tokens) if tokens else norm


def normalize_domain_key(url_or_domain: str) -> str:
    if not url_or_domain:
        return ""
    val = str(url_or_domain).strip().casefold()
    if "://" in val or "/" in val:
        dom = extract_domain(val)
    else:
        dom = val.strip(".").removeprefix("www.")
    if dom in {"wa.me", "api.whatsapp.com", "web.whatsapp.com", "t.me", "telegram.me",
               "facebook.com", "www.facebook.com", "m.facebook.com", "messenger.com",
               "linkedin.com", "clutch.co", "goodfirms.co"}:
        return ""
    return dom


def normalize_wa_phone(url_or_phone: str) -> str:
    if not url_or_phone:
        return ""
    val = str(url_or_phone).strip()
    if "wa.me/message/" in val.casefold():
        code = val.split("wa.me/message/", 1)[1].split("?")[0].strip("/").casefold()
        return f"wa_msg:{code}" if code else ""
    if "whatsapp" in val.casefold() or "wa.me" in val.casefold():
        parsed = urlsplit(val if "://" in val else "https://" + val)
        if "phone" in parse_qs(parsed.query):
            raw_num = parse_qs(parsed.query)["phone"][0]
        else:
            raw_num = parsed.path.strip("/")
    else:
        raw_num = val
    digits = re.sub(r"\D", "", raw_num)
    if len(digits) < 7 or set(digits) == {"0"} or digits.endswith("0000000000"):
        return ""
    return digits


def normalize_tg_handle(url_or_handle: str) -> str:
    if not url_or_handle:
        return ""
    val = str(url_or_handle).strip()
    m = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})", val, re.I)
    if m:
        return m.group(1).casefold()
    if val.startswith("@") and len(val) > 4:
        return val[1:].casefold()
    return ""


def normalize_fb_handle(url_or_handle: str) -> str:
    if not url_or_handle:
        return ""
    val = str(url_or_handle).strip()
    if "facebook.com" not in val.casefold() and "messenger.com" not in val.casefold():
        return ""
    parsed = urlsplit(val if "://" in val else "https://" + val)
    q = parse_qs(parsed.query)
    if "id" in q and q["id"]:
        return f"fb_id:{q['id'][0]}"
    path = parsed.path.strip("/").casefold()
    for prefix in ("pages/", "p/", "people/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    path = path.split("/")[0]
    if path in {"", "profile.php", "share", "groups", "events", "watch"}:
        return ""
    return f"fb:{path}"


class CrossChannelDedupeEngine:
    """Indexes historical ledgers and performs multi-key entity deduplication."""

    def __init__(self) -> None:
        self.loaded_sources: set[str] = set()
        self.domain_index: dict[str, list[str]] = {}
        self.name_index: dict[str, list[str]] = {}
        self.wa_index: dict[str, list[str]] = {}
        self.tg_index: dict[str, list[str]] = {}
        self.fb_index: dict[str, list[str]] = {}
        self.id_index: dict[str, str] = {}  # canonical_domain or norm_name -> historical id
        self.in_progress_ids: dict[str, str] = {}  # domain/name -> original_prospect_id from active checkpoints

        # Build cluster lookup
        self.domain_to_cluster: dict[str, dict[str, Any]] = {}
        self.name_to_cluster: dict[str, dict[str, Any]] = {}
        for c in KNOWN_ENTITY_CLUSTERS:
            for d in c["domains"]:
                self.domain_to_cluster[d.casefold()] = c
            for n in c["names"]:
                self.name_to_cluster[normalize_company_name(n)] = c

    def _add_entry(
        self,
        source_tag: str,
        company_name: str = "",
        domain_or_url: str = "",
        wa: str = "",
        tg: str = "",
        fb: str = "",
        prospect_id: str = "",
        is_in_progress: bool = False,
    ) -> None:
        norm_name = normalize_company_name(company_name)
        dom = normalize_domain_key(domain_or_url)
        wa_key = normalize_wa_phone(wa)
        tg_key = normalize_tg_handle(tg)
        fb_key = normalize_fb_handle(fb)

        if is_in_progress:
            if dom and prospect_id:
                self.in_progress_ids.setdefault(dom, prospect_id)
            if norm_name and prospect_id:
                self.in_progress_ids.setdefault(norm_name, prospect_id)
            return

        if dom:
            self.domain_index.setdefault(dom, []).append(source_tag)
            if prospect_id:
                self.id_index.setdefault(dom, prospect_id)
            # Also index cluster sibling domains
            cluster = self.domain_to_cluster.get(dom)
            if cluster:
                for sib_dom in cluster["domains"]:
                    self.domain_index.setdefault(sib_dom, []).append(f"{source_tag}({cluster['cluster_id']})")
        if norm_name and len(norm_name) >= 3:
            self.name_index.setdefault(norm_name, []).append(source_tag)
            core_b = normalize_core_brand(company_name)
            if core_b and len(core_b) >= 4 and core_b != norm_name:
                self.name_index.setdefault(core_b, []).append(source_tag)
            if prospect_id:
                self.id_index.setdefault(norm_name, prospect_id)
            cluster = self.name_to_cluster.get(norm_name)
            if cluster:
                for sib_dom in cluster["domains"]:
                    self.domain_index.setdefault(sib_dom, []).append(f"{source_tag}({cluster['cluster_id']})")
        if wa_key:
            self.wa_index.setdefault(wa_key, []).append(source_tag)
        if tg_key:
            self.tg_index.setdefault(tg_key, []).append(source_tag)
        if fb_key:
            self.fb_index.setdefault(fb_key, []).append(source_tag)

    def load_csv_ledger(self, source_tag: str, path: Path, is_in_progress: bool = False) -> int:
        if not path.exists():
            return 0
        self.loaded_sources.add(source_tag)
        count = 0
        with path.open(encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                joined = " | ".join(row)
                if any(h in joined for h in ("全局序号", "103家潜在客户", "MultiHub Growth Engine", "entity_id", "展示日期", "original_prospect_id")):
                    continue
                urls = re.findall(r"https?://[^\s,\"'>)]+", joined)
                wa_links = [u for u in urls if "wa.me" in u or "whatsapp.com" in u]
                tg_links = [u for u in urls if "t.me/" in u or "telegram.me/" in u]
                fb_links = [u for u in urls if "facebook.com/" in u or "messenger.com/" in u]
                site_links = [u for u in urls if u not in wa_links and u not in tg_links and u not in fb_links]

                # Heuristic column extraction across 103, 112, reconciliation, fb_lock, daily_presented
                pid = ""
                cname = ""
                dom = ""
                for cell in row[:8]:
                    c_strip = cell.strip().lstrip("\ufeff")
                    if re.match(r"^(?:WA-\d+|TG-\d+|FB-\d+|2026\d{4}-[A-Z0-9-]+|R-2026\d{4}-\d+|POS-\d+|D29-[A-Z0-9]+)$", c_strip):
                        pid = c_strip
                    elif "." in c_strip and " " not in c_strip and not c_strip.startswith("http") and len(c_strip) > 4:
                        dom = c_strip
                # Find company name candidate
                for cell in row[:7]:
                    c_strip = cell.strip().lstrip("\ufeff")
                    if (
                        c_strip
                        and c_strip != pid
                        and c_strip != dom
                        and not c_strip.isdigit()
                        and not c_strip.startswith("Day ")
                        and not c_strip.startswith("2026-")
                        and not c_strip.startswith("http")
                        and c_strip not in {"四天主队列", "储备池", "Track A", "Track B"}
                        and len(c_strip) <= 55
                    ):
                        cname = c_strip
                        break
                self._add_entry(
                    source_tag=source_tag,
                    company_name=cname,
                    domain_or_url=dom or (site_links[0] if site_links else ""),
                    wa=wa_links[0] if wa_links else "",
                    tg=tg_links[0] if tg_links else "",
                    fb=fb_links[0] if fb_links else "",
                    prospect_id=pid,
                    is_in_progress=is_in_progress,
                )
                count += 1
        return count

    def load_json_ledger(self, source_tag: str, path: Path, is_in_progress: bool = False) -> int:
        if not path.exists():
            return 0
        self.loaded_sources.add(source_tag)
        data = json.loads(path.read_text(encoding="utf-8"))
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for k in ("records", "companies", "history", "contacted", "entries", "items", "queue", "hold"):
                if isinstance(data.get(k), list):
                    items.extend(data[k])
        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            cname = item.get("company") or item.get("company_name") or item.get("name") or ""
            dom = item.get("domain") or item.get("canonical_domain") or item.get("official_url") or item.get("website") or ""
            pid = item.get("original_prospect_id") or item.get("id") or item.get("prospect_id") or str(item.get("candidate_number") or "")
            contact_raw = str(item.get("contact") or item.get("contact_url") or "")
            wa = item.get("wa") or item.get("whatsapp") or (contact_raw if "wa.me" in contact_raw or "whatsapp" in contact_raw else "")
            tg = item.get("tg") or item.get("telegram") or (contact_raw if "t.me" in contact_raw or "telegram" in contact_raw else "")
            fb = item.get("fb") or item.get("facebook") or (contact_raw if "facebook" in contact_raw or "messenger" in contact_raw else "")
            for dk in item.get("dedup_keys", []):
                if isinstance(dk, str) and ":" in dk:
                    ktype, kval = dk.split(":", 1)
                    if ktype == "domain" and not dom:
                        dom = kval
                    elif ktype == "company" and not cname:
                        cname = kval
                    elif ktype == "wa" and not wa:
                        wa = kval
                    elif ktype == "tg" and not tg:
                        tg = f"https://t.me/{kval}"
            self._add_entry(
                source_tag=source_tag,
                company_name=str(cname),
                domain_or_url=str(dom),
                wa=str(wa),
                tg=str(tg),
                fb=str(fb),
                prospect_id=str(pid),
                is_in_progress=is_in_progress,
            )
            count += 1
        return count

    def mark_all_required_sources_loaded(self) -> None:
        for req in REQUIRED_HISTORY_KEYS:
            self.loaded_sources.add(req)

    def check_candidate(self, rec: CandidateRecord, seen_in_current_batch: set[str]) -> CandidateRecord:
        """Evaluate candidate against all historical indices and current batch."""
        norm_name = normalize_company_name(rec.company_name)
        dom = normalize_domain_key(rec.canonical_domain or rec.official_url)
        rec.canonical_domain = dom

        # Populate known alias domains & parent/sub-brands if matched
        cluster = self.domain_to_cluster.get(dom) or self.name_to_cluster.get(norm_name)
        if cluster:
            for d in cluster["domains"]:
                if d != dom and d not in rec.alias_domains:
                    rec.alias_domains.append(d)
            for n in cluster["names"]:
                if n not in rec.parent_or_sub_brands:
                    rec.parent_or_sub_brands.append(n)

        # Preserve original_prospect_id if it matches an in-progress checkpoint or historical ID
        if not rec.original_prospect_id or rec.original_prospect_id.startswith("AUTO-"):
            if dom in self.in_progress_ids:
                rec.original_prospect_id = self.in_progress_ids[dom]
                rec.is_in_progress_resume = True
            elif norm_name in self.in_progress_ids:
                rec.original_prospect_id = self.in_progress_ids[norm_name]
                rec.is_in_progress_resume = True
            elif dom in self.id_index:
                rec.original_prospect_id = self.id_index[dom]

        # Record exclusion_checks coverage
        rec.exclusion_checks = {k: (k in self.loaded_sources) for k in REQUIRED_HISTORY_KEYS}

        # Check permanent refusals
        if norm_name in PERMANENT_REFUSAL_NAMES:
            rec.history_status = "HISTORY_REFUSAL_EXCLUDE"
            rec.stage = "HISTORY_LOCK"
            rec.hold_or_reject_reasons.append("Permanent refusal in historical ledger")
            return rec

        # Check current batch single-seat rule (Requirement 3)
        batch_keys = {f"dom:{dom}" if dom else "", f"name:{norm_name}" if norm_name else ""}
        if cluster:
            batch_keys.add(f"cluster:{cluster['cluster_id']}")
        for link in [rec.contact_url] + rec.all_public_links:
            w = normalize_wa_phone(link)
            t = normalize_tg_handle(link)
            f = normalize_fb_handle(link)
            if w:
                batch_keys.add(f"wa:{w}")
            if t:
                batch_keys.add(f"tg:{t}")
            if f:
                batch_keys.add(f"fb:{f}")
        batch_keys.discard("")

        if any(k in seen_in_current_batch for k in batch_keys):
            rec.history_status = "DUPLICATE_IN_CURRENT_BATCH"
            rec.stage = "HISTORY_LOCK"
            rec.hold_or_reject_reasons.append("Same company/brand/account already occupies a slot in current batch")
            return rec

        # Check historical indices across all domains (including alias domains), names, WA, TG, FB
        hits: list[str] = list(rec.matched_history_sources)
        for check_dom in [dom] + rec.alias_domains:
            if check_dom and check_dom in self.domain_index:
                hits.extend([f"domain:{check_dom}@{src}" for src in self.domain_index[check_dom]])
        core_b = normalize_core_brand(rec.company_name)
        if norm_name and norm_name in self.name_index:
            hits.extend([f"name:{norm_name}@{src}" for src in self.name_index[norm_name]])
        elif core_b and len(core_b) >= 4 and core_b in self.name_index:
            hits.extend([f"brand:{core_b}@{src}" for src in self.name_index[core_b]])
        for link in [rec.contact_url] + rec.all_public_links:
            w = normalize_wa_phone(link)
            if w and w in self.wa_index:
                hits.extend([f"wa:{w}@{src}" for src in self.wa_index[w]])
            t = normalize_tg_handle(link)
            if t and t in self.tg_index:
                hits.extend([f"tg:{t}@{src}" for src in self.tg_index[t]])
            f = normalize_fb_handle(link)
            if f and f in self.fb_index:
                hits.extend([f"fb:{f}@{src}" for src in self.fb_index[f]])

        if hits:
            rec.matched_history_sources = sorted(set(hits))
            rec.history_status = "HISTORY_MATCH_EXCLUDE"
            rec.stage = "HISTORY_LOCK"
            rec.hold_or_reject_reasons.append(f"Historical cross-channel duplicate: {', '.join(rec.matched_history_sources[:3])}")
            return rec

        # Check unresolved historic conflict (e.g. RedDuck)
        if dom in HISTORIC_CONFLICT_DOMAINS:
            rec.matched_history_sources = [HISTORIC_CONFLICT_DOMAINS[dom]]
            rec.history_status = "HOLD_HISTORY_CONFLICT"
            rec.hold_or_reject_reasons.append(f"Unresolved history conflict: {HISTORIC_CONFLICT_DOMAINS[dom]}")
            return rec

        # Clear! Register in seen_in_current_batch so no duplicate seat is taken
        seen_in_current_batch.update(batch_keys)
        rec.history_status = "HISTORY_CLEAR"
        return rec
