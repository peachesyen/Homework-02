"""TTS ("tts-1-hd") narration synthesis, with an optional Gemini path and an
offline espeak-ng fallback so the pipeline still produces real audio clips
without any API key configured.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from . import config

logger = logging.getLogger("reel_agent.tts")


@dataclass
class TTSResult:
    path: Path
    provider: str
    fallback: bool
    duration_seconds: float


def _openai_tts_sync(text: str, out_path: Path, voice: str) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    with client.audio.speech.with_streaming_response.create(
        model=config.TTS_MODEL,
        voice=voice,
        input=text,
        response_format="mp3",
    ) as response:
        response.stream_to_file(str(out_path))


def _gemini_tts_sync(text: str, out_path: Path) -> None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.GEMINI_TTS_VOICE
                    )
                )
            ),
        ),
    )
    pcm_bytes = response.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)


def _espeak_fallback_sync(text: str, out_wav: Path) -> None:
    subprocess.run(
        ["espeak-ng", "-s", "165", "-v", "en-us+f3", "-w", str(out_wav), text],
        check=True,
        capture_output=True,
    )


text_len_cache: dict[Path, str] = {}


def _probe_duration_seconds(path: Path) -> float:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        # rough fallback estimate: ~2.5 words/sec at typical TTS pace
        text = text_len_cache.get(path, "")
        return max(1.5, len(text.split()) / 2.5)


async def synthesize(text: str, out_path: Path, voice: str | None = None) -> TTSResult:
    """Synthesize `text` to an audio file at `out_path` (async, runs sync SDKs in a thread)."""
    text_len_cache[out_path] = text
    voice = voice or config.TTS_VOICE
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if config.TTS_PROVIDER == "gemini" and config.GOOGLE_API_KEY:
        try:
            await asyncio.to_thread(_gemini_tts_sync, text, out_path)
            dur = await asyncio.to_thread(_probe_duration_seconds, out_path)
            return TTSResult(path=out_path, provider=config.GEMINI_TTS_MODEL, fallback=False, duration_seconds=dur)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini TTS failed (%s); trying tts-1-hd next", exc)

    if config.OPENAI_API_KEY:
        try:
            await asyncio.to_thread(_openai_tts_sync, text, out_path, voice)
            dur = await asyncio.to_thread(_probe_duration_seconds, out_path)
            return TTSResult(path=out_path, provider=config.TTS_MODEL, fallback=False, duration_seconds=dur)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI TTS (%s) failed (%s); falling back to offline espeak-ng", config.TTS_MODEL, exc)
    else:
        logger.warning(config.MOCK_MODE_BANNER.format(what="TTS"))

    wav_path = out_path.with_suffix(".wav")
    await asyncio.to_thread(_espeak_fallback_sync, text, wav_path)
    dur = await asyncio.to_thread(_probe_duration_seconds, wav_path)
    return TTSResult(path=wav_path, provider="espeak-ng (offline fallback)", fallback=True, duration_seconds=dur)
