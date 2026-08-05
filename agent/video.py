"""Stitches per-slide PNG + narration audio into per-slide clips, then
concatenates them into the final ~30-60s reel.mp4 with ffmpeg.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from . import config

logger = logging.getLogger("reel_agent.video")


@dataclass
class SlideAV:
    index: int
    image_path: Path
    audio_path: Path
    audio_duration: float


async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({' '.join(cmd)}):\n{stderr.decode(errors='replace')[-2000:]}")


async def _build_clip(av: SlideAV, out_path: Path, fade_in: bool, fade_out: bool) -> float:
    duration = max(av.audio_duration + 0.5, 3.0)
    af = ["apad"]
    vf: list[str] = []
    if fade_in:
        vf.append("fade=t=in:st=0:d=0.3")
        af.append("afade=t=in:st=0:d=0.3")
    if fade_out:
        st = max(duration - 0.3, 0)
        vf.append(f"fade=t=out:st={st:.2f}:d=0.3")
        af.append(f"afade=t=out:st={st:.2f}:d=0.3")

    cmd = [
        config.FFMPEG_BIN, "-y",
        "-loop", "1", "-i", str(av.image_path),
        "-i", str(av.audio_path),
        "-filter_complex", f"[1:a]{','.join(af)}[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-t", f"{duration:.2f}",
        "-r", "24",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
    ]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd.append(str(out_path))
    await _run(cmd)
    return duration


async def build_reel(slides_av: list[SlideAV], out_path: Path) -> tuple[Path, float]:
    """Builds one clip per slide (in parallel) then concatenates them in order.

    Returns (video_path, total_duration_seconds).
    """
    slides_av = sorted(slides_av, key=lambda s: s.index)
    clip_dir = out_path.parent / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for i, av in enumerate(slides_av):
        clip_path = clip_dir / f"clip_{av.index}.mp4"
        tasks.append(
            _build_clip(av, clip_path, fade_in=(i == 0), fade_out=(i == len(slides_av) - 1))
        )
    durations = await asyncio.gather(*tasks)

    list_file = clip_dir / "concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{(clip_dir / f'clip_{av.index}.mp4').resolve()}'" for av in slides_av)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    await _run([config.FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)])

    total = sum(durations)
    lo, hi = config.TARGET_TOTAL_SECONDS
    if not (lo <= total <= hi):
        logger.warning(
            "Reel duration is %.1fs, outside the %d-%ds target — consider trimming narration length.",
            total, lo, hi,
        )
    return out_path, total
