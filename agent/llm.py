"""All LLM ("gpt-5.6-luna") structured-output calls, via PydanticAI.

Every public function here follows the same shape: try the real model,
and if that raises for any reason (no key, model not served, network
blocked), log a clear warning and fall back to the deterministic offline
mock in `mock_provider.py` so the rest of the pipeline still runs.
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from . import config, mock_provider
from .models import MAX_NARRATION_WORDS, SlideCritique, SlidePlan
from .proposal import ProposalSections
from .text_utils import cap_words

logger = logging.getLogger("reel_agent.llm")

_model_cache: OpenAIChatModel | None = None


def get_llm_model() -> OpenAIChatModel:
    global _model_cache
    if _model_cache is None:
        provider = OpenAIProvider(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
        _model_cache = OpenAIChatModel(model_name=config.LLM_MODEL, provider=provider)
    return _model_cache


async def run_structured(system_prompt: str, user_prompt: str, output_type):
    """Single structured LLM call. Raises on any failure; callers handle fallback."""
    agent = Agent(model=get_llm_model(), output_type=output_type, system_prompt=system_prompt)
    result = await agent.run(user_prompt)
    return result.output


SLIDE_PLAN_SYSTEM_PROMPT = f"""You are the creative director for a short
(30-60 second) video reel pitching a student's final project to a class.

You will receive the FULL text of the team's project_proposal.md. Read it
and produce a 4-6 slide plan (structured output) that tells the project's
story in order: hook -> problem -> how it works (generative AI angle) ->
who it's for -> honest limitation / what's next, roughly in that order,
condensed to fit the slide count.

Hard requirements:
- 4 to 6 slides total.
- Every slide needs a concrete `description` (exact on-screen text and a
  specific visual layout — not vague, an HTML/CSS/SVG author must be able
  to build it without asking questions) and a `narration` of at most
  {MAX_NARRATION_WORDS} words (it will be spoken aloud in under ~15s).
- Exactly ONE slide must have `is_primary_visual=True` and
  `visual_type="architecture_diagram_svg"` — this slide's description must
  specify a real diagram/infographic (boxes, arrows, icons drawn in
  HTML/CSS/SVG) illustrating the system's pipeline or architecture, not
  just a bullet list.
- Ground every slide in specifics from the proposal (project name, the
  actual AI models/APIs used, the actual audience, the actual limitation
  mentioned) — never generic filler.
- Keep total narration short enough that 4-6 clips at <=15s each land the
  whole reel in the 30-60 second target.
"""


async def generate_slide_plan(sections: ProposalSections) -> tuple[SlidePlan, str]:
    """Returns (plan, provider_label_used)."""
    if config.OPENAI_API_KEY:
        try:
            plan: SlidePlan = await run_structured(
                SLIDE_PLAN_SYSTEM_PROMPT,
                f"project_proposal.md:\n\n{sections.raw}",
                SlidePlan,
            )
            for s in plan.slides:
                s.narration = cap_words(s.narration, MAX_NARRATION_WORDS)
            primaries = [s for s in plan.slides if s.is_primary_visual]
            if len(primaries) != 1:
                for s in plan.slides:
                    s.is_primary_visual = False
                arch = [s for s in plan.slides if s.visual_type == "architecture_diagram_svg"]
                target = arch[0] if arch else plan.slides[min(2, len(plan.slides) - 1)]
                target.is_primary_visual = True
                target.visual_type = "architecture_diagram_svg"
            return plan, config.LLM_MODEL
        except Exception as exc:  # noqa: BLE001 - any provider failure -> fallback
            logger.warning(
                "LLM (%s) slide-plan generation failed (%s); using offline mock plan",
                config.LLM_MODEL,
                exc,
            )
    else:
        logger.warning(config.MOCK_MODE_BANNER.format(what="LLM"))
    return mock_provider.mock_slide_plan(sections), "mock-offline"


CRITIQUE_SYSTEM_PROMPT = f"""You are a tough but constructive video-reel
editor reviewing ONE slide (its on-screen description + spoken narration)
from a student project pitch.

Critique it honestly:
- List 1-3 concrete `issues` (too vague, narration too long/short, visual
  doesn't match narration, weak hook, missing a concrete detail, etc).
- List 1-3 concrete, actionable `suggestions` to fix them.
- Then WRITE the improved versions yourself: `revised_description` and
  `revised_narration` (narration must stay at or under {MAX_NARRATION_WORDS}
  words). The revision must actually apply your own suggestions — don't
  just restate the original.
- `change_summary`: one sentence on what actually changed.
"""


async def critique_slide(slide_index: int, description: str, narration: str, visual_summary: str) -> tuple[SlideCritique, str]:
    """Returns (critique, provider_label_used)."""
    if config.OPENAI_API_KEY:
        try:
            user_prompt = (
                f"Slide {slide_index}\n"
                f"Description (on-screen): {description}\n"
                f"Narration (spoken): {narration}\n"
                f"Rendered visual summary: {visual_summary}\n"
            )
            critique: SlideCritique = await run_structured(CRITIQUE_SYSTEM_PROMPT, user_prompt, SlideCritique)
            critique.slide_index = slide_index
            critique.original_description = description
            critique.original_narration = narration
            critique.revised_narration = cap_words(critique.revised_narration, MAX_NARRATION_WORDS)
            return critique, config.LLM_MODEL
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM (%s) critique failed for slide %s (%s); using offline mock critique",
                config.LLM_MODEL,
                slide_index,
                exc,
            )
    else:
        logger.warning(config.MOCK_MODE_BANNER.format(what="LLM"))
    from .models import Slide

    dummy = Slide(
        index=slide_index,
        title=f"Slide {slide_index}",
        description=description,
        narration=narration,
        visual_type="text_only",
    )
    return mock_provider.mock_critique(dummy), "mock-offline"
