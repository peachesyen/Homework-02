"""Small shared text helpers."""

from __future__ import annotations

import re


def cap_words(text: str, max_words: int) -> str:
    """Hard safety cap on narration length so TTS clips stay short.

    The LLM prompt already asks for <= max_words; this is the code-level
    backstop for when it doesn't comply exactly.
    """
    text = " ".join(text.split())
    words = text.split(" ")
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words])
    trimmed = re.sub(r"[,;:\-–—]+$", "", trimmed)
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "."
    return trimmed


def word_count(text: str) -> int:
    return len(text.split())


def strip_md(text: str) -> str:
    """Strip markdown noise (headings, bold/italic markers) so extracted
    proposal text reads as plain prose."""
    text = re.sub(r"^#{1,6}\s*(\d+(\.\d+)*\s*)?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return " ".join(text.split())


def first_sentence(text: str, max_chars: int = 400) -> str:
    text = strip_md(text)
    m = re.search(r"^(.*?[.!?])(\s|$)", text)
    sentence = m.group(1) if m else text
    if len(sentence) > max_chars:
        sentence = sentence[:max_chars].rsplit(" ", 1)[0] + "…"
    return sentence
