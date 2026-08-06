#!/usr/bin/env python3
"""
reel_agent.py — Tailtale Proposal Video Agent
================================================
Run from the terminal to turn a project proposal (.md) into a narrated,
critiqued, stitched highlight-reel video.

    python reel_agent.py project_proposal.md

What it does, in order:

  1. PLAN      A PydanticAI agent reads the proposal and writes a structured
               SlidePlan (<= --max-slides slides, each with a title, an
               on-screen description, and a narration script sized to fit
               a ~15s TTS clip). This is the only step an LLM's judgment
               drives — everything after it is deterministic.
  2. GENERATE  Per slide, in parallel: render its HTML to a PNG (a hand-built
               template if one exists in --templates-dir, otherwise a clean
               generated fallback layout), and synthesize its narration to a
               WAV/MP3 clip via TTS.
  3. CRITIQUE  Per slide, in parallel: a second PydanticAI agent (vision)
               reviews the rendered PNG for contrast/legibility problems and
               returns structured findings.
  4. ENHANCE   For slides the critique flags, patch the one class of issue
               this script can safely auto-fix (low-contrast body text) and
               re-render. Idempotent — a clean slide is left alone.
  5. STITCH    Per slide, in parallel: mux its PNG + audio into a segment.
  6. ASSEMBLE  Concatenate segments, in order, into the full narrated video.
  7. REEL      Time-compress the full video into a --reel-seconds highlight
               reel (default ~55s, audio pitch preserved).

All LLM output (planning and critique) uses `openai:gpt-5.6-luna`, always —
that model choice is a hard assignment requirement, not a default that shifts
with provider. TTS is `tts-1-hd` by default; set TTS_PROVIDER=gemini in .env
to use Gemini's TTS instead for a more expressive voice — that substitution
is explicitly allowed by the assignment for narration only, not for planning
or critique.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import wave
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional
from urllib import request as urlreq

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, ModelRetry

load_dotenv()  # reads .env in the current working directory


def _ffmpeg_works(path: str) -> bool:
    try:
        subprocess.run([path, "-version"], capture_output=True, timeout=10, check=True)
        return True
    except Exception:  # noqa: BLE001 - any failure means "don't trust this binary"
        return False


def _resolve_ffmpeg() -> str:
    """Prefer a system ffmpeg; fall back to the static binary bundled by
    imageio-ffmpeg (in requirements.txt) so this works with zero system
    setup. A binary merely being *found* on PATH isn't enough to trust it —
    a broken install (e.g. a missing shared library) still resolves via
    `which` but fails the moment it actually runs, so this verifies with a
    real invocation before committing to it."""
    env = os.environ.get("FFMPEG_BIN")
    if env and _ffmpeg_works(env):
        return env
    found = shutil.which("ffmpeg")
    if found and _ffmpeg_works(found):
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("No working ffmpeg found (checked PATH) and imageio-ffmpeg isn't installed "
                  "either. Install ffmpeg system-wide, or `pip install imageio-ffmpeg`.")


# Numeric HTTP status codes need word boundaries — a bare substring check
# on "500" would false-positive on any error that happens to mention an
# unrelated number containing those digits (e.g. "processed 1500 items").
# Phrase markers are checked case-insensitively as plain substrings, since
# they're specific enough in practice not to need the same guard.
_TRANSIENT_STATUS_CODES = ("429", "500", "502", "503", "504")
_TRANSIENT_STATUS_RE = re.compile(r"(?<!\d)(?:" + "|".join(_TRANSIENT_STATUS_CODES) + r")(?!\d)")
_TRANSIENT_PHRASES = ("resource_exhausted", "rate limit", "too many requests", "quota exceeded")


def _is_transient(exc: Exception) -> bool:
    text = str(exc)
    if _TRANSIENT_STATUS_RE.search(text):
        return True
    lowered = text.lower()
    return any(phrase in lowered for phrase in _TRANSIENT_PHRASES)

# Firing every slide's API call at once reliably trips free-tier rate limits
# in practice — cap how many are in flight together. TTS and vision-critique
# hit different endpoints with different quotas (Gemini's preview TTS model
# in particular tolerates far less concurrency than its vision model does in
# testing), so they get separate budgets rather than one shared number.
API_SEMAPHORE = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_API_CALLS", "3")))
_default_tts_concurrency = "1" if os.environ.get("TTS_PROVIDER", "openai").lower() == "gemini" else "4"
TTS_SEMAPHORE = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_TTS", _default_tts_concurrency)))


async def with_retries(coro_fn, *args, retries: int = 4, base_delay: float = 2.0, **kwargs):
    """Parallel fan-out (6 slides hitting an API at once) reliably trips
    provider rate limits — this showed up in real testing, not hypothetically.
    Retries transient errors with jittered exponential backoff; anything else
    raises immediately."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - deliberately broad, re-raised below when not transient
            last_exc = e
            if not _is_transient(e) or attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"    (transient error, retrying in {delay:.1f}s: {str(e)[:90]})")
            await asyncio.sleep(delay)
    raise last_exc  # pragma: no cover


