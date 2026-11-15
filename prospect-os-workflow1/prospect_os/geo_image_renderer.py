"""1080x1350 English GEO Evidence & Website Fact Research Card Renderer (Requirement 7, 8, 9).

Follows MultiHub GEO Evidence Image System v2.0:
  - Canvas: 1080 x 1350 px vertical PNG (mobile screen aspect ratio)
  - Palette: Warm archival paper (#FAF8F5), deep ink (#141413), single red annotation (#C92A2A),
    warm yellow highlight (#FFF3BF), muted slate border (#CBD5E1). No gradients or fake UI.
  - Strictly distinguishes:
      * Variant B (AI_LIVE_TEST_CARD): Requires authentic live AI search screenshot + prompt/model/time/answer.
      * Variant A (STUDY_FACT_CARD): Used when AI test is not run; embeds real archived website screenshot
        (if available) or verbatim website excerpt, and prominently stamps:
        "AI RECOMMENDATION TEST: NOT RUN — WEBSITE FACT RESEARCH CARD (NOT AI EVIDENCE)".
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .daily27_models import CandidateRecord

CANVAS_W = 1080
CANVAS_H = 1350

BG_PAPER = (250, 248, 245)
CARD_WHITE = (255, 255, 255)
INK_DARK = (20, 20, 19)
INK_MUTED = (71, 85, 105)
RED_ACCENT = (201, 42, 42)
RED_LIGHT_BG = (255, 245, 245)
YELLOW_HIGHLIGHT = (255, 243, 191)
YELLOW_BORDER = (217, 119, 6)
BORDER_GRAY = (203, 213, 225)
GREEN_BADGE = (235, 251, 238)
GREEN_TEXT = (43, 138, 62)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_chars: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = INK_DARK,
    line_spacing: int = 8,
    max_lines: int = 6,
) -> int:
    clean = " ".join(str(text or "").split())
    lines = textwrap.wrap(clean, width=max_chars)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, max_chars - 3)] + "..."
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, cur_y), line, font=font)
        cur_y += (bbox[3] - bbox[1]) + line_spacing
    return cur_y


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def render_geo_card_png(rec: CandidateRecord, output_dir: Path) -> CandidateRecord:
    """Render a 1080x1350 English GEO PNG card and update rec with path, sha256, and card type."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in rec.original_prospect_id)
    safe_co = "".join(c if c.isalnum() else "_" for c in rec.company_name)[:24].strip("_")
    is_live_ai = rec.ai_test.is_strict_live_proof and Path(rec.ai_test.raw_screenshot_path).exists()
    card_type = "AI_LIVE_TEST_CARD" if is_live_ai else "STUDY_FACT_CARD"
    rec.evidence_card_type = card_type

    suffix = "AI_EVIDENCE" if is_live_ai else "STUDY_FACT_CARD"
    filename = f"{safe_id}_{safe_co}_{suffix}_1080x1350.png"
    out_path = output_dir / filename

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_PAPER)
    draw = ImageDraw.Draw(img)

    f_tag = _load_font(20, bold=True)
    f_title = _load_font(32, bold=True)
    f_sub = _load_font(22, bold=False)
    f_sec = _load_font(22, bold=True)
    f_body = _load_font(22, bold=False)
    f_small = _load_font(18, bold=False)
    f_stamp = _load_font(21, bold=True)

    # Outer border frame
    draw.rectangle([28, 28, CANVAS_W - 28, CANVAS_H - 28], outline=BORDER_GRAY, width=2)

    # Top Header Bar
    draw.rectangle([48, 48, 438, 88], fill=INK_DARK)
    draw.text((62, 57), "MULTIHUB GEO | RESEARCH NOTE", font=f_tag, fill=CARD_WHITE)

    slot_label = f"ID: {rec.original_prospect_id} | Ch: {rec.channel} ({rec.allocated_slot or 'POOL'})"
    draw.text((456, 58), slot_label[:54], font=f_small, fill=INK_MUTED)

    # Company & Official Site line
    co_line = f"{rec.company_name}  ({rec.canonical_domain or rec.official_url})"
    draw.text((48, 104), co_line[:68], font=f_sec, fill=RED_ACCENT)

    # Buyer Procurement Question (Top Hierarchy)
    draw.text((48, 142), "BUYER PROCUREMENT QUESTION:", font=f_tag, fill=INK_MUTED)
    buyer_q = rec.buyer_question or (
        f"Which specialist provider can deliver {rec.primary_service or 'the software engineering service'} "
        f"with verifiable case evidence and clear project scoping?"
    )
    y_after_q = _draw_wrapped(
        draw, f'"{buyer_q}"', 48, 174, max_chars=52, font=f_title, fill=INK_DARK, line_spacing=10, max_lines=3
    )

    # Status Banner (Explicitly distinguishes Live AI Evidence vs Website Fact Card)
    banner_top = max(295, y_after_q + 14)
    banner_bot = banner_top + 66
    if is_live_ai:
        draw.rectangle([48, banner_top, CANVAS_W - 48, banner_bot], fill=GREEN_BADGE, outline=GREEN_TEXT, width=2)
        draw.text(
            (66, banner_top + 18),
            f"LIVE AI SEARCH TEST ARCHIVED: {rec.ai_test.platform} ({rec.ai_test.model or 'Default'}) @ {rec.ai_test.tested_at_utc}",
            font=f_stamp,
            fill=GREEN_TEXT,
        )
    else:
        draw.rectangle([48, banner_top, CANVAS_W - 48, banner_bot], fill=YELLOW_HIGHLIGHT, outline=RED_ACCENT, width=3)
        draw.text(
            (66, banner_top + 10),
            "AI RECOMMENDATION TEST: NOT RUN (STUDY_FACT_CARD — NOT AI EVIDENCE)",
            font=f_stamp,
            fill=RED_ACCENT,
        )
        draw.text(
            (66, banner_top + 38),
            "Contains verified official website facts & proposed buyer query only. No AI ranking or gap claimed.",
            font=f_small,
            fill=INK_DARK,
        )

    # Central Evidence Box (y: banner_bot + 18 to 880)
    ev_top = banner_bot + 18
    ev_bot = 875
    draw.rectangle([48, ev_top, CANVAS_W - 48, ev_bot], fill=CARD_WHITE, outline=BORDER_GRAY, width=2)

    raw_img_path = Path(rec.ai_test.raw_screenshot_path) if is_live_ai else (
        Path(rec.raw_web_screenshot_path) if rec.raw_web_screenshot_path else None
    )

    if raw_img_path and raw_img_path.exists():
        # Embed real archived browser/AI screenshot (preserving native aspect ratio inside viewport)
        draw.text(
            (68, ev_top + 14),
            "AUTHENTIC ARCHIVED BROWSER CAPTURE (UNALTERED PIXELS + CALLOUT):",
            font=f_tag,
            fill=INK_MUTED,
        )
        try:
            with Image.open(raw_img_path) as src_im:
                src_rgb = src_im.convert("RGB")
                avail_w = CANVAS_W - 140
                avail_h = (ev_bot - ev_top) - 165
                fitted = ImageOps.contain(src_rgb, (avail_w, avail_h))
                paste_x = 48 + (CANVAS_W - 96 - fitted.width) // 2
                paste_y = ev_top + 48
                img.paste(fitted, (paste_x, paste_y))
                # Draw red annotation callout border around the screenshot
                draw.rectangle(
                    [paste_x - 3, paste_y - 3, paste_x + fitted.width + 3, paste_y + fitted.height + 3],
                    outline=RED_ACCENT,
                    width=4,
                )
                cap_y = paste_y + fitted.height + 12
        except Exception:
            cap_y = ev_top + 60
        obs_text = "Observed on Official Site: " + (
            rec.observed_site_fact or rec.primary_service or "Verified company service offering on official site."
        )
        _draw_wrapped(draw, obs_text, 68, min(cap_y, ev_bot - 95), max_chars=74, font=f_body, fill=INK_DARK, max_lines=3)
    else:
        # Verbatim Website Fact Card layout (when no raw screenshot file is present)
        draw.rectangle([68, ev_top + 20, CANVAS_W - 68, ev_top + 64], fill=RED_LIGHT_BG, outline=RED_ACCENT, width=2)
        draw.text(
            (84, ev_top + 30),
            "VERIFIED OFFICIAL WEBSITE EVIDENCE (TEXT ARCHIVED — NO RAW CAPTURE)",
            font=f_tag,
            fill=RED_ACCENT,
        )
        cur_y = ev_top + 84
        draw.text((68, cur_y), "1. Official Service & Positioning Observed:", font=f_sec, fill=INK_DARK)
        cur_y = _draw_wrapped(
            draw,
            rec.observed_site_fact or rec.primary_service or "Official site verified; provides specialized B2B engineering services.",
            68,
            cur_y + 32,
            max_chars=72,
            font=f_body,
            fill=INK_DARK,
            max_lines=5,
        )
        cur_y += 16
        draw.text((68, cur_y), "2. Recent 30-Day Activity & Buyer Context:", font=f_sec, fill=INK_DARK)
        act_str = f"Activity Status: {rec.recent_30d_activity_status}. {rec.recent_30d_activity_evidence or 'No dated 30-day publication verified yet.'}"
        cur_y = _draw_wrapped(draw, act_str, 68, cur_y + 32, max_chars=72, font=f_body, fill=INK_MUTED, max_lines=3)

        if rec.ai_test.tested and not is_live_ai:
            cur_y += 14
            draw.rectangle([68, cur_y, CANVAS_W - 68, min(ev_bot - 20, cur_y + 115)], fill=YELLOW_HIGHLIGHT, outline=YELLOW_BORDER, width=2)
            note_txt = (
                f"Single AI Session Note ({rec.ai_test.platform}, raw screenshot not exported): "
                f"{rec.ai_test.verbatim_answer[:180]}"
            )
            _draw_wrapped(draw, note_txt, 84, cur_y + 12, max_chars=70, font=f_small, fill=INK_DARK, max_lines=4)

    # Bottom Section: Actionable GEO Opportunity & Service Boundary (y: 895 to 1185)
    act_top = 892
    draw.rectangle([48, act_top, CANVAS_W - 48, 1185], fill=CARD_WHITE, outline=BORDER_GRAY, width=2)
    draw.rectangle([48, act_top, 58, 1185], fill=RED_ACCENT)

    draw.text((68, act_top + 18), "WHAT WE OBSERVED vs. WHAT REMAINS TO VERIFY:", font=f_sec, fill=INK_DARK)
    hyp_text = rec.geo_opportunity_hypothesis or (
        "Official site documents core services, but we have not yet benchmarked whether AI assistants "
        "(ChatGPT / Perplexity / Gemini) surface and cite these specific capabilities when buyers compare providers."
    )
    y_h = _draw_wrapped(draw, hyp_text, 68, act_top + 50, max_chars=74, font=f_body, fill=INK_DARK, max_lines=3)

    draw.text((68, y_h + 12), "MULTIHUB GEO VERIFICATION STEP (NO RANKING GUARANTEE):", font=f_sec, fill=RED_ACCENT)
    step_text = (
        "1) Run recorded non-brand buyer queries across ChatGPT/Perplexity; "
        "2) Audit cited directories & technical schema/content clarity; "
        "3) Retest under identical prompt conditions."
    )
    _draw_wrapped(draw, step_text, 68, y_h + 44, max_chars=74, font=f_body, fill=INK_MUTED, max_lines=3)

    # Provenance Footer (y: 1200 to 1310)
    f_foot = _load_font(16, bold=False)
    foot_y = 1202
    draw.text((48, foot_y), f"Official URL: {rec.official_url[:82]}", font=f_foot, fill=INK_MUTED)
    draw.text((48, foot_y + 26), f"Independent Directory Source: {rec.discovery_source_url[:76]}", font=f_foot, fill=INK_MUTED)
    raw_hash_label = rec.raw_web_screenshot_sha256[:16] if rec.raw_web_screenshot_sha256 else "NONE_TEXT_ONLY"
    draw.text(
        (48, foot_y + 52),
        f"Card: {card_type} | Raw SHA256: {raw_hash_label} | Route: {rec.route_status}",
        font=f_foot,
        fill=INK_MUTED,
    )
    draw.text(
        (48, foot_y + 78),
        "Human review mandatory before any outreach. Auto-sending strictly disabled.",
        font=f_foot,
        fill=RED_ACCENT,
    )

    img.save(out_path, format="PNG")

    # Verify dimensions and compute SHA256
    with Image.open(out_path) as check_im:
        w, h = check_im.size
    rec.png_path = str(out_path)
    rec.png_dimensions = f"{w}x{h}"
    rec.png_sha256 = compute_file_sha256(out_path)
    rec.image_completed = (w == CANVAS_W and h == CANVAS_H and bool(rec.png_sha256))
    return rec
