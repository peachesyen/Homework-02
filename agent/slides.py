"""HTML slide authoring (LLM, with offline mock fallback) and PNG rendering
via a headless Chromium (Playwright).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import config, llm
from .models import Slide, SlideHTML

logger = logging.getLogger("reel_agent.slides")

# DogMood AI brand palette, taken from the real Figma mockup
# (figma.com/design/MyI8NfKD99ZghDQf93v8Kz): warm coral-to-magenta hero
# gradient, off-white app surface, orange primary accent, pink/magenta
# secondary accent, white rounded cards.
THEME = {
    "bg_light": "#f7f7fb",
    "hero_from": "#ff7a59",
    "hero_to": "#ff4d8d",
    "accent": "#ff8a3d",     # orange — primary CTA / active state
    "accent2": "#ff4d8d",    # pink/magenta — social / alert
    "text_dark": "#20232b",
    "text_light": "#ffffff",
    "muted": "#6b7280",
    "success": "#22c55e",
    "purple": "#8b5cf6",
    "card": "#ffffff",
}

BASE_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {config.FRAME_WIDTH}px; height: {config.FRAME_HEIGHT}px; overflow: hidden; }}
body {{
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  background: {THEME['bg_light']};
  color: {THEME['text_dark']};
  display: flex; align-items: center; justify-content: center;
}}
body.hero {{
  background: linear-gradient(160deg, {THEME['hero_from']}, {THEME['hero_to']} 75%);
  color: {THEME['text_light']};
}}
.card {{ width: 92%; height: 84%; display: flex; flex-direction: column; justify-content: center; gap: 16px; }}
.eyebrow {{ color: {THEME['accent']}; font-size: 20px; letter-spacing: 3px; text-transform: uppercase; font-weight: 800; }}
body.hero .eyebrow {{ color: rgba(255,255,255,0.9); }}
h1 {{ font-size: 54px; line-height: 1.12; font-weight: 800; }}
p.lede {{ font-size: 24px; color: {THEME['muted']}; max-width: 900px; line-height: 1.42; }}
body.hero p.lede {{ color: rgba(255,255,255,0.94); }}
.badge {{ display:inline-block; background: rgba(255,138,61,0.12); color:{THEME['accent']}; border:1px solid rgba(255,138,61,0.4); border-radius:999px; padding:6px 18px; font-size:17px; font-weight:700; width:fit-content; }}
body.hero .badge {{ background: rgba(255,255,255,0.2); color:#fff; border-color: rgba(255,255,255,0.55); }}
.dm-card {{ background:{THEME['card']}; border-radius:20px; box-shadow: 0 10px 30px rgba(32,35,43,0.08); }}
"""


# ---------------------------------------------------------------------------
# Real LLM-authored HTML
# ---------------------------------------------------------------------------

SLIDE_HTML_SYSTEM_PROMPT = f"""You write ONE complete, self-contained HTML5
document that will be screenshotted at {config.FRAME_WIDTH}x{config.FRAME_HEIGHT}px
and used as one slide/frame of a video reel.

Hard rules:
- Output a full document: <html><head><style>...inline CSS only...</style>
  </head><body>...</body></html>.
- NO external resources of any kind: no <img src="http...">, no CDNs, no
  webfonts, no network calls. Everything must render offline.
- NO AI-generated images or stock photography. If `is_primary_visual` is
  true for this slide, you MUST build a real illustration/diagram/
  infographic out of HTML/CSS and inline <svg> shapes (rect/circle/path/
  line/text) — at least 4 distinct connected visual elements. This is not
  optional and a text block with a small icon does not satisfy it.
- Match the DogMood AI brand (from the app's real Figma mockup): off-white
  app background {THEME['bg_light']} with dark text {THEME['text_dark']} on
  most slides; the title/hero slide uses a coral-to-magenta gradient
  ({THEME['hero_from']} -> {THEME['hero_to']}) with white text instead
  (add class="hero" to <body> for that one slide only). Orange
  {THEME['accent']} is the primary accent (CTAs, active states); pink/
  magenta {THEME['accent2']} is secondary (social/alerts). Content lives on
  white rounded cards (20px radius, soft shadow) — mirror the mockup's
  friendly, rounded, mobile-app aesthetic, not a generic dark dev-deck look.
- Keep on-screen text SHORT — this is a video slide, not a document page.
  A headline + 1-2 supporting lines is plenty.
- The slide must visually express the given `description` exactly (same
  headline/labels), sized and centered to read clearly on a 1280x720 frame.
"""


