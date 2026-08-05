"""Pydantic schemas shared across the reel agent's pipeline.

These are the structured-output contracts the LLM calls are constrained to
(via PydanticAI `output_type=`), and the on-disk shape of the two required
`ai_grading/` JSON artifacts (`slide_plan.json`, `critique_feedback.json`).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Budgeted for the offline espeak-ng fallback's slower ~1.9 words/sec pace
# (real tts-1-hd/Gemini speech is faster, so this is the conservative case)
# so that 4-6 slides at this cap keep the whole reel inside the 30-60s
# target, with real room under the <=15s-per-clip ceiling.
MAX_NARRATION_WORDS = 18

VisualType = Literal[
    "architecture_diagram_svg",  # the mandatory "real visual" slide
    "stat_or_chart_svg",
    "persona_or_icon_card",
    "title_card",
    "text_only",
]


class Slide(BaseModel):
    """One slide in the reel: what's on screen, and what's spoken over it."""

    index: int = Field(ge=1, le=6, description="1-based slide position")
    title: str = Field(description="Short on-screen headline for the slide")
    description: str = Field(
        description=(
            "What appears on screen: the concrete text content AND the "
            "visual (diagram/chart/layout) to draw. Specific enough that "
            "an HTML/CSS/SVG author could build it without guessing."
        )
    )
    narration: str = Field(
        description=(
            f"Spoken narration for this slide, <= {MAX_NARRATION_WORDS} words "
            "so the TTS clip stays at or under ~15 seconds."
        )
    )
    visual_type: VisualType = Field(
        description="What kind of visual this slide centers on"
    )
    is_primary_visual: bool = Field(
        default=False,
        description=(
            "True for the ONE slide that must be a real HTML/CSS/SVG "
            "illustration, infographic, or diagram (not just text with a "
            "small icon). Exactly one slide in the plan must set this True."
        ),
    )


class SlidePlan(BaseModel):
    """The full 4-6 slide plan for the reel (Homework 2 deliverable #2)."""

    project_title: str
    tagline: str = Field(description="One-line hook for the project")
    slides: Annotated[list[Slide], Field(min_length=4, max_length=6)]


class SlideHTML(BaseModel):
    """LLM-authored HTML for a single slide."""

    slide_index: int
    html: str = Field(
        description=(
            "A COMPLETE standalone HTML document (with <html><head><style>"
            "...</style></head><body>...</body></html>), self-contained "
            "(no external network requests), sized for a 1280x720 video "
            "frame."
        )
    )
    visual_summary: str = Field(
        description="One sentence describing the concrete visual rendered"
    )


class SlideCritique(BaseModel):
    """Critique + revision record for one slide (Homework 2 deliverable #5)."""

    slide_index: int
    original_description: str
    original_narration: str
    issues: Annotated[list[str], Field(min_length=1, max_length=5)] = Field(
        description="Concrete problems found with the slide/narration"
    )
    suggestions: Annotated[list[str], Field(min_length=1, max_length=5)] = Field(
        description="Concrete, actionable improvements"
    )
    revised_description: str = Field(
        description="Improved on-screen description incorporating the suggestions"
    )
    revised_narration: str = Field(
        description=f"Improved narration, still <= {MAX_NARRATION_WORDS} words"
    )
    change_summary: str = Field(
        description="One sentence: what actually changed between original and revised"
    )


class CritiqueFeedback(BaseModel):
    """Full critique pass across every slide (saved to critique_feedback.json)."""

    critiques: list[SlideCritique]
