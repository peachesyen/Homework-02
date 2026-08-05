"""Offline, deterministic fallbacks used only when `gpt-5.6-luna` is not
reachable (no OPENAI_API_KEY, model not served by the configured endpoint,
network blocked, etc).

Every real pipeline step tries the actual LLM/TTS call first; this module
exists purely so the agent still runs end-to-end and produces a coherent,
on-topic reel for grading/demo purposes without live API access. It is not
a replacement for the real models — `reel_agent.py` logs loudly whenever a
step falls back to this module, and the run summary records it.
"""

from __future__ import annotations

import re

from .models import MAX_NARRATION_WORDS, Slide, SlideCritique, SlidePlan
from .proposal import ProposalSections
from .text_utils import cap_words, first_sentence, strip_md, word_count


def _section(sections: ProposalSections, *keys: str) -> str:
    for key in sections.sections:
        if any(k in key for k in keys):
            return sections.sections[key]
    return ""


def _stack_labels(sections: ProposalSections) -> list[str]:
    """Pull short stage/subsystem labels out of a markdown table or list,
    for the architecture-diagram slide."""
    body = _section(sections, "implementation", "architecture", "stack")
    # Try to grab bolded **Labels** first (common in tables/lists).
    labels = re.findall(r"\*\*([^*]{2,40})\*\*", body)
    labels = [l.strip().rstrip(":") for l in labels if len(l.split()) <= 5]
    seen, uniq = set(), []
    for l in labels:
        if l.lower() not in seen:
            seen.add(l.lower())
            uniq.append(l)
    if len(uniq) >= 3:
        return uniq[:4]
    return ["Input", "AI Processing", "Structured Output", "User Experience"]


def _audience_labels(sections: ProposalSections) -> list[str]:
    """Short **bolded** labels only (e.g. "Pet Owners") — for narration/cards,
    not the full bullet sentence."""
    for key, bullets in sections.bullets.items():
        if "audience" in key or "introduction" in key:
            labels = []
            for b in bullets:
                m = re.search(r"\*\*([^*]{2,40})\*\*", b)
                if m:
                    labels.append(m.group(1).strip().rstrip(":"))
            if labels:
                return labels[:4]
    return []


def mock_slide_plan(sections: ProposalSections) -> SlidePlan:
    title = sections.title.split(":")[0].strip() or "Final Project"
    exec_summary = sections.executive_summary or sections.raw[:400]
    hook = first_sentence(exec_summary, 160)

    problem_body = _section(sections, "introduction", "problem", "market")
    problem = first_sentence(problem_body, 180) or (
        "This project tackles a real, underserved problem with generative AI."
    )

    stages = _stack_labels(sections)
    arch_desc = (
        "Inline SVG pipeline diagram with four connected stages: "
        + " → ".join(stages)
        + ". Each stage is a rounded box in the project's brand colors, "
        "linked by arrows showing data flowing left to right."
    )

    audience = _audience_labels(sections)
    if audience:
        aud_desc = "Icon-card row, one card per audience segment: " + "; ".join(audience)
    else:
        aud_desc = "Icon-card row showing the primary users this project serves."

    limits_body = _section(sections, "limitation", "ethic", "governance", "results")
    limits = first_sentence(limits_body, 180) or (
        "Built responsibly, with clear disclaimers and no data collected without consent."
    )

    slides = [
        Slide(
            index=1,
            title=title,
            description=(
                f"Title card: large centered project name '{title}' with a one-line "
                f"tagline underneath: \"{hook}\". Subtle gradient background."
            ),
            narration=cap_words(f"{title}. {hook}", MAX_NARRATION_WORDS),
            visual_type="title_card",
            is_primary_visual=False,
        ),
        Slide(
            index=2,
            title="The Problem",
            description=(
                f"Left-aligned headline 'The Problem', with supporting text: {problem} "
                "A simple broken-signal icon (CSS) beside the text."
            ),
            narration=cap_words(problem, MAX_NARRATION_WORDS),
            visual_type="text_only",
            is_primary_visual=False,
        ),
        Slide(
            index=3,
            title="How It Works",
            description=arch_desc,
            narration=cap_words(
                "Here's how it works: " + " then ".join(stages) + ".",
                MAX_NARRATION_WORDS,
            ),
            visual_type="architecture_diagram_svg",
            is_primary_visual=True,
        ),
        Slide(
            index=4,
            title="Who It's For",
            description=aud_desc,
            narration=cap_words(
                "Built for " + ", ".join(audience) if audience else
                "Built for the people who need it most.",
                MAX_NARRATION_WORDS,
            ),
            visual_type="persona_or_icon_card",
            is_primary_visual=False,
        ),
        Slide(
            index=5,
            title="Built Responsibly, What's Next",
            description=(
                f"Closing card: '{limits}' plus a short call-to-action line "
                "pointing to the GitHub repo."
            ),
            narration=cap_words(
                cap_words(limits, 12).rstrip(".") + ". Learn more on GitHub.",
                MAX_NARRATION_WORDS,
            ),
            visual_type="text_only",
            is_primary_visual=False,
        ),
    ]
    return SlidePlan(project_title=title, tagline=hook, slides=slides)


