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

THEME = {
    "bg_from": "#0b1020",
    "bg_to": "#1b2540",
    "accent": "#7dd3fc",
    "accent2": "#f472b6",
    "text": "#f8fafc",
    "muted": "#94a3b8",
}

BASE_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {config.FRAME_WIDTH}px; height: {config.FRAME_HEIGHT}px; overflow: hidden; }}
body {{
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  background: radial-gradient(1200px 800px at 20% -10%, {THEME['bg_to']}, {THEME['bg_from']} 60%);
  color: {THEME['text']};
  display: flex; align-items: center; justify-content: center;
}}
.card {{ width: 92%; height: 84%; display: flex; flex-direction: column; justify-content: center; gap: 18px; }}
.eyebrow {{ color: {THEME['accent']}; font-size: 22px; letter-spacing: 3px; text-transform: uppercase; font-weight: 700; }}
h1 {{ font-size: 58px; line-height: 1.1; font-weight: 800; }}
p.lede {{ font-size: 26px; color: {THEME['muted']}; max-width: 900px; line-height: 1.4; }}
.badge {{ display:inline-block; background: rgba(125,211,252,0.12); color:{THEME['accent']}; border:1px solid rgba(125,211,252,0.4); border-radius:999px; padding:6px 18px; font-size:18px; font-weight:600; width:fit-content; }}
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
- Match this palette/theme (dark background, light text, cyan accent
  {THEME['accent']}, pink accent {THEME['accent2']}):
  body background should be a dark gradient, text light, one accent color
  used for emphasis.
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
        fill = THEME["accent"] if i % 2 == 0 else THEME["accent2"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="16" '
            f'fill="rgba(255,255,255,0.06)" stroke="{fill}" stroke-width="2.5"/>'
        )
        parts.append(
            f'<foreignObject x="{x+10}" y="{y+10}" width="{box_w-20}" height="{box_h-20}">'
            f'<div xmlns="http://www.w3.org/1999/xhtml" style="color:#f8fafc;font-size:18px;'
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
        body = f"""
        <div class="card" style="align-items:center; text-align:center;">
          <svg width="120" height="120" viewBox="0 0 120 120" style="margin:0 auto 10px auto; display:block;">
            <circle cx="60" cy="60" r="52" fill="none" stroke="{THEME['accent']}" stroke-width="4" opacity="0.6"/>
            <circle cx="60" cy="60" r="30" fill="{THEME['accent2']}" opacity="0.85"/>
          </svg>
          <h1>{slide.title}</h1>
          <p class="lede">{slide.description.split(':', 1)[-1].strip()[:160]}</p>
        </div>
        """
        visual_summary = "Centered title card with a decorative SVG emblem"
    elif slide.visual_type == "persona_or_icon_card":
        items = re.findall(r"[A-Z][a-zA-Z &]{3,30}(?=:|,|;|$)", slide.description)[:4] or [
            "Users", "Creators", "Professionals"
        ]
        cards = "".join(
            f"""<div style="flex:1; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12);
                 border-radius:16px; padding:22px; text-align:center;">
                 <svg width="46" height="46" viewBox="0 0 46 46"><circle cx="23" cy="16" r="10"
                 fill="{THEME['accent']}"/><path d="M6 42c0-10 8-16 17-16s17 6 17 16" fill="{THEME['accent2']}"/></svg>
                 <div style="margin-top:10px; font-size:20px; font-weight:700;">{c.strip()}</div>
               </div>"""
            for c in items
        )
        body = f"""
        <div class="card">
          <div class="eyebrow">Who It's For</div>
          <h1 style="font-size:44px">{slide.title}</h1>
          <div style="display:flex; gap:20px; margin-top:14px;">{cards}</div>
        </div>
        """
        visual_summary = f"Row of {len(items)} audience icon-cards"
    else:
        body = f"""
        <div class="card">
          <div class="eyebrow">{slide.visual_type.replace('_', ' ').title()}</div>
          <h1>{slide.title}</h1>
          <p class="lede">{slide.description[:220]}</p>
          <div class="badge">Generative AI powered</div>
        </div>
        """
        visual_summary = "Headline + supporting text card with an accent badge"

    html = f"<html><head><style>{BASE_CSS}</style></head><body>{body}</body></html>"
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
