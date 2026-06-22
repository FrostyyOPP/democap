# Contributing to democap

Thanks for helping turn demo scripts into clean recordings. This guide covers dev
setup, the codebase map, and where help is most wanted (the Windows port).

## Dev setup

```bash
git clone https://github.com/FrostyyOPP/democap.git
cd democap
python3 bootstrap.py          # venv + deps + ffmpeg/OBS + Playwright Chromium
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m playwright install chromium
```

Sanity-check it works (no recording, safe):

```bash
.venv/bin/democap analyze samples/sample_script.docx
.venv/bin/democap course  samples/sample_script.docx   # (single-lesson is fine)
.venv/bin/democap doctor
```

## Codebase map

```
democap/
├── docx_parser.py      # .docx -> ordered raw text blocks
├── segmenter.py        # detect script genre; label voiceover/direction/prompt
├── demo_intent.py      # decide demo-vs-narration from the voiceover (heuristic + Claude)
├── step_extractor.py   # blocks -> structured Steps (+ tool tags, sticky app context)
├── course_splitter.py  # split a multi-lesson course into per-lesson plans
├── tool_detector.py    # macOS app/CLI/bundle detection
├── decision.py         # browser-vs-desktop routing per step
├── readiness.py        # readiness report + missing-tool prompts
├── models.py           # pydantic models (Step, Lesson, Course, ToolStatus, ...)
├── config.py           # YAML config + tool-catalog loaders
├── orchestrator.py     # analyze() / analyze_course() / run_lesson()
├── obs_control.py      # OBS recording: warm-up/trim/preflight + clean_recording()
├── obs_setup.py        # enable WebSocket + create scenes (cross-platform)
├── recorder/           # playwright_rec, obs_rec, ffmpeg_rec, encode, base
├── executor/           # browser_exec, browser_session (CDP/launch), desktop_exec
├── platform/           # macos.py (done), windows.py (TODO)
└── cli.py              # typer CLI: analyze / course / run-lesson / setup-obs / doctor
```

Config lives in `config/` (`default.yaml`, `tools_catalog.yaml`). Samples and the
parsed-step JSON schema are in `samples/`.

## Conventions

- Python 3.11+, standard library + the deps in `pyproject.toml`.
- Prefer readable code over clever code; match the surrounding style.
- Keep platform-specific logic behind `democap/platform/` and per-OS branches in
  `obs_setup.py` — don't sprinkle `platform.system()` checks elsewhere.
- New recorder/executor backends implement the small interfaces in
  `recorder/base.py` / mirror `executor/browser_exec.py`.
- Read **docs/RECORDING_NOTES.md** before touching capture code — the macOS
  warm-up/black-frame behavior is subtle and already encoded in `obs_control.py`.

## Most-wanted: the Windows port

This is the highest-value contribution. See **docs/WINDOWS.md** for the full guide.
In short, implement `democap/platform/windows.py` and wire a platform factory:

- **Tool detection** — registry uninstall keys / `where` / Start-Menu `.lnk` scan.
- **Launch** — `os.startfile` / `start`.
- **Desktop execution** — pywinauto / UI Automation (and SendInput, which—unlike
  macOS—usually reaches WebView2 controls like Excel Copilot).
- **Recording** — OBS Windows Graphics Capture (per-window, no display-change
  black-frame issue); ffmpeg fallback swaps `avfoundation` → `gdigrab`/`ddagrab`.

`obs_setup.py` already branches per-OS for the OBS config path and capture input
kind — extend/verify the Windows `window_capture` matcher there.

## Testing a recording change

Capture is hard to unit-test, so verify by hand:

```python
from democap.obs_control import preflight, clean_recording
assert preflight("democap_chrome")          # capture is alive (not black)
with clean_recording("democap_chrome", "runs/test.mp4"):
    input("perform a quick demo, then Enter")  # "you perform, I record"
```

Then confirm the MP4 is non-black (`obs_control.brightness(path, 6) > 5`) and has no
overlay. Keep PRs focused; note any manual verification you did.