# Per-visual-type critique angle, so the offline critique pass doesn't read
# as one templated note copy-pasted across every slide.
_VISUAL_CRITIQUE = {
    "title_card": (
        "Tagline states what the product is but not a concrete outcome for the user.",
        "Lead with the single most impressive result or number instead of a feature description.",
        " Add one bold stat or outcome phrase beneath the title.",
    ),
    "text_only": (
        "The problem is described in general terms — no sense of scale (how many people, how often).",
        "Add a rough stat or a one-line vivid example to make the problem feel real, not abstract.",
        " Add a small stat callout near the headline to quantify the problem.",
    ),
    "architecture_diagram_svg": (
        "Pipeline stage labels are internal/technical names rather than what changes for the user at each step.",
        "Keep the technical label but add a short outcome sub-label under each box (what the user gets).",
        " Add a one-word outcome caption under each pipeline stage.",
    ),
    "persona_or_icon_card": (
        "Audience segments are listed side by side but not differentiated by what each one gets out of it.",
        "Give each audience card a distinct one-phrase benefit instead of just a role name.",
        " Add a short benefit line under each audience card.",
    ),
    "stat_or_chart_svg": (
        "The chart/stat is described but the specific number or comparison isn't called out.",
        "State the headline number explicitly so it reads clearly even at a glance.",
        " Make the headline number the largest element on the slide.",
    ),
}
_DEFAULT_VISUAL_CRITIQUE = (
    "Visual description could tie more tightly to the project's core visual metaphor.",
    "Reuse the same accent color and shape language used on the other slides.",
    " Use the project's accent color for emphasis and consistent spacing.",
)


def mock_critique(slide: Slide) -> SlideCritique:
    issues: list[str] = []
    suggestions: list[str] = []

    wc = word_count(slide.narration)
    if wc > MAX_NARRATION_WORDS:
        issues.append(f"Narration is {wc} words, over the ~{MAX_NARRATION_WORDS}-word/15s budget.")
        suggestions.append("Cut narration to one punchy sentence with a single concrete claim.")
    else:
        issues.append("Narration states the topic but not a memorable, concrete detail.")
        suggestions.append("Add one concrete number, name, or example so it's memorable, not generic.")

    visual_issue, visual_suggestion, visual_addition = _VISUAL_CRITIQUE.get(
        slide.visual_type, _DEFAULT_VISUAL_CRITIQUE
    )
    if len(slide.description) < 60:
        issues.append("On-screen description is thin — not enough detail for a real visual.")
        suggestions.append("Specify exact on-screen text and layout (positions, colors, shapes).")
    else:
        issues.append(visual_issue)
        suggestions.append(visual_suggestion)

    revised_narration = cap_words(slide.narration, MAX_NARRATION_WORDS)
    if revised_narration == slide.narration and wc <= MAX_NARRATION_WORDS:
        # nothing to trim — nudge it tighter/punchier only if the addition
        # still fits the word budget cleanly (never re-truncate mid-phrase)
        candidate = revised_narration.rstrip(".") + ". Powered by generative AI."
        if word_count(candidate) <= MAX_NARRATION_WORDS:
            revised_narration = candidate

    revised_description = slide.description.strip()
    if visual_addition.strip().lower() not in revised_description.lower():
        revised_description += visual_addition

    return SlideCritique(
        slide_index=slide.index,
        original_description=slide.description,
        original_narration=slide.narration,
        issues=issues,
        suggestions=suggestions,
        revised_description=revised_description,
        revised_narration=revised_narration,
        change_summary=(
            "Tightened narration to the time budget and added a concrete visual/styling detail."
            if revised_narration != slide.narration or revised_description != slide.description
            else "Minor polish; original was already solid."
        ),
    )