# --------------------------------------------------------------------------
# Config
#
# Two independent choices, per the assignment spec — don't conflate them:
#   - LLM_MODEL: what the planner and critic agents reason with. The
#     assignment requires this to always be gpt-5.6-luna. Not providerswitchable
#     in normal use; the env var override below exists for local development
#     only (this sandbox's network policy blocks api.openai.com outright, so
#     testing happened against a Gemini override — see README).
#   - TTS_PROVIDER: openai (tts-1-hd, the required default) or gemini
#     (explicitly allowed as a narration-only substitution for a more
#     expressive voice). This one *is* meant to be switchable.
# --------------------------------------------------------------------------

FFMPEG_BIN = _resolve_ffmpeg()

LLM_MODEL = os.environ.get("LLM_MODEL", "openai:gpt-5.6-luna")
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "openai").lower()  # "openai" | "gemini"

_llm_is_openai = LLM_MODEL.split(":", 1)[0] == "openai"
if _llm_is_openai and not os.environ.get("OPENAI_API_KEY"):
    sys.exit("OPENAI_API_KEY is not set (required: all LLM output uses gpt-5.6-luna). "
              "Copy .env.example to .env and fill it in.")
if not _llm_is_openai and not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    sys.exit("LLM_MODEL is overridden to a non-OpenAI model but no GEMINI_API_KEY/GOOGLE_API_KEY is set.")

if TTS_PROVIDER == "openai":
    TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1-hd")
    DEFAULT_VOICE = "onyx"
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")
else:
    TTS_MODEL = os.environ.get("TTS_MODEL", "gemini-2.5-flash-preview-tts")
    DEFAULT_VOICE = "Kore"
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("TTS_PROVIDER=gemini but GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in.")

# PROVIDER is what the TTS dispatch code below checks — alias kept short
# since it's referenced at every synth_audio() call site.
PROVIDER = TTS_PROVIDER


# --------------------------------------------------------------------------
# Data model — the single source of truth for slide content
# --------------------------------------------------------------------------

class VisualSource(str, Enum):
    MOCKUP_SCREENSHOT = "mockup_screenshot"
    DIAGRAM = "diagram"
    STAT_GRAPHIC = "stat_graphic"
    TEXT_ONLY = "text_only"


class Slide(BaseModel):
    slide_number: int = Field(..., ge=1, description="1-indexed position in the deck")
    title: str = Field(..., description="On-screen headline, <= 8 words")
    slide_description: str = Field(
        ..., description="Everything visible on screen: layout, text, and visuals"
    )
    visual_source: VisualSource
    narration: str = Field(
        ..., description="TTS script for this slide. Must read aloud in ~15 seconds or less "
                          "(roughly 35-40 words) at a natural pace."
    )


class SlidePlan(BaseModel):
    project_name: str
    video_title: str
    slides: list[Slide] = Field(..., description="4 to 6 slides, in presentation order")