async def generate_slide_html(slide: Slide) -> tuple[SlideHTML, str]:
    """Returns (SlideHTML, provider_label_used)."""
    if config.OPENAI_API_KEY:
        try:
            user_prompt = (
                f"Slide {slide.index}/6 — title: {slide.title}\n"
                f"visual_type: {slide.visual_type}\n"
                f"is_primary_visual: {slide.is_primary_visual}\n"
                f"description (what must appear on screen): {slide.description}\n"
            )
            result: SlideHTML = await llm.run_structured(
                SLIDE_HTML_SYSTEM_PROMPT, user_prompt, SlideHTML
            )
            result.slide_index = slide.index
            if "<svg" not in result.html.lower() and slide.is_primary_visual:
                # Model didn't comply with the mandatory-visual rule; don't
                # silently ship a text-only "primary visual" slide.
                raise ValueError("primary visual slide did not include an <svg> diagram")
            return result, config.LLM_MODEL
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM (%s) HTML generation failed for slide %s (%s); using offline template",
                config.LLM_MODEL, slide.index, exc,
            )
    else:
        logger.warning(config.MOCK_MODE_BANNER.format(what="LLM"))
    return _mock_html_for_slide(slide), "mock-offline"


# ---------------------------------------------------------------------------
# Offline mock HTML templates (fallback only)
# ---------------------------------------------------------------------------

def _extract_stage_labels(description: str, fallback_title: str) -> list[str]:
    # Prefer '...'-quoted stage names (how a human-authored description
    # marks the literal on-screen labels) over guessing from prose.
    # Negative lookbehind so a contraction apostrophe (app's, screen's) is
    # never mistaken for the start of a quoted label.
    quoted = re.findall(r"(?<![A-Za-z])'([^']{2,50})'", description)
    if 3 <= len(quoted) <= 6:
        return [q.split(" — ")[0].split(":")[0].strip() for q in quoted[:5]]
    if "→" in description:
        stages = [s.strip() for s in description.split("→") if s.strip()]
        stages = [re.sub(r"^[^:]*:\s*", "", s) for s in stages]
        stages = [s.split(".")[0].strip() for s in stages]
        if 3 <= len(stages) <= 6:
            return stages[:5]
    caps = re.findall(r"\b([A-Z][A-Za-z0-9]+(?:\s[A-Z][A-Za-z0-9]+){0,3})\b", description)
    caps = [c for c in caps if c.lower() not in {"inline", "svg"}]
    uniq: list[str] = []
    for c in caps:
        if c not in uniq:
            uniq.append(c)
    if len(uniq) >= 3:
        return uniq[:4]
    return ["Input", fallback_title, "AI Model", "Output"]


