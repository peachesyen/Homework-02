#!/usr/bin/env python3
"""reel_agent.py — HW2 Final Project Video Reel Agent (PydanticAI).

Reads project_proposal.md, plans a 4-6 slide video reel (structured
Pydantic output), authors each slide as HTML/CSS/SVG, narrates it with TTS,
critiques and revises every slide + its narration, then renders and stitches
everything into a ~30-60s reel.mp4 — with slide generation, TTS, and their
critique/enhancement all running in parallel across slides via asyncio.

Usage:
    python reel_agent.py [--proposal project_proposal.md] [--out build/reel.mp4]

Requires OPENAI_API_KEY in a local .env for real gpt-5.6-luna / tts-1-hd
output; without it, every step still runs end-to-end using deterministic
offline fallbacks (see agent/mock_provider.py and README.md).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from agent import config
from agent.critique import critique_and_revise
from agent.flow_diagram import render_agent_flow_png
from agent.llm import generate_slide_plan
from agent.models import CritiqueFeedback, Slide
from agent.proposal import load_proposal_text, parse_sections
from agent.slides import SlideRenderer, generate_slide_html
from agent.tts import synthesize
from agent.video import SlideAV, build_reel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reel_agent")


def _write_json(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


async def _draft_slide(slide: Slide, renderer_providers: dict) -> tuple:
    """Stage 2+3: author this slide's HTML and its draft narration audio, in parallel."""
    html_task = asyncio.create_task(generate_slide_html(slide))
    audio_path = config.AUDIO_DIR / f"slide_{slide.index}_draft"
    tts_task = asyncio.create_task(synthesize(slide.narration, audio_path))
    html_result, html_provider = await html_task
    tts_result = await tts_task
    renderer_providers[f"slide_{slide.index}_html_draft"] = html_provider
    renderer_providers[f"slide_{slide.index}_tts_draft"] = tts_result.provider
    return slide, html_result


async def _finalize_slide(
    revised_slide: Slide, renderer: SlideRenderer, providers: dict
) -> SlideAV:
    """Stage 5: regenerate this slide's HTML + audio from the critique's
    revised text, render the final PNG, and synthesize the final narration —
    HTML/render and audio run in parallel with each other, and this whole
    function runs in parallel across all slides via asyncio.gather."""

    async def _html_then_render():
        html_result, provider = await generate_slide_html(revised_slide)
        providers[f"slide_{revised_slide.index}_html_final"] = provider
        html_path = config.SLIDES_DIR / f"slide_{revised_slide.index}.html"
        html_path.write_text(html_result.html, encoding="utf-8")
        png_path = config.FRAMES_DIR / f"slide_{revised_slide.index}.png"
        await renderer.render(html_result.html, png_path)
        return png_path

    async def _audio():
        audio_path = config.AUDIO_DIR / f"slide_{revised_slide.index}_final"
        result = await synthesize(revised_slide.narration, audio_path)
        providers[f"slide_{revised_slide.index}_tts_final"] = result.provider
        return result

    png_path, tts_result = await asyncio.gather(_html_then_render(), _audio())
    return SlideAV(
        index=revised_slide.index,
        image_path=png_path,
        audio_path=tts_result.path,
        audio_duration=tts_result.duration_seconds,
    )


async def run(proposal_path: Path, out_video: Path) -> None:
    t0 = time.time()
    providers: dict[str, str] = {}

    log.info("Reading proposal from %s", proposal_path)
    raw = load_proposal_text(proposal_path)
    sections = parse_sections(raw)

    # Slide plan and the (data-independent) flow diagram can be produced concurrently.
    log.info("Generating slide plan and agent-flow diagram in parallel...")
    (plan, plan_provider), flow_png = await asyncio.gather(
        generate_slide_plan(sections),
        render_agent_flow_png(config.AI_GRADING_DIR / "agent_flow.png"),
    )
    providers["slide_plan"] = plan_provider
    log.info("Slide plan: %d slides, provider=%s", len(plan.slides), plan_provider)
    _write_json(plan, config.AI_GRADING_DIR / "slide_plan.json")
    log.info("Wrote ai_grading/slide_plan.json and ai_grading/agent_flow.png")

    # Stage: draft HTML + draft narration audio, in parallel across all slides.
    log.info("Drafting HTML + narration for %d slides (parallel)...", len(plan.slides))
    drafts = await asyncio.gather(*(_draft_slide(s, providers) for s in plan.slides))

    # Stage: critique + revise every slide, in parallel across all slides.
    log.info("Critiquing + revising %d slides (parallel)...", len(plan.slides))
    critiques = await asyncio.gather(
        *(critique_and_revise(slide, html_result) for slide, html_result in drafts)
    )
    for c in critiques:
        providers[f"slide_{c[0].slide_index}_critique"] = c[1]
    critique_feedback = CritiqueFeedback(critiques=[c[0] for c in sorted(critiques, key=lambda c: c[0].slide_index)])
    _write_json(critique_feedback, config.AI_GRADING_DIR / "critique_feedback.json")
    log.info("Wrote ai_grading/critique_feedback.json")

    revised_slides: list[Slide] = []
    for slide, _ in drafts:
        crit = next(c for c, _ in critiques if c.slide_index == slide.index)
        revised_slides.append(
            slide.model_copy(
                update={
                    "description": crit.revised_description,
                    "narration": crit.revised_narration,
                }
            )
        )

    # Stage: regenerate final HTML+PNG and final audio, in parallel across all slides.
    log.info("Finalizing HTML/PNG + narration for %d slides (parallel)...", len(revised_slides))
    async with SlideRenderer() as renderer:
        slides_av = await asyncio.gather(
            *(_finalize_slide(s, renderer, providers) for s in revised_slides)
        )

    # Stage: stitch into the final reel (per-slide clip build is itself parallel).
    log.info("Stitching %d slide clips into the final reel...", len(slides_av))
    video_path, total_seconds = await build_reel(list(slides_av), out_video)

    elapsed = time.time() - t0
    n_mock = sum(1 for v in providers.values() if v == "mock-offline" or "fallback" in v)
    log.info("=" * 72)
    log.info("DONE in %.1fs", elapsed)
    log.info("  reel:              %s  (%.1fs)", video_path, total_seconds)
    log.info("  slides/:           %d HTML files", len(revised_slides))
    log.info("  ai_grading/:       slide_plan.json, critique_feedback.json, agent_flow.png")
    log.info("  provider calls:    %d total, %d used the offline fallback", len(providers), n_mock)
    if n_mock:
        log.warning(
            "%d/%d calls fell back to offline mock providers (see log above for why) — "
            "set OPENAI_API_KEY in .env for real gpt-5.6-luna/tts-1-hd output.",
            n_mock, len(providers),
        )
    log.info("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=config.PROPOSAL_PATH)
    parser.add_argument("--out", type=Path, default=config.VIDEO_PATH)
    args = parser.parse_args()

    if not args.proposal.exists():
        log.error("Proposal file not found: %s", args.proposal)
        sys.exit(1)

    asyncio.run(run(args.proposal, args.out))


if __name__ == "__main__":
    main()
