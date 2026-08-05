"""Renders ai_grading/agent_flow.png: a diagram of the agent's pipeline —
nodes for every function/tool call, with each node's inputs and outputs,
and dashed groups marking the two steps that run in parallel across slides.

This diagram describes the fixed pipeline shape (it doesn't depend on a
particular run's data), so it's built as one static SVG and screenshotted
with the same headless Chromium used for the slides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ACCENT = "#7dd3fc"
ACCENT2 = "#f472b6"
BG_FROM = "#0b1020"
BG_TO = "#1b2540"
TEXT = "#f8fafc"
MUTED = "#a8b3c7"
IO_FILL = "rgba(244,114,182,0.14)"
STEP_FILL = "rgba(125,211,252,0.10)"


@dataclass
class Node:
    id: str
    title: str
    sub: str
    x: int
    y: int
    w: int = 300
    h: int = 110
    kind: str = "step"  # "step" | "io"

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass
class Edge:
    src: str
    dst: str


NODES: list[Node] = [
    Node("proposal", "project_proposal.md", "input file · the final project proposal", 550, 20, w=300, h=70, kind="io"),
    Node("plan", "generate_slide_plan()", "LLM: gpt-5.6-luna\nin: proposal text  →  out: SlidePlan (4-6 slides, JSON)", 500, 140, w=400, h=100),
    Node("html1", "generate_slide_html()", "LLM: gpt-5.6-luna\nin: Slide  →  out: SlideHTML (draft)", 160, 300, w=320, h=110),
    Node("tts1", "synthesize()", "TTS: tts-1-hd\nin: draft narration  →  out: draft audio.mp3", 920, 300, w=320, h=110),
    Node("critique", "critique_and_revise()", "LLM: gpt-5.6-luna (parallel across all slides)\nin: description + narration + visual summary\nout: SlideCritique (issues, suggestions, revised text)", 460, 460, w=480, h=120),
    Node("html2", "generate_slide_html()  — revised", "LLM: gpt-5.6-luna\nin: revised_description  →  out: final SlideHTML", 160, 630, w=320, h=110),
    Node("tts2", "synthesize()  — revised", "TTS: tts-1-hd\nin: revised_narration  →  out: final audio", 920, 630, w=320, h=110),
    Node("render", "render_html_to_png()", "Playwright / headless Chromium\nin: final HTML  →  out: slides/slide_N.png", 160, 800, w=320, h=100),
    Node("stitch", "build_reel()", "ffmpeg (per-slide clip build in parallel, then concat)\nin: slide_N.png + final audio  →  out: reel.mp4", 460, 950, w=480, h=110),
    Node("outputs", "Outputs", "reel.mp4  ·  slides/*.html  ·  ai_grading/slide_plan.json  ·  ai_grading/critique_feedback.json  ·  ai_grading/agent_flow.png", 300, 1110, w=800, h=100, kind="io"),
]

EDGES: list[Edge] = [
    Edge("proposal", "plan"),
    Edge("plan", "html1"),
    Edge("plan", "tts1"),
    Edge("html1", "critique"),
    Edge("tts1", "critique"),
    Edge("critique", "html2"),
    Edge("critique", "tts2"),
    Edge("html2", "render"),
    Edge("render", "stitch"),
    Edge("tts2", "stitch"),
    Edge("stitch", "outputs"),
]

GROUPS = [
    {"label": "parallel across all slides (asyncio.gather)", "x": 120, "y": 270, "w": 1160, "h": 160},
    {"label": "parallel across all slides (asyncio.gather)", "x": 120, "y": 600, "w": 1160, "h": 160},
]

CANVAS_W, CANVAS_H = 1400, 1250


def _node_box(n: Node) -> str:
    fill = IO_FILL if n.kind == "io" else STEP_FILL
    stroke = ACCENT2 if n.kind == "io" else ACCENT
    lines = n.sub.split("\n")
    sub_html = "".join(f'<div style="color:{MUTED}; font-size:14.5px; line-height:1.5;">{l}</div>' for l in lines)
    return f"""
    <rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="14"
          fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>
    <foreignObject x="{n.x+14}" y="{n.y+10}" width="{n.w-28}" height="{n.h-20}">
      <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:-apple-system,Helvetica,Arial,sans-serif;
           display:flex; flex-direction:column; justify-content:center; height:100%;">
        <div style="color:{TEXT}; font-size:18px; font-weight:800; margin-bottom:4px;">{n.title}</div>
        {sub_html}
      </div>
    </foreignObject>
    """


def _edge_path(e: Edge, nodes_by_id: dict[str, Node]) -> str:
    src, dst = nodes_by_id[e.src], nodes_by_id[e.dst]
    x1, y1 = src.cx, src.y + src.h
    x2, y2 = dst.cx, dst.y
    midy = (y1 + y2) / 2
    return (
        f'<path d="M{x1},{y1} C{x1},{midy} {x2},{midy} {x2},{y2}" '
        f'fill="none" stroke="{ACCENT}" stroke-width="2.5" marker-end="url(#arrow)"/>'
    )


def build_svg() -> str:
    nodes_by_id = {n.id: n for n in NODES}
    groups_svg = "".join(
        f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="20" '
        f'fill="none" stroke="{ACCENT2}" stroke-width="2" stroke-dasharray="8 6"/>'
        f'<text x="{g["x"]+g["w"]/2}" y="{g["y"]-10}" text-anchor="middle" '
        f'fill="{ACCENT2}" font-size="15" font-weight="700" '
        f'font-family="-apple-system,Helvetica,Arial,sans-serif" letter-spacing="1">{g["label"]}</text>'
        for g in GROUPS
    )
    edges_svg = "".join(_edge_path(e, nodes_by_id) for e in EDGES)
    nodes_svg = "".join(_node_box(n) for n in NODES)

    return f"""<!doctype html>
<html><head><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background: radial-gradient(1400px 1000px at 20% -10%, {BG_TO}, {BG_FROM} 60%); }}
  .wrap {{ padding: 30px; }}
  h1 {{ color:{TEXT}; font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:26px;
        text-align:center; margin-bottom: 6px; }}
  h2 {{ color:{MUTED}; font-family:-apple-system,Helvetica,Arial,sans-serif; font-size:16px;
        text-align:center; font-weight:400; margin-bottom: 12px; }}
</style></head>
<body>
  <div class="wrap">
    <h1>PetEmotion AI Reel Agent — Pipeline</h1>
    <h2>reel_agent.py · PydanticAI · gpt-5.6-luna (LLM) · tts-1-hd (TTS) · Playwright · ffmpeg</h2>
    <svg width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="{ACCENT}"/>
        </marker>
      </defs>
      {groups_svg}
      {edges_svg}
      {nodes_svg}
    </svg>
  </div>
</body></html>"""


async def render_agent_flow_png(out_path: Path) -> Path:
    from playwright.async_api import async_playwright

    from . import config

    html = build_svg()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        launch_kwargs = {"args": ["--no-sandbox"]}
        if config.CHROMIUM_EXECUTABLE_PATH:
            launch_kwargs["executable_path"] = config.CHROMIUM_EXECUTABLE_PATH
        browser = await pw.chromium.launch(**launch_kwargs)
        page = await browser.new_page(viewport={"width": CANVAS_W + 60, "height": CANVAS_H + 80})
        await page.set_content(html, wait_until="load")
        await page.screenshot(path=str(out_path), full_page=True)
        await browser.close()
    return out_path