def _svg_pipeline(stages: list[str]) -> str:
    n = len(stages)
    box_w, box_h, gap = 190, 110, 40
    total_w = n * box_w + (n - 1) * gap
    start_x = (1100 - total_w) // 2
    y = 40
    parts = [f'<svg width="1100" height="200" viewBox="0 0 1100 200">']
    parts.append(
        f'<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        f'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="{THEME["accent"]}"/></marker></defs>'
    )
    for i, label in enumerate(stages):
        x = start_x + i * (box_w + gap)
        stroke = THEME["accent"] if i % 2 == 0 else THEME["accent2"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="16" '
            f'fill="{THEME["card"]}" stroke="{stroke}" stroke-width="3" '
            f'style="filter:drop-shadow(0 6px 14px rgba(32,35,43,0.12))"/>'
        )
        parts.append(
            f'<foreignObject x="{x+10}" y="{y+10}" width="{box_w-20}" height="{box_h-20}">'
            f'<div xmlns="http://www.w3.org/1999/xhtml" style="color:{THEME["text_dark"]};font-size:18px;'
            f'font-weight:700;text-align:center;display:flex;align-items:center;'
            f'justify-content:center;height:100%;font-family:sans-serif;line-height:1.25">'
            f'{label}</div></foreignObject>'
        )
        if i < n - 1:
            x2 = x + box_w
            parts.append(
                f'<line x1="{x2}" y1="{y+box_h//2}" x2="{x2+gap-6}" y2="{y+box_h//2}" '
                f'stroke="{THEME["accent"]}" stroke-width="3" marker-end="url(#arrow)"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _mock_html_for_slide(slide: Slide) -> SlideHTML:
    if slide.is_primary_visual or slide.visual_type == "architecture_diagram_svg":
        body_class = ""
        stages = _extract_stage_labels(slide.description, slide.title)
        svg = _svg_pipeline(stages)
        body = f"""
        <div class="card" style="align-items:center; text-align:center;">
          <div class="eyebrow">How It Works</div>
          <h1 style="font-size:46px">{slide.title}</h1>
          <div style="margin-top: 10px;">{svg}</div>
        </div>
        """
        visual_summary = f"Inline SVG pipeline diagram: {' -> '.join(stages)}"
    elif slide.visual_type == "title_card":
        body_class = "hero"
        body = f"""
        <div class="card" style="align-items:center; text-align:center;">
          <div class="badge">AI EXPRESSION DETECTOR</div>
          <svg width="160" height="160" viewBox="0 0 160 160" style="margin:10px auto; display:block;">
            <circle cx="80" cy="80" r="76" fill="rgba(255,255,255,0.16)" stroke="rgba(255,255,255,0.7)" stroke-width="4"/>
            <ellipse cx="55" cy="55" rx="16" ry="20" fill="#fff" opacity="0.9" transform="rotate(-20 55 55)"/>
            <ellipse cx="105" cy="55" rx="16" ry="20" fill="#fff" opacity="0.9" transform="rotate(20 105 55)"/>
            <ellipse cx="80" cy="92" rx="46" ry="40" fill="#fff"/>
            <circle cx="65" cy="82" r="6" fill="{THEME['text_dark']}"/>
            <circle cx="95" cy="82" r="6" fill="{THEME['text_dark']}"/>
            <ellipse cx="80" cy="100" rx="10" ry="7" fill="{THEME['accent']}"/>
            <path d="M80 105 Q80 116 68 112" stroke="{THEME['text_dark']}" stroke-width="3" fill="none" stroke-linecap="round"/>
          </svg>
          <h1>{slide.title}</h1>
          <p class="lede">{slide.narration.strip()[:160]}</p>
        </div>
        """
        visual_summary = "Hero title card, coral-to-magenta gradient, with a simple SVG dog-face emblem in a circular frame"
    elif slide.visual_type == "persona_or_icon_card":
        body_class = ""
        # Prefer '...'-quoted labels (human-authored on-screen text) over
        # guessing capitalized phrases out of prose.
        quoted = re.findall(r"(?<![A-Za-z])'([^']{2,30})'", slide.description)
        capped = re.findall(r"[A-Z][a-zA-Z &]{3,30}(?=:|,|;|$)", slide.description)
        items = (quoted or capped)[:4] or ["Users", "Creators", "Professionals"]
        icon_colors = [THEME["accent"], THEME["accent2"], THEME["purple"]]
        cards = "".join(
            f"""<div class="dm-card" style="flex:1; padding:24px; text-align:center;">
                 <svg width="44" height="44" viewBox="0 0 44 44"><circle cx="22" cy="15" r="9"
                 fill="{icon_colors[i % len(icon_colors)]}"/><path d="M6 40c0-9 7-15 16-15s16 6 16 15"
                 fill="{icon_colors[i % len(icon_colors)]}" opacity="0.55"/></svg>
                 <div style="margin-top:10px; font-size:19px; font-weight:700; color:{THEME['text_dark']};">{c.strip()}</div>
               </div>"""
            for i, c in enumerate(items)
        )
        body = f"""
        <div class="card">
          <div class="eyebrow">{slide.title}</div>
          <h1 style="font-size:42px">{slide.title}</h1>
          <div style="display:flex; gap:20px; margin-top:14px;">{cards}</div>
        </div>
        """
        visual_summary = f"Row of {len(items)} white audience icon-cards"
    elif slide.visual_type == "stat_or_chart_svg":
        body_class = ""
        # Require a capitalized one-word label directly before the percent
        # (e.g. "Hungry 48%") so incidental phrases like "...ring at 92%"
        # in surrounding prose don't get mistaken for chart rows.
        rows = re.findall(r"\b([A-Z][a-z]+)\s+(\d{1,3})%", slide.description)
        if not rows:
            rows = [("Hungry", 48), ("Bored", 25), ("Upset", 15), ("Sad", 12)]
        bar_w, row_h = 640, 46
        bars = []
        colors = [THEME["accent"], THEME["accent2"], THEME["purple"], THEME["muted"]]
        for i, (label, pct) in enumerate(rows[:4]):
            pct = int(pct)
            y = i * row_h
            fill_w = int(bar_w * pct / 100)
            bars.append(
                f'<text x="0" y="{y+20}" font-size="18" font-weight="700" fill="{THEME["text_dark"]}" '
                f'font-family="sans-serif">{label.strip()}</text>'
                f'<rect x="0" y="{y+28}" width="{bar_w}" height="14" rx="7" fill="#eceef2"/>'
                f'<rect x="0" y="{y+28}" width="{fill_w}" height="14" rx="7" fill="{colors[i % len(colors)]}"/>'
                f'<text x="{bar_w+16}" y="{y+40}" font-size="18" font-weight="800" '
                f'fill="{colors[i % len(colors)]}" font-family="sans-serif">{pct}%</text>'
            )
        svg = f'<svg width="760" height="{len(rows[:4])*row_h}" viewBox="0 0 760 {len(rows[:4])*row_h}">{"".join(bars)}</svg>'
        body = f"""
        <div class="card" style="align-items:center; text-align:center;">
          <div class="eyebrow">{slide.title}</div>
          <h1 style="font-size:44px">{slide.title}</h1>
          <div class="dm-card" style="padding:32px; margin-top:8px;">{svg}</div>
        </div>
        """
        visual_summary = f"White card with an SVG horizontal bar chart: {', '.join(f'{l.strip()} {p}%' for l, p in rows[:4])}"
    else:
        body_class = ""
        body = f"""
        <div class="card">
          <div class="eyebrow">{slide.visual_type.replace('_', ' ').title()}</div>
          <h1>{slide.title}</h1>
          <p class="lede">{slide.narration.strip()[:220]}</p>
          <div class="badge">Generative AI powered</div>
        </div>
        """
        visual_summary = "Headline + supporting text card with an accent badge"

    html = f'<html><head><style>{BASE_CSS}</style></head><body class="{body_class}">{body}</body></html>'
    return SlideHTML(slide_index=slide.index, html=html, visual_summary=visual_summary)


# ---------------------------------------------------------------------------
# Rendering HTML -> PNG (Playwright / headless Chromium)
# ---------------------------------------------------------------------------

class SlideRenderer:
    """One shared headless browser; renders many slides concurrently (one
    Page per render, all under the same Browser instance)."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    async def __aenter__(self) -> "SlideRenderer":
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_kwargs = {"args": ["--no-sandbox"]}
        if config.CHROMIUM_EXECUTABLE_PATH:
            launch_kwargs["executable_path"] = config.CHROMIUM_EXECUTABLE_PATH
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def render(self, html: str, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page = await self._browser.new_page(
            viewport={"width": config.FRAME_WIDTH, "height": config.FRAME_HEIGHT}
        )
        try:
            await page.set_content(html, wait_until="load")
            await page.screenshot(path=str(out_path))
        finally:
            await page.close()
        return out_path
