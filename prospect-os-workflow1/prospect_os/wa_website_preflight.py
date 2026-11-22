"""WA-only, public website route preflight. No WhatsApp login, probes or sending."""
from __future__ import annotations

import io
import re
import shutil
from typing import Any
from urllib.parse import urlsplit, parse_qs

from .contact_enrichment import enrich_record, fetch_html
from .source_pool import canonical_domain, public_http_url, USER_AGENT


def valid_wa_candidate(url: str) -> bool:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or host not in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
        return False
    path = p.path.strip("/")
    if host == "wa.me" and re.fullmatch(r"message/[a-zA-Z0-9]{6,}", path):
        return True
    digits = path if host == "wa.me" else (parse_qs(p.query).get("phone") or [""])[0].lstrip("+")
    return bool((host == "wa.me" or path == "send") and re.fullmatch(r"[1-9]\d{6,14}", digits) and not digits.endswith("0000000000"))


def decode_public_qr(png: bytes) -> list[str]:
    import zxingcpp
    from PIL import Image
    return [code.text for code in zxingcpp.read_barcodes(Image.open(io.BytesIO(png)))
            if valid_wa_candidate(code.text)]


def render_public_page(url: str) -> tuple[str, str, list[str]]:
    """Render public first-party content only. No credentials, clicks or POSTs."""
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError as exc:
        raise RuntimeError("playwright_not_installed") from exc
    if not public_http_url(url):
        raise RuntimeError("non_public_render_url")
    domain = canonical_domain(url)
    try:
        with sync_playwright() as pw:
            executable = shutil.which("chromium") or shutil.which("chromium-browser")
            browser = pw.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
            try:
                ctx = browser.new_context(user_agent=USER_AGENT, service_workers="block", accept_downloads=False)
                ctx.route("**/*", lambda route: route.continue_() if (route.request.method == "GET"
                          and canonical_domain(route.request.url) == domain and public_http_url(route.request.url)) else route.abort())
                page = ctx.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if response is None or response.status >= 400 or canonical_domain(page.url) != domain:
                    raise RuntimeError("public_render_unavailable_or_blocked")
                page.wait_for_timeout(800)
                qr_urls: list[str] = []
                images = page.locator('img[alt*="whatsapp" i], img[title*="whatsapp" i], img[alt*="qr" i], img[src*="qrcode" i]')
                for i in range(min(images.count(), 4)):
                    image = images.nth(i)
                    if image.is_visible():
                        try:
                            qr_urls.extend(decode_public_qr(image.screenshot(timeout=1500)))
                        except (Error, OSError, ValueError):
                            continue
                return page.content(), page.url, list(dict.fromkeys(qr_urls))
            finally:
                browser.close()
    except (Error, ImportError) as exc:
        raise RuntimeError(f"render_unavailable: {type(exc).__name__}") from exc


def preflight_website(record: dict[str, Any], *, render: bool = True, **kwargs: Any) -> dict[str, Any]:
    """Keep route discovery separate from recipient, registration, history and consent."""
    options = {"max_pages": 5, "delay_seconds": 0.25,
               "fetcher": lambda url: fetch_html(url, timeout=8, max_bytes=750_000),
               "render_fetcher": render_public_page if render else None}
    options.update(kwargs)
    result = enrich_record(record, **options)
    routes = [c for c in result["contacts"] if c.get("channel") == "whatsapp" and valid_wa_candidate(c.get("value", ""))]
    def rank(c: dict[str, Any]) -> tuple[bool, bool]:
        return (not bool(c.get("route_verification_status")),
                (c.get("outreach_route") or {}).get("purpose") in {"decision_maker", "partnerships", "sales"})
    routes.sort(key=rank, reverse=True)
    result["wa_routes"] = routes
    result["wa_preflight_status"] = ("OFFICIAL_LINK_FOUND" if any(not c.get("route_verification_status") for c in routes)
                                     else "LABELLED_NUMBER_REVIEW" if routes else
                                     "HOLD_ACCESS" if result["contact_enrichment_errors"] else "NO_ROUTE_OBSERVED")
    result["wa_account_verified"] = False
    result["recipient_opt_in_status"] = "UNKNOWN"
    result["send_ready"] = False
    return result
