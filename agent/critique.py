"""The 'enhance every slide' pass: critique on-screen description + narration,
then produce a revised version of both. Thin wrapper over `llm.critique_slide`
that also keeps a record of which provider actually produced each critique
(real `gpt-5.6-luna` vs. the offline mock fallback).
"""

from __future__ import annotations

from . import llm
from .models import Slide, SlideCritique, SlideHTML


async def critique_and_revise(slide: Slide, html_result: SlideHTML) -> tuple[SlideCritique, str]:
    """Critiques one slide's description+narration and writes revised versions.

    Returns (critique, provider_label_used).
    """
    critique, provider = await llm.critique_slide(
        slide_index=slide.index,
        description=slide.description,
        narration=slide.narration,
        visual_summary=html_result.visual_summary,
    )
    return critique, provider
