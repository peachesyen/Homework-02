"""Central configuration: paths, model names, and provider settings.

Model names are fixed by the HW2 assignment spec (`gpt-5.6-luna` for all LLM
output, `tts-1-hd` for all TTS output) but are still read from the
environment so they can be pointed at a course-provided proxy/base_url
without touching code.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
SLIDES_DIR = REPO_ROOT / "slides"
AI_GRADING_DIR = REPO_ROOT / "ai_grading"
BUILD_DIR = REPO_ROOT / "build"
FRAMES_DIR = BUILD_DIR / "frames"
AUDIO_DIR = BUILD_DIR / "audio"
VIDEO_PATH = BUILD_DIR / "reel.mp4"
PROPOSAL_PATH = REPO_ROOT / "project_proposal.md"

for _d in (SLIDES_DIR, AI_GRADING_DIR, FRAMES_DIR, AUDIO_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- LLM (assignment requires gpt-5.6-luna for all LLM output) ---
LLM_MODEL = os.environ.get("REEL_LLM_MODEL", "gpt-5.6-luna")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# Optional: point at a course-provided proxy that aliases gpt-5.6-luna to a
# real backing model, if the standard api.openai.com endpoint doesn't serve it.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None

# --- TTS (assignment requires tts-1-hd; Gemini TTS allowed as an alternative) ---
TTS_PROVIDER = os.environ.get("REEL_TTS_PROVIDER", "openai")  # "openai" | "gemini"
TTS_MODEL = os.environ.get("REEL_TTS_MODEL", "tts-1-hd")
TTS_VOICE = os.environ.get("REEL_TTS_VOICE", "alloy")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_TTS_MODEL = os.environ.get("REEL_GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.environ.get("REEL_GEMINI_TTS_VOICE", "Kore")

# --- Video / timing budget ---
MAX_SLIDE_SECONDS = 15
TARGET_TOTAL_SECONDS = (30, 60)
FRAME_WIDTH, FRAME_HEIGHT = 1280, 720

# --- Playwright ---
# Leave unset to let Playwright auto-resolve its installed browser (normal
# path after `playwright install chromium`). Set to override, e.g. in a
# sandbox where the browser lives at a fixed non-standard path.
CHROMIUM_EXECUTABLE_PATH = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or None

# --- ffmpeg ---
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

MOCK_MODE_BANNER = (
    "[reel_agent] No usable {what} credentials/model found — "
    "falling back to the offline mock {what} provider so the pipeline "
    "still runs end-to-end. Set the relevant API key in .env for real output."
)
