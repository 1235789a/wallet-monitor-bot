"""Loads and merges real RAW prospect pools, enriched checkpoints, and archived browser evidence.

Implements Requirement 1 & 2:
  - Uses existing RAW customer pools as initial data without re-searching processed companies from scratch.
  - Preserves original_prospect_id across all checkpoints and pools.
  - Attaches real archived browser screenshots (.jpg), website texts, and contact links.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .cross_channel_dedupe import normalize_company_name, normalize_domain_key
from .daily27_models import AITestRecord, CandidateRecord
from .geo_image_renderer import compute_file_sha256

# Curated verified facts from 2026-11-01 & 2026-11-02 live browser & google:browse checks
CURATED_ENRICHMENTS: dict[str, dict[str, Any]] = {
    "20261101-R02-083": {
        "company_name": "Ozturksoft",
        "official_url": "https://ozturksoft.net/",
        "contact_url": "https://wa.me/905465496806",
        "channel": "WA",
        "primary_service": "Ankara AI integration, enterprise software and digital transformation",
        "observed_site_fact": "Homepage explicitly lists SEO & GEO optimisation for AI search alongside custom software.",
    },
    "20261101-R02-085": {
        "company_name": "TankDev",
        "official_url": "https://tankdev.tech/",
        "contact_url": "https://wa.me/905300939183",
        "channel": "WA",
        "primary_service": "Custom business software, ERP/CRM integrations and applied AI workflows",
        "observed_site_fact": "Explicitly markets GEO / AI search visibility optimization alongside custom software.",
    },
    "20261101-R02-086": {
        "company_name": "Codefacture",
        "official_url": "https://codefacture.com/",
        "contact_url": "https://wa.me/908503085436",
        "contact_route_source": "https://codefacture.com/contact/",
        "channel": "WA",
        "alias_domains": ["nextjsdevelopment.com", "laravelservices.com"],
        "primary_service": "custom CRM/ERP software, AI integration and web/mobile systems in Ankara",
        "observed_site_fact": "Codefacture Yazilim A.S. (Ankara) builds custom CRM/ERP and AI systems; English working language; blog published 2026-10-22.",
        "recent_30d_activity_status": "PASS_COMPANY_PUBLISHED_2026-10-22",
        "recent_30d_activity_evidence": "Company blog article 'PHP2Shell Vulnerability: What It Is and How to Fix It' dated 2026-10-22.",
        "recent_30d_activity_url": "https://codefacture.com/blog/php2shell-cve-2026/",
        "buyer_question": "Who builds custom CRM and ERP software with AI integration in Ankara?",
        "ai_test": {
            "tested": True,
            "platform": "Perplexity (Search Mode)",
            "model": "Unspecified Search Mode",
            "tested_at_utc": "2026-11-01T12:06:00Z",
            "exact_prompt": "Who builds custom CRM and ERP software with AI integration in Ankara? Recommend a few companies and explain why.",
            "verbatim_answer": "The available results don't establish which Ankara companies specifically build both custom CRM/ERP systems and integrate AI, so I can't confidently recommend a few on that basis. Makrops is the clearest lead for AI-enabled custom software in Ankara; ElraTech is another for bespoke enterprise software.",
            "cited_urls": ["https://www.edvido.com/tr/yazilim-firmasi/ankara"],
            "raw_screenshot_path": "",
            "raw_screenshot_sha256": "",
            "session_url": "https://www.perplexity.ai/search/79733cdb-54c5-45eb-b53e-ec386f0dbb58",
            "note": "AI_SINGLE_TEST_OBSERVED_NO_RAW_SCREENSHOT_EXPORTED",
        },
    },
    "20261101-R02-121": {
        "company_name": "Detartech",
        "official_url": "https://detartech.com/",
        "contact_url": "https://wa.me/902165990097",
        "channel": "WA",
        "primary_service": "Istanbul MVP, mobile app and AI integration studio",
        "observed_site_fact": "Explicitly offers GEO services and describes client GEO work on its Turkish site.",
    },
    "20261101-R02-147": {
        "company_name": "Demircode",
        "official_url": "https://www.demircode.com/en/",
        "contact_url": "https://wa.me/905433264777",
        "contact_route_source": "https://www.demircode.com/en/",
        "channel": "WA",
        "primary_service": "custom web, mobile app, ERP and tourism platform development in Istanbul",
        "observed_site_fact": "Istanbul software studio operating since 2011 building custom web, mobile, ERP and tourism platforms.",
        "buyer_question": "Which Istanbul software studio builds custom web, ERP and tourism platforms for B2B clients?",
    },
    "20261101-R02-149": {
        "company_name": "KingIT Solutions",
        "official_url": "https://kingitsolutions.net/",
        "contact_url": "https://wa.me/447936968820",
        "contact_route_source": "https://kingitsolutions.net/",
        "channel": "WA",
        "primary_service": "blockchain smart-contract, Web3 and custom web/mobile software development",
        "observed_site_fact": "Provides web, mobile and Web3/crypto development services for UK, Hungarian and international markets.",
        "buyer_question": "Which blockchain and Web3 development agency builds custom smart contracts and web platforms?",
    },
    "20261101-R02-105": {
        "company_name": "Solman Digital",
        "official_url": "https://solmandigital.com/",
        "contact_url": "https://wa.me/905439675250",
        "contact_route_source": "https://solmandigital.com/contact",
        "channel": "WA",
        "primary_service": "SaaS MVP development and AI workflow automation in Istanbul",
        "observed_site_fact": "Official site offers Web/SaaS MVP builds and AI automation with direct WhatsApp project intake.",
        "buyer_question": "Which Istanbul development studio builds SaaS MVPs and AI automation workflows for startups?",
    },
    "20261101-R02-127": {
        "company_name": "Rihef Software & Consulting",
        "official_url": "https://rihef.com/en",
        "contact_url": "https://wa.me/902129090060",
        "contact_route_source": "https://rihef.com/contact",
        "channel": "WA",
        "primary_service": "B2B SaaS products and custom enterprise software consulting in Istanbul",
        "observed_site_fact": "Lists 8 in-house SaaS products alongside custom enterprise software consulting and WhatsApp desk.",
        "buyer_question": "Which Istanbul software consultancy builds both custom B2B software and production SaaS platforms?",
    },
    "20261101-R02-143": {
        "company_name": "SilverOps",
        "official_url": "https://silverops.io/",
        "channel": "UNASSIGNED",
        "primary_service": "high-load web platforms, e-commerce and AI integration",
        "observed_site_fact": "English-speaking web platform and AI integration studio; claims Astana Hub residency; no public WA/TG/FB route on homepage.",
    },
    "20261101-R02-122": {
        "company_name": "NAFRU",
        "official_url": "https://nafru.com/",
        "channel": "UNASSIGNED",
        "primary_service": "Istanbul corporate websites, SaaS and custom software development",
        "observed_site_fact": "Turkish and English site versions offering SaaS and custom software; contact form only.",
    },
    "20261101-R02-144": {
        "company_name": "ByteOn Technologies",
        "official_url": "https://www.byteonai.com/",
        "channel": "UNASSIGNED",
        "primary_service": "AI/ML and custom business software systems",
        "observed_site_fact": "Offers web/mobile and AI/ML solutions; contact form only without public WA/TG/FB route.",
    },
    "20261101-R02-088": {
        "company_name": "Triton Teknoloji",
        "official_url": "https://tritonteknoloji.com/en/",
        "alias_domains": ["nacstream.com", "siemstream.com"],
        "channel": "UNASSIGNED",
        "primary_service": "AI-driven cybersecurity platforms (NacStream, SiemStream, DataStream)",
        "observed_site_fact": "Ankara cybersecurity software vendor building NAC, SIEM and data security platforms; no public WA/TG/FB route.",
    },
    "20261101-R02-101": {
        "company_name": "PoxPen",
        "official_url": "https://www.poxpen.com/",
        "channel": "UNASSIGNED",
        "primary_service": "startup MVP, web/mobile and digital transformation consulting",
        "observed_site_fact": "Istanbul software studio offering startup MVP and digital transformation; no public WA/TG/FB route.",
    },
    "20261101-R02-113": {
        "company_name": "Smartup Network",
        "official_url": "https://smartup.network/",
        "channel": "UNASSIGNED",
        "primary_service": "technical partner building startup MVPs and AI products",
        "observed_site_fact": "Istanbul startup technical partner; no verified public WA/TG/FB business route.",
    },
    "20261101-R02-117": {
        "company_name": "Reorigin Technology",
        "official_url": "https://reorigintech.com/",
        "channel": "UNASSIGNED",
        "primary_service": "B2B custom software, SaaS, DaaS and AI automation",
        "observed_site_fact": "Founded 2026 in Istanbul; leadership page updated 2026-10-26; phone and email on contact page without official WA link.",
        "recent_30d_activity_status": "PASS_PAGE_UPDATED_2026-10-26",
        "recent_30d_activity_evidence": "Leadership page explicitly stamped Last updated: 26 October 2026.",
        "recent_30d_activity_url": "https://reorigintech.com/team",
    },
    "20261101-R02-080": {
        "company_name": "Citymatrix",
        "official_url": "https://citymatrix.com.tr/",
        "channel": "UNASSIGNED",
        "primary_service": "software engineering and maritime/data platforms (Laycan, Veridizin)",
        "observed_site_fact": "Ankara software engineering studio presenting Laycan and Veridizin platforms; email contact only.",
    },
    "20261101-R02-018": {
        "company_name": "Wavect GmbH",
        "official_url": "https://wavect.io/",
        "channel": "UNASSIGNED",
        "primary_service": "AI development and Web3 product engineering",
        "observed_site_fact": "Austrian/European Web3 and AI engineering studio; blog overview lists 2026 industry awards; no WA/TG/FB direct route.",
    },
    "20261101-R02-028": {
        "company_name": "BrightNode",
        "official_url": "https://brightnode.io/",
        "channel": "UNASSIGNED",
        "primary_service": "RWA tokenization, tokenomics consulting and Web3 marketing",
        "observed_site_fact": "Provides Web3 marketing and tokenomics advisory; has internal marketing capability (PARTNER track).",
    },
    "20261101-R02-096": {
        "company_name": "Zironsoft",
        "official_url": "https://zironsoft.com/",
        "contact_url": "https://www.facebook.com/profile.php?id=100083327779732",
        "contact_route_source": "https://zironsoft.com/",
        "channel": "FB",
        "primary_service": "enterprise software development, microservices and digital transformation in Ankara",
        "observed_site_fact": "Founded 2022 at Bilkent CyberPark Ankara; builds custom enterprise software and microservices.",
    },
    "20261101-R02-097": {
        "company_name": "FnF1 Teknoloji",
        "official_url": "https://www.fnf1.com.tr/en/",
        "contact_url": "https://www.facebook.com/fnf1teknoloji",
        "contact_route_source": "https://www.fnf1.com.tr/en/",
        "channel": "FB",
        "primary_service": "enterprise software, ERP integrations and AI development in Ankara",
        "observed_site_fact": "Ankara software company building custom ERP integrations and enterprise AI workflows.",
    },
    "20261101-R02-099": {
        "company_name": "ZeroHint",
        "official_url": "https://zerohint.com/",
        "contact_url": "https://www.facebook.com/zerohint",
        "contact_route_source": "https://zerohint.com/",
        "channel": "FB",
        "primary_service": "Unity game development and outsourced co-development",
        "observed_site_fact": "Remote-first Unity game development and co-development studio with 10 specialists.",
    },
    "20261101-R02-100": {
        "company_name": "Cool Digital Solutions",
        "official_url": "https://letsbecool.com/",
        "contact_url": "https://www.facebook.com/cooldigitalsolutions/",
        "contact_route_source": "https://letsbecool.com/",
        "channel": "FB",
        "primary_service": "AI-native digital product and innovation engineering",
        "observed_site_fact": "Istanbul digital product and AI innovation agency.",
    },
    "20261101-R02-109": {
        "company_name": "BWA Digital",
        "official_url": "https://www.bwa.com.tr/en",
        "contact_url": "https://www.facebook.com/bwadigital",
        "contact_route_source": "https://www.bwa.com.tr/en",
        "channel": "FB",
        "primary_service": "corporate web design, software, SEO and AI-agent services",
        "observed_site_fact": "Istanbul agency offering corporate web, SEO and AI-agent services (SEO peer overlap).",
    },
    "20261101-R02-126": {
        "company_name": "CRENNO",
        "official_url": "https://crenno.com/",
        "contact_url": "https://www.facebook.com/crennotech",
        "contact_route_source": "https://crenno.com/",
        "channel": "FB",
        "primary_service": "software engineering, IT consulting, AI/ML and blockchain R&D",
        "observed_site_fact": "Istanbul technology and software R&D studio operating since 2009.",
    },
    "20261101-R02-136": {
        "company_name": "LimonAgaci",
        "official_url": "https://www.limonagaci.com/",
        "contact_url": "https://www.facebook.com/limonagaciweb",
        "contact_route_source": "https://www.limonagaci.com/",
        "channel": "FB",
        "primary_service": "custom web/mobile applications, API integrations and SaaS development",
        "observed_site_fact": "Istanbul custom software and web/mobile app development studio.",
    },
    # Newly live-browsed small RAW candidates from RAW_checkpoint_resume02.json (2026-11-02)
    "20261101-R02-102": {
        "company_name": "Madebycat",
        "official_url": "https://madebycat.com/",
        "channel": "UNASSIGNED",
        "primary_service": "enterprise UX/UI design, web development and CMS transformation",
        "observed_site_fact": "Founded 2007 in Istanbul with Cambridge & Dubai offices; contact via hello@madebycat.com and project form (no WA/TG/FB link).",
    },
    "20261101-R02-118": {
        "company_name": "Crayn AI",
        "official_url": "https://www.crayn.ai/",
        "alias_domains": ["creodive.com"],
        "channel": "UNASSIGNED",
        "primary_service": "custom AI agents, WhatsApp chatbots, n8n workflow automation and web software",
        "observed_site_fact": "Istanbul AI studio ('Bir Creodive markasi'); explicitly states technical SEO for ChatGPT & Perplexity visibility.",
    },
    "20261101-R02-139": {
        "company_name": "Makrops Software",
        "official_url": "https://makrops.com/en/about",
        "channel": "UNASSIGNED",
        "primary_service": "digital twins, 3D visualization, custom web/mobile apps and enterprise AI",
        "observed_site_fact": "Founded 2024 in Istanbul; small senior team building digital twins, 3D visualization, web/mobile and RAG AI workflows.",
    },
    "20261101-R02-148": {
        "company_name": "Dexola",
        "official_url": "https://dexola.com/",
        "channel": "UNASSIGNED",
        "primary_service": "venture-grade AI product engineering and Web3 development",
        "observed_site_fact": "Venture-grade AI and Web3 product engineering studio.",
    },
    "20261101-R02-154": {
        "company_name": "Cyber Bee",
        "official_url": "https://cyberbee.dev/",
        "channel": "UNASSIGNED",
        "primary_service": "Web3 DeFi/RWA smart contracts, AI agents and 4-6 week startup MVPs",
        "observed_site_fact": "London Web3 & AI studio (Shukhrat Shadibekov CEO, Alex Topal CTO); 40+ products shipped; contact via hello@cyberbee.dev & consultation form.",
        "recent_30d_activity_status": "OBSERVED_2026_BLOG",
        "recent_30d_activity_evidence": "Blog posts dated May & July 2026 on AI Agents for DeFi Fund Automation.",
    },
    "20261101-R02-155": {
        "company_name": "Mifort",
        "official_url": "https://mifort.com/",
        "channel": "UNASSIGNED",
        "primary_service": "web, mobile and blockchain software development teams",
        "observed_site_fact": "Provides dedicated web, mobile and blockchain engineering teams.",
    },
    "20261101-R02-157": {
        "company_name": "Tesseract Academy",
        "official_url": "https://tesseract.academy/",
        "channel": "UNASSIGNED",
        "primary_service": "executive AI consulting, Agentic Flywheel and data science training",
        "observed_site_fact": "UK AI consulting & training firm led by Dr Stylianos Kampakis; offers AI Readiness Assessment and Agentic Flywheel.",
    },
    "20261101-R02-167": {
        "company_name": "MLabs Ltd",
        "official_url": "https://www.mlabs.city/",
        "channel": "UNASSIGNED",
        "primary_service": "Haskell, Rust, Cardano formal verification and AI-accelerated engineering",
        "observed_site_fact": "London high-assurance engineering consultancy specializing in Haskell, Rust, Cardano audits and AI verification.",
    },
    "20261101-R02-173": {
        "company_name": "Nordstone",
        "official_url": "https://nordstone.co.uk/",
        "channel": "UNASSIGNED",
        "primary_service": "AI-powered mobile and web application development in London",
        "observed_site_fact": "UK technology studio specializing in AI-powered mobile and web apps; blog active August 2026.",
    },
    "20261101-R02-180": {
        "company_name": "Techloyce LTD",
        "official_url": "https://www.techloyce.com/about/",
        "channel": "UNASSIGNED",
        "primary_service": "Zoho, Odoo, HubSpot and SugarAI CRM consulting, migration and integration",
        "observed_site_fact": "UK/US/Canada CRM & ERP consultancy with 100+ Zoho, Odoo and HubSpot implementations.",
    },
}

# Regulated Retail Experiment Candidates (Requirement 11: strictly RESEARCH_ONLY)
REGULATED_RETAIL_RECORDS: list[dict[str, Any]] = [
    {
        "original_prospect_id": "R-20261101-001",
        "company_name": "The Solent Cellar",
        "discovery_source_url": "https://www.vindependents.co.uk/",
        "raw_source_dataset": "20261101_regulated_retail_pilot",
        "official_url": "https://thesolentcellar.co.uk/",
        "canonical_domain": "thesolentcellar.co.uk",
        "country_or_region": "UK",
        "claimed_size_range": "2 - 9",
        "segment": "REGULATED_RETAIL_RESEARCH",
        "retail_category": "wine",
        "channel": "WA",
        "contact_url": "https://thesolentcellar.co.uk/contact/",
        "primary_service": "Independent wine merchant in Lymington (storefront & UK delivery)",
        "observed_site_fact": "Independent specialist wine merchant in Lymington; member of Vindependents; no verified WhatsApp route.",
        "is_retail_research": True,
    },
    {
        "original_prospect_id": "R-20261101-002",
        "company_name": "Bear's Vapes",
        "discovery_source_url": "https://www.gov.uk/government/publications/tobacco-products-and-e-cigarette-cross-border-sales-registration/list-of-registered-retailers",
        "raw_source_dataset": "20261101_regulated_retail_pilot",
        "official_url": "https://bearsvapes.co.uk/",
        "canonical_domain": "bearsvapes.co.uk",
        "country_or_region": "UK",
        "claimed_size_range": "2 - 9",
        "segment": "REGULATED_RETAIL_RESEARCH",
        "retail_category": "vape",
        "channel": "WA",
        "contact_url": "https://bearsvapes.co.uk/pages/bears-vapes-contact",
        "primary_service": "Family-run independent vape retailer in Leven, Fife",
        "observed_site_fact": "Registered UK independent vape retailer in Fife; contact page only; requires age/platform compliance review.",
        "is_retail_research": True,
    },
    {
        "original_prospect_id": "R-20261101-003",
        "company_name": "Scandals",
        "discovery_source_url": "https://www.barrelofpain.co.uk/find-us",
        "raw_source_dataset": "20261101_regulated_retail_pilot",
        "official_url": "https://scandals.love/",
        "canonical_domain": "scandals.love",
        "country_or_region": "UK",
        "claimed_size_range": "2 - 9",
        "location_count": 3,
        "segment": "REGULATED_RETAIL_RESEARCH",
        "retail_category": "adult",
        "channel": "WA",
        "contact_url": "https://scandals.love/pages/contact-us",
        "primary_service": "Adult retailer with 3 Merseyside outlets",
        "observed_site_fact": "Operates 3 local outlets (exceeds 1-2 store rule) and homepage returned Site Unavailable in cloud browser.",
        "is_retail_research": True,
    },
]


def load_all_raw_and_checkpoint_candidates(downloads_dir: Path) -> list[CandidateRecord]:
    """Load and merge all real RAW candidate pools while preserving original_prospect_id."""
    records_by_id: dict[str, CandidateRecord] = {}
    domain_to_id: dict[str, str] = {}

    # 1. Load 181 RAW records from RAW_checkpoint_resume02.json
    raw_r02_path = downloads_dir / "RAW_checkpoint_resume02.json"
    if raw_r02_path.exists():
        r02_data = json.loads(raw_r02_path.read_text(encoding="utf-8"))
        for row in r02_data.get("rows", []):
            pid = row.get("id", "")
            if not pid:
                continue
            section = row.get("section", "")
            # Extract service summary from Clutch/GoodFirms directory excerpt
            lines = [ln.strip() for ln in section.splitlines() if ln.strip() and not ln.strip().startswith("* ###")]
            summary = " ".join(lines[:6])[:240]
            rec = CandidateRecord(
                original_prospect_id=pid,
                company_name=row.get("name", ""),
                discovery_source_url=row.get("source", ""),
                discovery_channel="independent_directory",
                raw_source_dataset="RAW_checkpoint_resume02.json",
                claimed_size_range=row.get("size", ""),
                primary_service=summary,
                matched_history_sources=["RAW_CHECKPOINT_HISTORY_HIT"] if row.get("history_name_hit") else [],
            )
            records_by_id[pid] = rec

    # 2. Merge 20 enriched records from ENRICHED_CHECKPOINT_R02_v03.json
    enr_r02_path = downloads_dir / "ENRICHED_CHECKPOINT_R02_v03.json"
    if enr_r02_path.exists():
        enr_data = json.loads(enr_r02_path.read_text(encoding="utf-8"))
        for r in enr_data.get("records", []):
            pid = r.get("original_prospect_id", "")
            if not pid:
                continue
            rec = records_by_id.get(pid) or CandidateRecord(
                original_prospect_id=pid,
                company_name=r.get("company", ""),
                discovery_source_url=r.get("discovery_directory", ""),
                raw_source_dataset="ENRICHED_CHECKPOINT_R02_v03.json",
                claimed_size_range=r.get("directory_size", ""),
            )
            if r.get("proposed_official_url"):
                rec.official_url = r["proposed_official_url"]
            if r.get("official_domain"):
                rec.canonical_domain = normalize_domain_key(r["official_domain"])
                if rec.canonical_domain:
                    domain_to_id[rec.canonical_domain] = pid
            for pe in r.get("page_evidence", []):
                if pe.get("text") and not rec.observed_site_fact:
                    clean_txt = " ".join(pe["text"].split())[:280]
                    rec.observed_site_fact = f"Title: {pe.get('title', '')}. Excerpt: {clean_txt}"
                for lnk in pe.get("links", []):
                    if isinstance(lnk, str) and lnk not in rec.all_public_links:
                        rec.all_public_links.append(lnk)
            records_by_id[pid] = rec

    # 3. Merge work_research_queue_20261102.json & hold_reject_queue_20261102.json
    for q_file, q_key in [("work_research_queue_20261102.json", "queue"), ("hold_reject_queue_20261102.json", "hold")]:
        qp = downloads_dir / q_file
        if qp.exists():
            qdata = json.loads(qp.read_text(encoding="utf-8"))
            for r in qdata.get(q_key, []):
                pid = r.get("original_prospect_id", "")
                if not pid:
                    continue
                rec = records_by_id.get(pid) or CandidateRecord(
                    original_prospect_id=pid,
                    company_name=r.get("company", ""),
                    discovery_source_url=r.get("discovery_url", ""),
                    raw_source_dataset=q_file,
                    claimed_size_range=r.get("directory_size", ""),
                )
                if r.get("official_url"):
                    rec.official_url = r["official_url"]
                if r.get("domain"):
                    rec.canonical_domain = normalize_domain_key(r["domain"])
                    if rec.canonical_domain:
                        domain_to_id[rec.canonical_domain] = pid
                if r.get("observed_site_excerpt") and not rec.observed_site_fact:
                    rec.observed_site_fact = " ".join(r["observed_site_excerpt"].split())[:280]
                if r.get("activity") and r["activity"] != "UNKNOWN":
                    rec.recent_30d_activity_status = r["activity"]
                for lnk in r.get("public_links", []):
                    if isinstance(lnk, str) and lnk not in rec.all_public_links:
                        rec.all_public_links.append(lnk)
                records_by_id[pid] = rec

    # 4. Merge curated enrichments from 2026-11-01 & 2026-11-02 research docs & live browse
    for pid, info in CURATED_ENRICHMENTS.items():
        rec = records_by_id.get(pid)
        if not rec:
            continue
        if info.get("official_url"):
            rec.official_url = info["official_url"]
            rec.canonical_domain = normalize_domain_key(info["official_url"])
            if rec.canonical_domain:
                domain_to_id[rec.canonical_domain] = pid
        if info.get("contact_url"):
            rec.contact_url = info["contact_url"]
            if info["contact_url"] not in rec.all_public_links:
                rec.all_public_links.insert(0, info["contact_url"])
        if info.get("contact_route_source"):
            rec.contact_route_source = info["contact_route_source"]
        if info.get("channel") and info["channel"] != "UNASSIGNED":
            rec.channel = info["channel"]
        if info.get("alias_domains"):
            for ad in info["alias_domains"]:
                if ad not in rec.alias_domains:
                    rec.alias_domains.append(ad)
        if info.get("primary_service"):
            rec.primary_service = info["primary_service"]
        if info.get("observed_site_fact"):
            rec.observed_site_fact = info["observed_site_fact"]
        if info.get("recent_30d_activity_status"):
            rec.recent_30d_activity_status = info["recent_30d_activity_status"]
        if info.get("recent_30d_activity_evidence"):
            rec.recent_30d_activity_evidence = info["recent_30d_activity_evidence"]
        if info.get("recent_30d_activity_url"):
            rec.recent_30d_activity_url = info["recent_30d_activity_url"]
        if info.get("buyer_question"):
            rec.buyer_question = info["buyer_question"]
        if info.get("ai_test"):
            rec.ai_test = AITestRecord(**info["ai_test"])

    # 5. Load directory_raw_pool_154.csv + unpacked browser evidence (batch1, batch2, mt7)
    pool154_path = downloads_dir / "directory_raw_pool_154.csv"
    batch1_dir = downloads_dir / "unpacked_evidence/batch1"
    batch2_dir = downloads_dir / "unpacked_evidence/batch2"
    mt7_dir = downloads_dir / "unpacked_evidence/mt7"

    # Build domain -> unpacked browser capture index
    browser_captures: dict[str, dict[str, Any]] = {}
    for folder in (batch1_dir, batch2_dir):
        if not folder.exists():
            continue
        for jp in sorted(folder.glob("*.json")):
            if jp.name.isupper():
                continue
            try:
                d = json.loads(jp.read_text(encoding="utf-8"))
            except Exception:
                continue
            url = d.get("url") or ""
            dom = normalize_domain_key(url)
            if not dom:
                continue
            entry = browser_captures.setdefault(dom, {"url": url, "links": [], "jpg": "", "txt": ""})
            for l in d.get("links", []):
                href = l.get("href") if isinstance(l, dict) else l
                if isinstance(href, str) and href.startswith("https://") and href not in entry["links"]:
                    entry["links"].append(href)
            stem = jp.stem
            jpg_candidate = folder / f"{stem}.jpg"
            txt_candidate = folder / f"{stem}.txt"
            if jpg_candidate.exists() and jpg_candidate.stat().st_size > 5000 and not entry["jpg"]:
                entry["jpg"] = str(jpg_candidate)
            if txt_candidate.exists() and txt_candidate.stat().st_size > 200 and not entry["txt"]:
                entry["txt"] = txt_candidate.read_text(encoding="utf-8", errors="replace")[:400]

    # Add Mt7 Private Limited (from 2026-10-31 independent DSCE + GoodFirms + batch2 archive)
    if (batch2_dir / "mt7_resort_service.jpg").exists():
        mt7_id = "20261031-RAW-MT7"
        mt7_jpg = str(batch2_dir / "mt7_resort_service.jpg")
        records_by_id[mt7_id] = CandidateRecord(
            original_prospect_id=mt7_id,
            company_name="Mt7 Private Limited",
            discovery_source_url="https://www.goodfirms.co/company/mt7-pvt-ltd",
            discovery_channel="independent_directory",
            raw_source_dataset="MultiHub_continuation_run02_delta.zip",
            official_url="https://mt7.io/industries/resorts-and-homestays",
            canonical_domain="mt7.io",
            alias_domains=["mt7.in"],
            country_or_region="India",
            claimed_size_range="2 - 9",
            estimated_min_employees=7,
            estimated_max_employees=7,
            channel="WA",
            contact_url="https://wa.me/917800007500",
            contact_route_source="https://mt7.io/locations/bengaluru",
            all_public_links=["https://wa.me/917800007500"],
            recipient_name="Abdul Adnan",
            recipient_role="Founder (verified on mt7.io contact modal)",
            recipient_verified=True,
            primary_service="direct resort booking websites with Razorpay and two-way eZee PMS sync",
            observed_site_fact="Official resort service page documents direct booking engine with Razorpay and two-way eZee property-management sync; About page lists 7-person team led by founder Abdul Adnan; blog post dated 30 October 2026.",
            recent_30d_activity_status="PASS_COMPANY_BLOG_2026-10-30",
            recent_30d_activity_evidence="Company blog post published 30 October 2026.",
            recent_30d_activity_url="https://mt7.io/blog",
            buyer_question="Which Indian developer can build a direct resort booking site with Razorpay and two-way eZee PMS sync?",
            raw_web_screenshot_path=mt7_jpg,
            raw_web_screenshot_sha256=compute_file_sha256(Path(mt7_jpg)),
        )
        domain_to_id["mt7.io"] = mt7_id

    if pool154_path.exists():
        with pool154_path.open(encoding="utf-8", errors="replace") as f:
            reader = list(csv.reader(f))
        for idx, row in enumerate(reader[1:], 1):
            if len(row) < 2:
                continue
            cname = row[0].strip().lstrip("\ufeff")
            dom = normalize_domain_key(row[1].strip())
            page_ref = row[2].strip() if len(row) > 2 else "page_1"
            prelim_hit = (len(row) > 3 and row[3].strip() == "是")
            if not cname or not dom or dom in domain_to_id:
                continue
            pid = f"20261031-DIR154-{idx:03d}"
            cap = browser_captures.get(dom, {})
            off_url = cap.get("url") or f"https://{dom}/"
            clean_txt = " ".join((cap.get("txt") or "").split())[:260]
            jpg_path = cap.get("jpg") or ""
            rec = CandidateRecord(
                original_prospect_id=pid,
                company_name=cname,
                discovery_source_url=f"https://clutch.co/developers/artificial-intelligence?page={page_ref}",
                discovery_channel="independent_directory",
                raw_source_dataset="directory_raw_pool_154.csv",
                official_url=off_url,
                canonical_domain=dom,
                claimed_size_range="10 - 49",
                all_public_links=list(cap.get("links", [])),
                primary_service="custom software, AI and web/mobile product engineering" if clean_txt else "",
                observed_site_fact=f"Archived browser capture from {off_url}: {clean_txt}" if clean_txt else "",
                raw_web_screenshot_path=jpg_path,
                raw_web_screenshot_sha256=compute_file_sha256(Path(jpg_path)) if jpg_path else "",
                matched_history_sources=["DIR154_V3_QA_HISTORY_HIT"] if prelim_hit else [],
            )
            # Enrich known deep-checked batch2 companies
            if dom == "neuradynamics.ai":
                rec.claimed_size_range = "10 - 20"
                rec.primary_service = "AI customer support automation and human-handoff agents"
                rec.observed_site_fact = "Official service page & 23 Oct 2026 blog record AI customer support automation; co-founders Himanshu Srivastava & Abhilasha Roopam."
                rec.recent_30d_activity_status = "PASS_COMPANY_BLOG_2026-10-23"
                rec.recent_30d_activity_evidence = "Blog article dated 23 October 2026 on AI Customer Support Automation."
                rec.recent_30d_activity_url = "https://neuradynamics.ai/blogs/ai-customer-support-automation-2026-benefits"
                rec.buyer_question = "Which AI engineering team builds customer-support agents with human handoff and CRM integration?"
                if (batch2_dir / "neura_service.jpg").exists():
                    rec.raw_web_screenshot_path = str(batch2_dir / "neura_service.jpg")
                    rec.raw_web_screenshot_sha256 = compute_file_sha256(batch2_dir / "neura_service.jpg")
            elif dom == "bixtech.co":
                rec.claimed_size_range = "2 - 9"
                rec.primary_service = "AI workflow automation and custom business software in Malaysia"
                rec.buyer_question = "Which Malaysia AI consultancy builds custom business workflow automation?"
            elif dom == "dfkdigitals.com":
                rec.claimed_size_range = "2 - 9"
                rec.primary_service = "custom web platforms and digital product engineering in Brazil"
                rec.buyer_question = "Which software studio builds custom web platforms and digital products for SMBs?"
            elif dom == "jaraware.com":
                rec.claimed_size_range = "10 - 49"
                rec.primary_service = "custom mobile app, web and enterprise software development"
                rec.buyer_question = "Which software team delivers custom mobile and web applications with direct engineering support?"
            elif dom == "hkinfosoft.com":
                rec.claimed_size_range = "10 - 49"
                rec.primary_service = "custom web, Laravel/React and mobile app development in Ahmedabad"
                rec.buyer_question = "Which Ahmedabad web and mobile development agency builds custom Laravel and React platforms?"
            elif dom == "snsoftwares.com":
                rec.claimed_size_range = "10 - 49"
                rec.alias_domains = ["snsoftware.in"]
                rec.primary_service = "WhatsApp CRM integration and custom business software"
                rec.buyer_question = "Which software provider builds custom WhatsApp CRM and AI chatbot integrations?"
            elif dom == "bitronix.ai":
                rec.claimed_size_range = "10 - 49"
                rec.primary_service = "AI software development and enterprise automation"
                rec.buyer_question = "Which AI development firm builds custom enterprise AI and software systems?"
            elif dom == "creativesite.in":
                rec.claimed_size_range = "2 - 9"
                rec.primary_service = "custom web design and software development services in India"
                rec.buyer_question = "Which small Indian web development studio builds custom business websites and web apps?"

            records_by_id[pid] = rec
            domain_to_id[dom] = pid

    # 6. Merge 2026-10-29 27 candidate manifest (D29-WA01..15, D29-TG01..02, D29-FB01..10)
    d29_path = Path("/working_dir/c_3134177ccee79b95/agent_sandbox/tool_output_artifacts/ttl=3d/drive:read_file_content_aa692d28.txt")
    if d29_path.exists():
        try:
            raw_txt = d29_path.read_text(encoding="utf-8", errors="replace")
            # Parse JSON inside tool output or raw JSON text
            idx_brace = raw_txt.find("{")
            if idx_brace >= 0:
                clean_json = raw_txt[idx_brace:].replace("\_", "_").replace("\[", "[").replace("\]", "]")
                d29 = json.loads(clean_json)
                for item in d29.get("records", []):
                    pid = item.get("observation_id", "")
                    dom = normalize_domain_key(item.get("website", ""))
                    if not pid or not dom or dom in domain_to_id:
                        continue
                    rec = CandidateRecord(
                        original_prospect_id=pid,
                        company_name=item.get("company", ""),
                        discovery_source_url="https://clutch.co/developers/artificial-intelligence",
                        discovery_channel="independent_directory",
                        raw_source_dataset="MultiHub_V3_20261029_source_manifest",
                        official_url=item.get("website", ""),
                        canonical_domain=dom,
                        claimed_size_range="2 - 9",
                        channel=item.get("channel", "UNASSIGNED"),
                        contact_url=item.get("public_contact_url") or "",
                        contact_route_source=item.get("source_url") or item.get("website", ""),
                        all_public_links=[item["public_contact_url"]] if item.get("public_contact_url") else [],
                        primary_service=item.get("buyer_task", ""),
                        observed_site_fact=item.get("observed_fact", ""),
                        buyer_question=f"Which specialist team provides {item.get('buyer_task', 'this service')} with clear deliverables and handover?",
                    )
                    if item.get("recipient_verification") == "FOUNDER_DIRECT_PERSONAL_TG_VERIFIED":
                        rec.recipient_verified = True
                    records_by_id[pid] = rec
                    domain_to_id[dom] = pid
        except Exception:
            pass

    # 7. Append the 3 Regulated Retail Research Experiment candidates (R-20261101-001..003)
    for r_dict in REGULATED_RETAIL_RECORDS:
        pid = r_dict["original_prospect_id"]
        records_by_id[pid] = CandidateRecord(**r_dict)

    return list(records_by_id.values())