class SlideCritique(BaseModel):
    contrast_ok: bool = Field(description="False if any on-screen text has a legibility problem")
    visual_issues: list[str] = Field(default_factory=list, description="Specific on-screen elements that fail, if any")
    visual_fixes: list[str] = Field(default_factory=list, description="Concrete, actionable visual fixes")
    narration_ok: bool = Field(description="False if the narration is too long, unclear, or mismatched to the visual")
    narration_issues: list[str] = Field(default_factory=list, description="Specific problems with the narration script")
    narration_fixes: list[str] = Field(default_factory=list, description="Concrete rewrites or trims to the narration")


class Revision(BaseModel):
    """What actually changed after critique — the audit trail graders check."""
    slide_number: int
    visual_revised: bool
    visual_change: str = Field(default="", description="What was changed on screen, or empty if nothing was")
    narration_revised: bool
    narration_before: str = Field(default="")
    narration_after: str = Field(default="")


class CritiqueFeedbackEntry(BaseModel):
    slide_number: int
    title: str
    critique: SlideCritique
    revision: Revision


# --------------------------------------------------------------------------
# Agents (PydanticAI) — the two steps that need a model's judgment
# --------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are a professional UX/UI presentation designer with 30 years of experience,
turning a project proposal document into a short pitch-video slide plan.

Rules:
- Produce at most {max_slides} slides, in a natural pitch arc: open with the
  problem/hook, introduce the solution, explain the core mechanism briefly,
  cover differentiation or validation if the proposal discusses it, and close
  with scope/roadmap.
- Each `narration` must be speakable in about 15 seconds or less (roughly
  35-40 words) at a natural pace. Before finalizing each slide, call the
  `count_words` tool on its narration draft and rewrite it shorter if the
  count is above 40 — do not guess the length, check it.
- Each `slide_description` should describe a concrete, buildable layout
  (what text blocks, what kind of visual — a diagram, a stat callout, an
  icon row, a comparison table) — not vague ("a nice graphic").
- Ground every claim in the proposal text. Do not invent statistics,
  competitors, or features the proposal does not mention.
- Never claim the product does something the proposal explicitly scopes out
  or defers to a later phase — say so if relevant (the proposal's own
  honesty about limitations is often one of its most important points).
"""

CRITIC_SYSTEM_PROMPT = """\
You are a senior UX/UI critic reviewing one slide from a narrated video —
both the rendered frame AND the narration spoken over it. Review two things:

1. Visual contrast/legibility for playback on a compressed video stream. Use
   the `contrast_ratio` tool on the specific foreground/background hex colors
   you can identify on screen rather than eyeballing it — WCAG treats
   anything under 4.5:1 as failing for normal text. Name the exact element
   that fails (e.g. "the mono caption under the donut chart"), not a vague
   category.
2. Narration quality: too long for the stated clip duration (use
   `count_words` — over ~40 words is too long for a 15s clip), unclear, or
   mismatched to what's on screen at that moment.

