#!/usr/bin/env python3
"""One-off: author the DogMood AI slide plan by hand (as UX/UI + web dev),
grounded in the real Figma mockup (figma.com/design/MyI8NfKD99ZghDQf93v8Kz),
validate it against the SlidePlan Pydantic schema, and write
ai_grading/slide_plan.json.

Not part of the runtime pipeline — reel_agent.py normally calls
llm.generate_slide_plan() to have gpt-5.6-luna produce this. This script
exists because the actual mockup screens (colors, copy, layout) are only
knowable by looking at the Figma file, which the LLM never sees.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config
from agent.models import Slide, SlidePlan

slides = [
    Slide(
        index=1,
        title="DogMood AI",
        description=(
            "Hero/splash card matching the app's onboarding screen: full-bleed "
            "coral-to-magenta gradient background (#ff7a59 -> #ff4d8d). Centered "
            "translucent-white pill badge 'AI EXPRESSION DETECTOR'. Below it, bold "
            "white headline 'DogMood AI' (54px). A 160px circular frame (white ring "
            "on translucent fill) containing a simple friendly dog face built from "
            "SVG shapes (two tilted ear ellipses, a round muzzle, two dot eyes, an "
            "orange nose, a small curved mouth) — no photo. Below the frame, one "
            "line of white/90%-opacity tagline text."
        ),
        narration="Meet DogMood AI — real-time dog emotion detection, right from your phone's camera.",
        visual_type="title_card",
        is_primary_visual=False,
    ),
    Slide(
        index=2,
        title="Pet Tech Tracks Steps. Not Feelings.",
        description=(
            "Light off-white card. Left-aligned bold headline 'Pet Tech Tracks "
            "Steps. Not Feelings.' Two small stat chips side by side beneath it: a "
            "gray chip '8,532 steps today', and an orange-bordered chip 'Mood: "
            "unknown?'. One supporting line below: owners miss early signs of "
            "stress, boredom, or illness because nothing is actually watching for "
            "them. Orange 'Generative AI powered' badge pinned bottom-left."
        ),
        narration="Step counters track movement, not mood — early signs of stress or illness go unnoticed.",
        visual_type="text_only",
        is_primary_visual=False,
    ),
    Slide(
        index=3,
        title="How It Works",
        description=(
            "Inline SVG infographic, four connected white rounded stage-cards "
            "(matching the app's real card style: 16px radius, soft shadow, "
            "colored 3px border alternating orange/magenta) laid out left to "
            "right with arrow connectors: (1) '20-Frame Capture' — echoes the "
            "capture screen's dashed orange tracking-circle motif, (2) 'Gemini 1.5 "
            "Flash — Multimodal Analysis', (3) 'Structured Mood JSON', (4) '3 "
            "Outputs: Avatar, Dashboard, DogSocial'. Small 'HOW IT WORKS' eyebrow "
            "label above in tracked orange uppercase."
        ),
        narration="Twenty frames in four seconds feed Gemini 1.5 Flash, which reads micro-expressions and outputs a mood.",
        visual_type="architecture_diagram_svg",
        is_primary_visual=True,
    ),
    Slide(
        index=4,
        title="See It In Action",
        description=(
            "Recreation of the app's real results-dashboard card: white card, "
            "top green 'ANALYSIS COMPLETE' pill, large text 'Hungry! 92% AI CONF' "
            "next to a circular orange progress ring at 92%. Below it, an "
            "'Emotion Mix' horizontal bar chart, four rows with orange/magenta/ "
            "purple/gray bars: Hungry 48%, Bored 25%, Upset 15%, Sad 12%, each "
            "with its percentage right-aligned."
        ),
        narration="Every scan returns a confidence score and a full emotion breakdown, not just one guess.",
        visual_type="stat_or_chart_svg",
        is_primary_visual=False,
    ),
    Slide(
        index=5,
        title="Beyond the Score",
        description=(
            "Three white icon-cards in a row, each echoing a real screen: (1) "
            "orange icon, 'Dog Companion' — reactive 3D avatar mirrors the "
            "detected mood; (2) magenta icon, 'DogSocial' — share AI-verified "
            "mood posts with other owners; (3) purple icon, 'Vet Finder' — a "
            "distress alert auto-suggests nearby vets. 'Beyond the Score' as the "
            "headline above the row."
        ),
        narration="Beyond the score: a reactive 3D avatar, a DogSocial feed, and a vet finder for real distress.",
        visual_type="persona_or_icon_card",
        is_primary_visual=False,
    ),
    Slide(
        index=6,
        title="Built Responsibly, For Everyone",
        description=(
            "Closing card, off-white background. Headline 'Built Responsibly, "
            "For Everyone'. Three small audience tags in a row: Pet Owners, "
            "Creators, Veterinarians. Below, a thin purple-bordered disclaimer "
            "box: 'A behavioral approximation, not a vet diagnosis.' Bottom line: "
            "'See the code on GitHub.'"
        ),
        narration="Built for owners, creators, and vets — a behavioral approximation, never a diagnosis. See the repo.",
        visual_type="text_only",
        is_primary_visual=False,
    ),
]

plan = SlidePlan(
    project_title="PetEmotion AI (DogMood AI)",
    tagline="Understand your dog's emotions with real-time AI analysis — barks, eyes, and ear posture translated instantly.",
    slides=slides,
)

out_path = config.AI_GRADING_DIR / "slide_plan.json"
out_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
print(f"Wrote {out_path} ({len(plan.slides)} slides)")
for s in plan.slides:
    print(f"  {s.index}. [{s.visual_type}{' *PRIMARY*' if s.is_primary_visual else ''}] {s.title}"
          f" — narration: {len(s.narration.split())} words")
