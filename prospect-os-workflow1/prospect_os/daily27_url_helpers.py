"""Stable URL helpers for Daily27. Does not alter the legacy website resolver."""
from __future__ import annotations
from urllib.parse import urlsplit

SEARCH_ENGINE_DOMAINS = {"google.com","bing.com","duckduckgo.com","baidu.com","yandex.com","yahoo.com"}

def extract_domain(url: str) -> str:
    if not url:
        return ""
    val = str(url).strip()
    if not val:
        return ""
    if "://" not in val:
        val = "https://" + val
    try:
        return (urlsplit(val).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""

def is_search_engine(url: str) -> bool:
    domain = extract_domain(url)
    return any(domain == host or domain.endswith("." + host) for host in SEARCH_ENGINE_DOMAINS)