Do not comment on layout taste, color choice, or content quality beyond
these two axes.
"""


def build_planner_agent(max_slides: int) -> Agent[None, SlidePlan]:
    agent: Agent[None, SlidePlan] = Agent(
        LLM_MODEL,
        output_type=SlidePlan,
        system_prompt=PLANNER_SYSTEM_PROMPT.format(max_slides=max_slides),
    )

    @agent.tool_plain
    def count_words(text: str) -> int:
        """Count the words in a narration draft, to check it fits the ~15s TTS budget."""
        return len(text.split())

    return agent


_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    if not _HEX_COLOR_RE.match(hex_color or ""):
        raise ValueError(f"not a 6-digit hex color: {hex_color!r}")
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def build_critic_agent() -> Agent[None, SlideCritique]:
    agent: Agent[None, SlideCritique] = Agent(
        LLM_MODEL,
        output_type=SlideCritique,
        system_prompt=CRITIC_SYSTEM_PROMPT,
    )

    @agent.tool_plain
    def contrast_ratio(
        foreground_hex: Annotated[str, Field(examples=["#b6c2ba"])],
        background_hex: Annotated[str, Field(examples=["#0d1310"])],
    ) -> float:
        """WCAG contrast ratio between two colors, each a 6-digit hex string
        like '#b6c2ba' (the # is optional). Returns a value from 1 (no
        contrast) to 21 (max contrast); WCAG AA requires >= 4.5 for normal
        text."""
        try:
            l1 = _relative_luminance(_hex_to_rgb(foreground_hex))
            l2 = _relative_luminance(_hex_to_rgb(background_hex))
        except ValueError as e:
            # Tell the model its arguments were malformed so it can retry
            # with a corrected call, instead of crashing the whole run over
            # one bad tool call.
            raise ModelRetry(
                f"{e}. Pass two 6-digit hex colors, e.g. contrast_ratio('#b6c2ba', '#0d1310')."
            ) from e
        lighter, darker = max(l1, l2), min(l1, l2)
        return round((lighter + 0.05) / (darker + 0.05), 2)

    @agent.tool_plain
    def count_words(text: str) -> int:
        """Count the words in a narration script."""
        return len(text.split())

    return agent


critic_agent: Agent[None, SlideCritique] = build_critic_agent()


class RevisedNarration(BaseModel):
    narration: str = Field(..., description="Rewritten narration, <= 40 words, same meaning and tone")


def build_reviser_agent() -> Agent[None, RevisedNarration]:
    agent: Agent[None, RevisedNarration] = Agent(
        LLM_MODEL,
        output_type=RevisedNarration,
        system_prompt=(
            "Rewrite the given slide narration to fix the stated issues — usually "
            "shortening it to fit a ~15s clip (~40 words or fewer) — while keeping "
            "its meaning and tone. Call count_words on your rewrite before returning "
            "to confirm it fits; if it doesn't, shorten it again."
        ),
    )

    @agent.tool_plain
    def count_words(text: str) -> int:
        """Count the words in a narration draft."""
        return len(text.split())

    return agent


reviser_agent: Agent[None, RevisedNarration] = build_reviser_agent()


async def revise_narration(slide: Slide, critique: SlideCritique) -> Optional[str]:
    """Only called when the critic flagged the narration — returns a rewritten
    script, or None if nothing needed to change."""
    if critique.narration_ok:
        return None
    async with API_SEMAPHORE:
        result = await with_retries(
            reviser_agent.run,
            f"Slide title: '{slide.title}'\n"
            f"Original narration: \"{slide.narration}\"\n"
            f"Issues to fix: {'; '.join(critique.narration_issues) or 'too long'}",
        )
    return result.output.narration


# --------------------------------------------------------------------------
# Stage 1: PLAN
# --------------------------------------------------------------------------

async def plan_from_proposal(proposal_text: str, max_slides: int) -> SlidePlan:
    agent = build_planner_agent(max_slides)
    result = await with_retries(agent.run, proposal_text)
    plan = result.output
    if len(plan.slides) > max_slides:
        plan.slides = plan.slides[:max_slides]
    return plan


# --------------------------------------------------------------------------
# Stage 2a: RENDER (HTML -> PNG)
# --------------------------------------------------------------------------

GENERIC_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  :root{{
    --ink:#0d1310; --panel:#121a16; --paper:#f4f7f2; --muted:#b6c2ba;
    --line:#26362d; --warm:#ff7a45; --calm:#4fd1b0;
    --font-display: ui-serif,"Iowan Old Style",Georgia,serif;
    --font-sans: ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
    --font-mono: ui-monospace,"SF Mono","DejaVu Sans Mono",monospace;
  }}
  *{{box-sizing:border-box;}}
  html,body{{margin:0;padding:0;background:#000;height:100%;}}
  .stage{{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;}}
  .slide{{
    width:1920px;height:1080px;position:relative;background:var(--ink);
    color:var(--paper); font-family:var(--font-sans); padding:120px;
    display:flex; flex-direction:column; justify-content:center;
  }}
  .watermark{{
    position:absolute; top:40px; right:56px; font-family:var(--font-mono);
    font-size:220px; font-weight:700; color:var(--panel); z-index:0; line-height:1;
  }}
  .accent{{ width:64px; height:6px; background:var(--warm); border-radius:3px; margin-bottom:28px; }}
  .eyebrow{{
    font-family:var(--font-mono); font-size:18px; letter-spacing:.16em; text-transform:uppercase;
    color:var(--calm); margin-bottom:18px; position:relative; z-index:1;
  }}
  h1{{
    font-family:var(--font-display); font-weight:600; font-size:64px; line-height:1.1;
    margin:0 0 28px; max-width:20ch; position:relative; z-index:1;
  }}
  p{{ font-size:24px; line-height:1.55; color:var(--muted); max-width:70ch; position:relative; z-index:1; }}
</style></head>
<body><div class="stage"><div class="slide">
  <div class="watermark">{slide_number:02d}</div>
  <div class="accent"></div>
  <div class="eyebrow">{eyebrow}</div>
  <h1>{title}</h1>
  <p>{description}</p>
</div></div></body></html>
"""


