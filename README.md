# Tailtale — `reel_agent.py`

Turns `project_proposal.md` into a narrated, critiqued, stitched highlight-reel
video. One command:

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# edit .env and paste in your real OPENAI_API_KEY

python reel_agent.py project_proposal.md
```

Output lands in `output/` (`full_video.mp4`, `reel.mp4`) and `ai_grading/`
(`slide_plan.json`, `critique_feedback.json` — written fresh on every run).

## Repo layout (matches the required grading structure)

```
README.md
requirements.txt
.gitignore                  .env is in here — never committed
project_proposal.md         the actual Tailtale proposal (the agent's input)
reel_agent.py                the agent — run this
test_reel_agent.py            offline pytest suite for reel_agent.py — see
                              "Verifying the agent code offline" below
slides/                      hand-built HTML templates, one per slide number
                              (01-hook.html, 02-solution.html, ...) — used in
                              the reel. If a plan produces a slide number with
                              no matching template here, reel_agent.py falls
                              back to a clean generated layout.
ai_grading/
  ├── slide_plan.json               required: this run's slide plan
  ├── critique_feedback.json        required: critique + what was revised
  ├── agent_flow.png                required: the pipeline diagram
  ├── agent_flow.html                (source for the diagram, for reference)
  └── sample_live_planner_output.json  bonus: a genuinely fresh planner run
                                        from today, proof the agent works
                                        end-to-end on the real proposal —
                                        see "How this was tested" below
```

`reel.mp4` is **not** in this repo on purpose — the assignment wants it
uploaded to the grading website, not committed to GitHub.

## Stack

- **Python + PydanticAI**, with real registered tools, not just structured
  output:
  - **Planner agent** (`plan_from_proposal`) — reads the proposal, returns a
    structured `SlidePlan`. Has a `count_words` tool it's instructed to call
    on every narration draft before finalizing, so the ~15s/~40-word budget
    is checked, not guessed.
  - **Critic agent** (`critique_slide`) — takes the rendered PNG *and* the
    narration text together, returns a structured `SlideCritique` covering
    both. Has a `contrast_ratio` tool (real WCAG luminance-ratio math) so
    contrast judgments are computed, not eyeballed, plus the same
    `count_words` tool for narration length.
  - **Reviser agent** (`revise_narration`) — only invoked when the critic
    flags the narration; rewrites it to fit, verifying with `count_words`.
- **`openai:gpt-5.6-luna` for all three agents, always** — set via
  `LLM_MODEL` in `.env`, defaulting to `gpt-5.6-luna` and not meant to be
  changed in normal use. This is a hard assignment requirement, not a
  provider default that shifts with other settings.
- **`tts-1-hd` for narration by default.** `TTS_PROVIDER=gemini` in `.env`
  is the one explicitly-allowed substitution — for narration only, for a
  more expressive voice — and does not affect which model the agents above
  use.
- `requirements.txt` pins what's needed; `.env.example` is the template.

## Parallelization

Three stages fan out across all slides concurrently (with real timing
logged on every run): render + TTS synthesis together, critique, and
segment stitching. Two stages run once, sequentially, because they mutate
shared state or their order encodes meaning: enhance (patches shared files
and rewrites the plan's narration) and assemble (concatenation order is the
video's narrative order). See `ai_grading/agent_flow.png` for the full
diagram with every stage's tool and inputs/outputs.

Per-endpoint concurrency limits and retry/backoff exist because parallel
fan-out reliably trips provider rate limits in practice, not hypothetically
— see "How this was tested" below for what that looked like.

## CLI options

```
python reel_agent.py [proposal.md]
  --templates-dir DIR     hand-built slide templates (default: slides/)
  --out-dir DIR           run artifacts: renders, audio, video (default: output/)
  --grading-dir DIR       where slide_plan.json / critique_feedback.json go (default: ai_grading/)
  --max-slides N          cap on slide count (default: 6)
  --voice NAME            TTS voice (default: onyx for OpenAI, Kore for Gemini)
  --reel-seconds N        target reel length, 30-60 required by the assignment (default: 55)
  --skip-critique         skip the critique/enhance stages
  --plan-json FILE        resume from a previously saved slide_plan.json instead of re-planning
  --audio-cache DIR       reuse WAVs from a prior run instead of re-calling TTS
  --chrome-path PATH      Chromium executable, if Playwright can't find one
```

`--plan-json` and `--audio-cache` matter beyond convenience: re-running the
whole pipeline from scratch after tweaking one CSS token means paying for a
fresh LLM call and a fresh TTS call per slide for no reason. Both flags let
you re-run only the deterministic stages against already-paid-for content.

## Verifying the agent code offline (no API key, no network, no cost)

```bash
pip install -r requirements.txt   # includes pytest + pytest-asyncio
pytest test_reel_agent.py -v
```

This is the answer to "how do I know the PydanticAI wiring actually works"
without spending quota against a live provider. It uses PydanticAI's own
`TestModel` to drive every agent (planner, critic, reviser) through a real
`agent.run()` — real schema validation, real tool registration, real tool
invocation — with a fake, free, deterministic model standing in for the LLM.
24 tests, all passing, covering:

- **WCAG contrast math** against the textbook reference (black/white = 21:1
  exactly) and a regression pin on the exact `--muted` token shipped in
  `slides/*.html`.
- **Reel-speed math**, including the real 94.56s → 50s → 1.89x case this
  project actually shipped, the 2x clamp, and ffmpeg duration parsing.
- **`enhance_html`**, checked for both correctness and idempotency (running
  it twice on an already-patched file must be a no-op).
- **Slide template fallback resolution** (hand-built template found → used;
  missing → falls back to `GENERIC_TEMPLATE`, populated with the plan's own
  title/description).
- **Planner and critic agent wiring**: a real `agent.run()` returns a
  schema-valid `SlidePlan` / `SlideCritique`, and their registered tools
  (`count_words`, `contrast_ratio`) are actually invoked mid-run, not just
  declared — proven by patching the live tool call path
  (`Tool.function_schema.function`, not just the `Tool.function` alias) and
  checking it fires.
- **Retry logic**: a transient error (`"429 Too Many Requests"`) is retried
  and eventually succeeds; a non-transient error (a real bug) raises
  immediately on the first attempt, with no wasted retries.

Two real robustness bugs were found and fixed by this suite, not just
tested around:

1. `contrast_ratio` crashed with an unhandled `ValueError` on a malformed
   hex string instead of giving the model a chance to correct itself. Fixed
   by validating input and raising `pydantic_ai.ModelRetry` instead, so a
   bad tool call becomes a guided retry, not a dead run. (Its examples are
   also now documented in the tool's JSON schema via `Field(examples=...)`,
   which independently helps a real LLM call it correctly the first time.)
2. Transient-vs-fatal error detection used naive substring matching (`"500"
   in str(e)`), which could false-match bare numbers inside an unrelated
   message. Replaced with `_is_transient()`: word-boundary regex for HTTP
   status codes plus a curated phrase list, so retries only happen for
   errors that are actually transient.

This does not replace a live run against the real `gpt-5.6-luna` /
`tts-1-hd` endpoints (see below for what *was* run live) — no test can
prove a specific provider's network path from inside a unit test. What it
proves is that the agent's own code is correctly wired end-to-end, which is
the part a deterministic test suite can actually settle, and it catches
regressions for free on every future change.

## How the live pipeline was tested

`api.openai.com` is unreachable from the sandbox this was built in — an
organization network policy blocks it outright, unrelated to the code or
the key. So `gpt-5.6-luna` and `tts-1-hd`, the required defaults, could not
be executed end-to-end in that environment. What **was** run there, live,
substituting a Gemini model only for local testing (`LLM_MODEL=google:...`,
`TTS_PROVIDER=gemini`), proves the architecture works:

- **The planner agent, live, on the real proposal** — produced a genuine
  6-slide plan (see `ai_grading/sample_live_planner_output.json`) with its
  own original titles and narration, not a copy of anything pre-written.
- **The critic agent's tools, live, with real output**: on an
  already-revised slide, it called `contrast_ratio` and returned specific
  computed ratios (e.g. "~2.56:1", "~4.14:1") for named elements — not
  vague color guesses. `critique_feedback.json`'s "ROUND 2" note on slide 5
  documents this run, including a follow-up recomputation against the
  actual shipped CSS values (10.21:1 / 9.97:1) that shows the critic's
  screenshot-based estimate was overcautious rather than a real defect —
  logged rather than silently trusted or dismissed either way.
- **Tool-calling itself**, independently confirmed: a minimal test agent
  with a registered tool actually invoked it mid-run (printed proof in
  development logs) before a quota error hit on the *next* call.
- **The full render → audio → stitch → assemble → reel pipeline**, producing
  a 93.96s full video and reels at both 55.04s and 50.08s with correct
  video/audio streams.

Two real, reproducible problems surfaced by actually running this, worth
knowing before you run it yourself:

1. **Gemini's free tier caps individual preview models at 10-20 requests
   per project per day.** Repeated same-day testing across multiple models
   exhausted several of them while building this. The retry logic correctly
   identifies `RESOURCE_EXHAUSTED` and reports it plainly rather than
   retrying forever pretending it's transient. OpenAI's paid tier doesn't
   have this problem, which is one more reason it's the required default.
2. **Firing every slide's API call at once trips rate limits that firing
   them one-at-a-time doesn't**, even inside a single provider's quota
   window. `TTS_SEMAPHORE` and `API_SEMAPHORE` cap concurrency per-endpoint
   rather than sharing one budget, because different endpoints hit
   different limits in testing.

## Design choice worth flagging

The six hand-built templates in `slides/` are a fixed, hand-designed system,
built and critiqued across several rounds. The planner agent's job is to
derive accurate *content* (titles, on-screen copy, narration) from whatever
proposal it's given — for slide numbers with no matching template,
`reel_agent.py` falls back to a clean generated layout (`GENERIC_TEMPLATE`
in the source), so the tool works on a proposal it's never seen, just with
a plainer look than the six purpose-built Tailtale slides.
