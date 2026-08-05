"""Loads and lightly parses project_proposal.md.

The parsed sections feed both the real LLM prompt (as grounding context)
and the offline mock fallback (which has no LLM to lean on at all, so it
needs actual text to build slides from).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config


@dataclass
class ProposalSections:
    raw: str
    title: str = "Untitled Project"
    executive_summary: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    bullets: dict[str, list[str]] = field(default_factory=dict)


def load_proposal_text(path=None) -> str:
    path = path or config.PROPOSAL_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"project_proposal.md not found at {path} — "
            "the agent reads this file as its required input."
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("project_proposal.md is empty")
    return text


def parse_sections(raw: str) -> ProposalSections:
    """Heuristic markdown split: '# Title' then '## N. Section Name' blocks."""
    result = ProposalSections(raw=raw)

    title_match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
    if title_match:
        result.title = title_match.group(1).strip()

    # Split on any level-2 heading ("## ...")
    parts = re.split(r"^##\s+(.+)$", raw, flags=re.MULTILINE)
    # parts[0] is preamble before first "## "; then alternating heading, body
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip()
        key = re.sub(r"^\d+\.\s*", "", heading).strip().lower()
        result.sections[key] = body
        result.bullets[key] = re.findall(r"^\*\s+.*$", body, re.MULTILINE)

    for key, body in result.sections.items():
        if "executive summary" in key:
            result.executive_summary = re.sub(r"\s+", " ", body).strip()

    return result