def resolve_slide_html(slide: Slide, templates_dir: Path, out_dir: Path) -> Path:
    """Prefer a hand-built template on disk; fall back to a generated one."""
    match = sorted(templates_dir.glob(f"{slide.slide_number:02d}-*.html")) if templates_dir.exists() else []
    if match:
        return match[0]

    generated_dir = out_dir / "generated_slides"
    generated_dir.mkdir(parents=True, exist_ok=True)
    path = generated_dir / f"{slide.slide_number:02d}-generated.html"
    html = GENERIC_TEMPLATE.format(
        slide_number=slide.slide_number,
        eyebrow=f"{slide.slide_number:02d} — {slide.visual_source.value.replace('_', ' ').title()}",
        title=slide.title,
        description=slide.slide_description,
    )
    path.write_text(html)
    return path


def render_png_sync(html_path: Path, png_path: Path, chrome_path: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path or None, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_timeout(200)
        page.screenshot(path=str(png_path))
        browser.close()


async def render_slide(slide: Slide, templates_dir: Path, out_dir: Path, chrome_path: str) -> Path:
    html_path = resolve_slide_html(slide, templates_dir, out_dir)
    png_path = out_dir / "shots" / f"{slide.slide_number:02d}.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(render_png_sync, html_path, png_path, chrome_path)
    return png_path


# --------------------------------------------------------------------------
# Stage 2b: SYNTH AUDIO
# --------------------------------------------------------------------------

async def synth_audio_openai(text: str, voice: str, out_path: Path) -> None:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.audio.speech.create(
        model=TTS_MODEL, voice=voice, input=text, response_format="wav"
    )
    await response.astream_to_file(str(out_path))


def _gemini_tts_sync(text: str, voice: str, out_path: Path) -> None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    body = {
        "contents": [{"parts": [{"text": (
            "Say in a warm, confident, professional voice, at a measured pace, "
            "like a narrator in a startup product-pitch video: " + text
        )}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
    req = urlreq.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            with urlreq.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            break
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if not _is_transient(e) or attempt == 3:
                raise
            delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
            print(f"    (transient TTS error, retrying in {delay:.1f}s: {str(e)[:90]})")
            time.sleep(delay)
    else:
        raise last_exc  # pragma: no cover

    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "rate=24000")).group(1))
    pcm = base64.b64decode(part["data"])
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


async def synth_audio(slide: Slide, voice: str, out_dir: Path, cache_dir: Optional[Path]) -> Path:
    ext = "wav"
    out_path = out_dir / "audio" / f"{slide.slide_number:02d}.{ext}"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_dir:
        cached = sorted(cache_dir.glob(f"{slide.slide_number:02d}-*.wav"))
        if cached:
            out_path.write_bytes(cached[0].read_bytes())
            return out_path

    async with TTS_SEMAPHORE:
        if PROVIDER == "openai":
            await with_retries(synth_audio_openai, slide.narration, voice, out_path)
        else:
            await asyncio.to_thread(_gemini_tts_sync, slide.narration, voice, out_path)
    return out_path


# --------------------------------------------------------------------------
# Stage 3: CRITIQUE
# --------------------------------------------------------------------------

async def critique_slide(png_path: Path, slide: Slide) -> SlideCritique:
    img_bytes = png_path.read_bytes()
    async with API_SEMAPHORE:
        result = await with_retries(
            critic_agent.run,
            [f"Slide {slide.slide_number}: '{slide.title}'.\n"
             f"Narration for this slide (spoken while it's on screen): \"{slide.narration}\"\n"
             f"Review the frame below against both axes in your instructions.",
             BinaryContent(data=img_bytes, media_type="image/png")],
        )
    return result.output


# --------------------------------------------------------------------------
# Stage 4: ENHANCE
# --------------------------------------------------------------------------

def enhance_html(html_path: Path, critique: SlideCritique) -> bool:
    """Auto-fix the one issue class this script trusts itself to patch:
    a low-contrast --muted CSS token. Returns True if it changed anything."""
    if critique.contrast_ok:
        return False
    src = html_path.read_text()
    if "--muted:#b6c2ba" in src or "--muted:#c6d1c9" in src:
        return False  # already at the bright value
    new_src, n = re.subn(r"--muted:#[0-9a-fA-F]{6};", "--muted:#b6c2ba;", src, count=1)
    if n:
        html_path.write_text(new_src)
        return True
    return False


# --------------------------------------------------------------------------
# Stage 5-7: STITCH / ASSEMBLE / REEL
# --------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


async def stitch_segment(png_path: Path, audio_path: Path, out_dir: Path, slide_number: int) -> Path:
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    out_path = seg_dir / f"{slide_number:02d}.mp4"
    cmd = [
        FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png_path), "-i", str(audio_path),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-vf", "scale=1920:1080,format=yuv420p",
        "-shortest", str(out_path), "-loglevel", "error",
    ]
    await asyncio.to_thread(_run, cmd)
    return out_path


async def assemble(segments: list[Path], out_dir: Path) -> Path:
    list_path = out_dir / "concat_list.txt"
    list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in segments))
    out_path = out_dir / "full_video.mp4"
    cmd = [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
           "-c", "copy", str(out_path), "-loglevel", "error"]
    await asyncio.to_thread(_run, cmd)
    return out_path


def parse_ffmpeg_duration(ffmpeg_stderr: str) -> Optional[float]:
    """Parse ffmpeg's 'Duration: HH:MM:SS.ss' line from its own stderr probe
    output into seconds. Pulled out as a pure function so the parsing logic
    is unit-testable without invoking a real ffmpeg subprocess."""
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", ffmpeg_stderr)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def compute_reel_speed(total_seconds: float, target_seconds: float) -> float:
    """How much to speed up `total_seconds` of content to fit in
    `target_seconds`, clamped to [1.0, 2.0] — below 1x would mean slowing
    down (never wanted here), and ffmpeg's atempo needs a second filter
    chained above 2x, which this deliberately doesn't attempt in one pass."""
    if target_seconds <= 0:
        raise ValueError("target_seconds must be positive")
    return max(1.0, min(2.0, total_seconds / target_seconds))


async def make_reel(full_video: Path, out_dir: Path, target_seconds: float) -> Path:
    probe = subprocess.run(
        [FFMPEG_BIN, "-i", str(full_video)], capture_output=True, text=True
    ).stderr
    total = parse_ffmpeg_duration(probe) or target_seconds
    speed = compute_reel_speed(total, target_seconds)

    out_path = out_dir / "reel.mp4"
    cmd = [
        FFMPEG_BIN, "-y", "-i", str(full_video),
        "-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac",
        str(out_path), "-loglevel", "error",
    ]
    await asyncio.to_thread(_run, cmd)
    return out_path


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

async def run_parallel(label: str, coros) -> list:
    t0 = time.time()
    results = await asyncio.gather(*coros)
    print(f"[{label}] {len(results)} tasks in {time.time() - t0:.2f}s (parallel)")
    return results


async def main_async(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    grading_dir = Path(args.grading_dir)
    grading_dir.mkdir(parents=True, exist_ok=True)
    templates_dir = Path(args.templates_dir)
    cache_dir = Path(args.audio_cache) if args.audio_cache else None
    voice = args.voice or DEFAULT_VOICE

    print(f"=== reel_agent — llm={LLM_MODEL}, tts_provider={TTS_PROVIDER} ({TTS_MODEL}) ===\n")

    if args.plan_json:
        # Resume from an already-generated plan instead of spending another
        # planner call — useful for re-running the deterministic stages
        # after tweaking a template, without re-hitting the LLM API.
        plan = SlidePlan.model_validate_json(Path(args.plan_json).read_text())
        print(f"[plan] loaded {len(plan.slides)} slides from {args.plan_json} (planner call skipped)\n")
    else:
        proposal_text = Path(args.proposal).read_text()
        print("[plan] asking the planner agent to read the proposal...")
        plan = await plan_from_proposal(proposal_text, args.max_slides)
        print(f"[plan] {len(plan.slides)} slides for '{plan.project_name}'\n")

    # ai_grading/slide_plan.json — required grading artifact, written before
    # any critique/revision so graders can diff it against the final slides.
    (grading_dir / "slide_plan.json").write_text(plan.model_dump_json(indent=2))

    # Stage 2: generate (render + audio), parallel across ALL slides and both kinds
    png_paths = await run_parallel(
        "render",
        (render_slide(s, templates_dir, out_dir, args.chrome_path) for s in plan.slides),
    )
    audio_paths = await run_parallel(
        "synth_audio",
        (synth_audio(s, voice, out_dir, cache_dir) for s in plan.slides),
    )
    print()

    feedback_entries: list[CritiqueFeedbackEntry] = []

    if not args.skip_critique:
        # Stage 3: critique, parallel across slides — covers both the
        # rendered visual and the narration text together.
        critiques = await run_parallel(
            "critique",
            (critique_slide(p, s) for p, s in zip(png_paths, plan.slides)),
        )
        for s, c in zip(plan.slides, critiques):
            v_flag = "OK" if c.contrast_ok else "VISUAL ISSUES"
            n_flag = "OK" if c.narration_ok else "NARRATION ISSUES"
            print(f"  slide {s.slide_number} [{v_flag}] [{n_flag}]")
            for issue in c.visual_issues:
                print(f"    visual:    {issue}")
            for issue in c.narration_issues:
                print(f"    narration: {issue}")
        print()

        # Stage 4: enhance — visual patch + re-render, and narration rewrite +
        # re-synthesis, per slide. Sequential: both mutate shared state
        # (files on disk, and the plan's own narration text) that later
        # stages depend on, so this can't safely run concurrently with itself.
        slides_needing_rerender: list[Slide] = []
        slides_needing_resynth: list[Slide] = []

        for i, (slide, png_path, critique) in enumerate(zip(plan.slides, png_paths, critiques)):
            html_path = resolve_slide_html(slide, templates_dir, out_dir)
            visual_changed = enhance_html(html_path, critique)
            if visual_changed:
                slides_needing_rerender.append(slide)

            narration_before = slide.narration
            narration_after = narration_before
            narration_changed = False
            if not critique.narration_ok:
                revised = await revise_narration(slide, critique)
                if revised and revised.strip() != narration_before.strip():
                    narration_after = revised.strip()
                    plan.slides[i].narration = narration_after
                    narration_changed = True
                    slides_needing_resynth.append(plan.slides[i])

            feedback_entries.append(CritiqueFeedbackEntry(
                slide_number=slide.slide_number,
                title=slide.title,
                critique=critique,
                revision=Revision(
                    slide_number=slide.slide_number,
                    visual_revised=visual_changed,
                    visual_change=("brightened low-contrast --muted text token" if visual_changed else ""),
                    narration_revised=narration_changed,
                    narration_before=narration_before if narration_changed else "",
                    narration_after=narration_after if narration_changed else "",
                ),
            ))

        if slides_needing_rerender:
            print(f"[enhance] patched {len(slides_needing_rerender)} slide visual(s), re-rendering...")
            new_pngs = await run_parallel(
                "re-render",
                (render_slide(s, templates_dir, out_dir, args.chrome_path) for s in slides_needing_rerender),
            )
            for s, p in zip(slides_needing_rerender, new_pngs):
                png_paths[s.slide_number - 1] = p
        if slides_needing_resynth:
            print(f"[enhance] revised {len(slides_needing_resynth)} slide narration(s), re-synthesizing audio...")
            new_audio = await run_parallel(
                "re-synth",
                (synth_audio(s, voice, out_dir, None) for s in slides_needing_resynth),  # bypass cache: text changed
            )
            for s, a in zip(slides_needing_resynth, new_audio):
                audio_paths[s.slide_number - 1] = a
        if not slides_needing_rerender and not slides_needing_resynth:
            print("[enhance] no changes needed (idempotent)")
        print()

        # ai_grading/critique_feedback.json — required grading artifact.
        (grading_dir / "critique_feedback.json").write_text(
            json.dumps([e.model_dump() for e in feedback_entries], indent=2)
        )
        # Keep slide_plan.json in sync if narration was revised after the
        # first write, so it reflects what's actually in the final video.
        (grading_dir / "slide_plan.json").write_text(plan.model_dump_json(indent=2))

    # Stage 5: stitch, parallel across slides
    segments = await run_parallel(
        "stitch",
        (stitch_segment(p, a, out_dir, s.slide_number)
         for p, a, s in zip(png_paths, audio_paths, plan.slides)),
    )

    # Stage 6: assemble (sequential — order matters)
    t0 = time.time()
    full_video = await assemble(segments, out_dir)
    print(f"[assemble] -> {full_video} ({time.time() - t0:.2f}s)")

    # Stage 7: reel (sequential)
    t0 = time.time()
    reel = await make_reel(full_video, out_dir, args.reel_seconds)
    print(f"[reel] -> {reel} ({time.time() - t0:.2f}s)")

    print("\n=== Done ===")
    print(f"Full video:        {full_video}")
    print(f"Reel:              {reel}")
    print(f"Slide plan:        {grading_dir / 'slide_plan.json'}")
    if not args.skip_critique:
        print(f"Critique feedback: {grading_dir / 'critique_feedback.json'}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a narrated proposal video from a proposal document.")
    p.add_argument("proposal", nargs="?", default="project_proposal.md", help="Path to the proposal .md file")
    p.add_argument("--templates-dir", default="slides", help="Directory of hand-built per-slide HTML templates")
    p.add_argument("--out-dir", default="output", help="Directory for all generated artifacts")
    p.add_argument("--grading-dir", default="ai_grading",
                   help="Directory for slide_plan.json and critique_feedback.json (required repo layout)")
    p.add_argument("--audio-cache", default=None, help="Optional directory of pre-generated WAVs to reuse")
    p.add_argument("--plan-json", default=None,
                   help="Skip the planner call and resume from a previously saved slide_plan.json")
    p.add_argument("--max-slides", type=int, default=6)
    p.add_argument("--voice", default=None, help="TTS voice name (defaults per provider)")
    p.add_argument("--reel-seconds", type=float, default=55.0, help="Target reel duration (30-60s)")
    p.add_argument("--skip-critique", action="store_true", help="Skip the critique/enhance stages")
    p.add_argument("--chrome-path", default=os.environ.get("CHROME_PATH", ""),
                   help="Path to a Chromium executable for Playwright, if not on PATH")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
