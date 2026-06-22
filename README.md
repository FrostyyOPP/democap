# democap

Turn a Word (`.docx`) demo script into a **clean MP4 demo recording** on macOS —
no Claude control overlay, no orange border, no terminal UI in the final video.

democap reads your script, extracts ordered steps, figures out which tools each
step needs, checks whether they're installed, tells you if anything is missing,
and (once execution is wired up) drives the demo and records **only the target
app window or browser viewport** — never the full desktop.

> **Status (open-source v0.1, macOS-first):**
>
> | Capability | State |
> |---|---|
> | Parse `.docx` → ordered structured steps (numbered **and** VOICEOVER scripts) | ✅ working |
> | Demo-intent classifier (decides demo vs. narration from the voiceover) | ✅ working (heuristic; Claude drop-in) |
> | Split a full multi-lesson course into per-lesson plans | ✅ working |
> | Tool detection + readiness report | ✅ working |
> | **Browser** demo: drive + record a clean MP4 (Playwright video, or real Chrome via CDP + OBS) | ✅ working — proven end-to-end |
> | **Desktop** demo: OBS window-capture + clean MP4 (warm-up + trim baked in) | ✅ working for normal apps |
> | Excel **Copilot** pane driven by automation | ⚠️ macOS limitation — pane rejects synthetic keystrokes; use "you perform, I record" |
> | Windows port | 🚧 stubbed (`democap/platform/windows.py`) — likely smoother for capture + Copilot |
>
> Before recording, read **[docs/RECORDING_NOTES.md](docs/RECORDING_NOTES.md)** — it
> documents the macOS OBS/ScreenCaptureKit gotchas (black-frame warm-up, the sticky
> black state on window resize / display change, multi-monitor pinning) and the
> reliable workarounds, all encoded in `democap/obs_control.py`.

---

## Two script formats — and inferring demos from voiceover

democap auto-detects the script genre:

- **Numbered demo** — imperative `Step 1: Open Chrome` lists.
- **Video script** — `VOICEOVER:` narration with optional `[SCREEN CAPTURE]` /
  `[ZOOM]` / `[TYPE-ALONG]` directions (e.g. Starweaver scripts).

Video scripts usually **don't label which parts are demos**. So democap reads each
voiceover line and *infers* it with a **demo-intent classifier**: is the voice
describing an on-screen action to record, or just narrating a story over a slide?

| Voiceover (example) | Decision |
|---|---|
| "It is nine in the morning, a few weeks into your new job…" | narration |
| "Look at the top of the screen and find the Home tab." | **demo** |
| "Open your browser and go to gemini dot google dot com. Sign in." | **demo** (browser) |
| "Next, we turn that mess into clean data." | narration |

Classifier modes (`config/default.yaml` → `classifier.mode`): `heuristic` (free,
offline, default with no key), `claude` (Claude on every line), `hybrid` (heuristic
first, Claude resolves only the *ambiguous* lines), and `auto` (hybrid if
`ANTHROPIC_API_KEY` is set, else heuristic). Set the key in your environment/`.env`
to upgrade accuracy without changing any code. "Sticky app context" carries the
current app (Excel → Copilot → Gemini) across lines so a bare "Click it" still
routes correctly.

---

## Why the recording stays clean

The Claude control overlay / orange border is a **separate floating window drawn
on top of the screen**. democap avoids it by never recording the whole display:

| Step type | Backend | Why it's clean |
|-----------|---------|----------------|
| Browser   | **Playwright** native context video | Records the page viewport rendered by the browser — the OS screen (and any overlay) is never in the stream. |
| Desktop   | **OBS Window Capture** (obs-websocket) | Grabs the target app's own window surface from the compositor; other apps' overlays/borders aren't part of that window. |
| Fallback  | **FFmpeg** avfoundation crop region | A fixed rectangle over the app. Used only if OBS is unavailable; full-display capture is never offered. |

`forbid_fullscreen_capture: true` in config enforces this — democap refuses a
display capture if a window/region option exists.

---

## Requirements

Already present on a typical setup (this repo was scaffolded against):
macOS 12.3+, Python 3.11+, Homebrew, FFmpeg, OBS Studio, Google Chrome.

Everything else is Python packages installed into a local venv.

## Setup — one command

From a fresh clone (needs only system Python 3.11+ and a package manager —
Homebrew on macOS, winget on Windows, apt/dnf/pacman on Linux):

```bash
python3 bootstrap.py
```

This **fully automates** the install: system deps (ffmpeg, OBS via the package
manager), a project `.venv`, democap + all Python deps, and the Playwright
Chromium browser. No manual download or config editing.

Then two commands finish OBS (also automated):

```bash
.venv/bin/democap setup-obs   # enable OBS WebSocket + create capture scenes via API
.venv/bin/democap doctor      # verify ffmpeg, Playwright, OBS, and scenes are ready
```

> On Windows, use `.venv\Scripts\democap.exe` instead of `.venv/bin/democap`.

`setup-obs` quits/relaunches OBS, writes the WebSocket config (with a generated
password saved into `config/default.yaml`), and creates the `democap_clean` /
`democap_chrome` capture scenes over the API — no clicking in OBS.

**The one unavoidable manual step** (the OS protects it and it *cannot* be
scripted): grant OBS the **Screen Recording** permission. `setup-obs` opens that
settings pane for you; toggle OBS on, then quit & reopen OBS and run `democap
doctor`.

## Usage

```bash
# Phase 1-3: parse, route, detect tools, print readiness report.
democap analyze samples/sample_script.docx

# Save the structured steps as JSON:
democap analyze samples/sample_script.docx --json runs/steps.json

# Non-interactive (no missing-tool prompts), e.g. for CI:
democap analyze path/to/your_script.docx --no-prompt

# Phase 4-5 (execute + record): scaffolded, not yet implemented.
democap run samples/sample_script.docx
```

### Full multi-lesson courses

A combined course `.docx` (many lessons in one file) is split into lessons —
**one clean MP4 per lesson**. Boundaries are read from the document's own markers
(`Prompt Ledger — lesson X.Y`, the word-count notes, and the end-of-doc title
table); trailing appendices/checklists are ignored.

```bash
democap course path/to/Complete_Course_Scripts.docx --json-dir runs/course
```

This prints a per-lesson plan (title, est. minutes, demo vs. narration counts,
tools) and writes one JSON per lesson plus a `course_index.json`.

### Record one lesson (Phase 4+5)

```bash
democap run-lesson path/to/Complete_Course_Scripts.docx 1.1 --out runs/1_1.mp4
```

Executes that lesson's **browser** steps and records a clean MP4; **desktop
(Excel/Copilot) steps are deferred** and listed in `runs/1_1.runlog.json` for the
OBS desktop path. Browser recording follows `recording.browser.connect`:

- **`launch`** — Playwright opens its own Chromium against a persistent profile
  (`recording.browser.profile_dir`); sign into Google once and it stays logged in.
  Recorded with Playwright's native viewport video — no OBS needed.
- **`cdp`** — democap attaches to your **real Chrome** and OBS records the Chrome
  window. Start Chrome once with remote debugging:
  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 --user-data-dir="$HOME/democap/.chrome-cdp"
  ```

### OBS scene setup (desktop + cdp recording)

Create these scenes once in OBS (each = one **macOS Screen Capture** source set to
**Window** capture, bound to the right app — *not* a display capture):

| Scene name (config key) | Captures |
|---|---|
| `democap_clean` (`recording.obs.scene`) | the **Excel** window |
| `democap_chrome` (`recording.browser.obs_scene_chrome`) | the **Chrome** window |

Then OBS → *Tools → WebSocket Server Settings* → Enable, and put the port/password
in `recording.obs`. Window capture excludes overlays drawn by other apps, so the
Claude control UI / orange border never appears in the recording.

`analyze` performs **no GUI actions and records nothing** — it's always safe to run.

### What the readiness report tells you
- Every parsed step with its normalized **action**, **route** (browser / desktop /
  narration / undecided), tagged **tools**, and a ⚠ on risky steps.
- Each required tool: type, whether it's installed, how it was detected, and any
  browser alternative.
- A **verdict** (READY / NOT READY) and the clean-capture backend per route.
- If a desktop-required tool is missing, democap **stops and asks** whether to
  install it, use a browser alternative, or skip those steps. It never installs
  or substitutes on its own.

---

## Project layout

```
democap/
├── config/
│   ├── default.yaml         # capture mode, fps, resolution, OBS creds, export
│   └── tools_catalog.yaml   # tool aliases, detection, browser alternatives
├── samples/
│   ├── sample_script.docx           # example input
│   ├── parsed_steps.schema.json     # JSON schema for parsed output
│   └── parsed_steps.example.json    # example parsed output
├── democap/
│   ├── cli.py               # `democap analyze|run`
│   ├── models.py            # pydantic: Step, DemoScript, ToolStatus, ReadinessReport
│   ├── docx_parser.py       # .docx -> ordered raw text blocks
│   ├── step_extractor.py    # raw blocks -> structured Steps + required tools
│   ├── tool_detector.py     # macOS app/CLI/bundle detection
│   ├── decision.py          # browser-vs-desktop routing per step
│   ├── readiness.py         # build/print report; prompt on missing tools
│   ├── config.py            # YAML loaders
│   ├── orchestrator.py      # ties phases together (analyze())
│   ├── recorder/            # base interface + playwright/obs/ffmpeg backends
│   ├── executor/            # browser (Playwright) + desktop (computer-use) — Phase 4
│   └── platform/            # macos.py (done), windows.py (TODO stubs)
└── runs/                    # timestamped logs + final MP4s (gitignored)
```

## Open-source dependencies (and why each is needed)

| Package | Role |
|---------|------|
| **python-docx** | Read the `.docx` script into text blocks. |
| **playwright** | Drive browser steps *and* record the viewport as clean video. |
| **pydantic** | Validated `Step` / `Report` models that serialize to the JSON schema. |
| **typer** | The `democap` command-line interface. |
| **pyyaml** | Load `config/*.yaml`. |
| **obsws-python** | Control OBS recording (window capture) over obs-websocket. |
| **rich** | Readable readiness tables in the terminal. |
| FFmpeg *(system)* | Transcode/remux to final MP4; crop-region fallback capture. |
| OBS Studio *(system)* | Clean desktop window capture. |

## Configuration

- `config/default.yaml` — recording (fps, resolution, backends, OBS creds),
  export (codec/CRF), and behavior (pause on risky steps). Paths accept `~`.
- `config/tools_catalog.yaml` — add a tool by giving it `aliases` (substrings that
  imply it), a `classification` (`desktop_required` / `browser_capable` /
  `optional`), detection hints (`app_names`, `bundle_id`, `cli`), and an optional
  `browser_alt`.

Override either with `--config` / `--catalog`.

---

## Roadmap

**Done (macOS):** docx/voiceover parsing, demo-intent classifier, course splitting,
tool detection, browser execution (Playwright `launch` + real-Chrome `cdp`),
Playwright video + OBS window-capture recording, ffmpeg export, and `obs_control`
with warm-up/trim/preflight baked in. A full browser demo (Gemini over CDP + OBS)
was recorded clean, end-to-end.

**Next:**
- Stitch a lesson's browser + desktop segments into one MP4 (`ffmpeg concat`).
- Full-course `democap run` that rolls the record flow across all lessons.
- An optional Claude-backed pass for the demo-intent classifier (set `ANTHROPIC_API_KEY`).

### Windows port (the recommended next platform)

The two pieces that fight macOS automation are usually easier on Windows, so the
port is worth doing:
- **Capture:** OBS uses Windows Graphics Capture (per-window handle) — no
  display-change black-frame state, follows windows across monitors. The warm-up/
  trim logic in `obs_control` still applies but the sticky-black recovery dance
  largely goes away.
- **Driving Copilot:** SendInput generally reaches WebView2 controls, so typing into
  Excel Copilot is more likely to "just work" (the macOS blocker).
- **Port points** (`democap/platform/windows.py`): registry/`where`/Start-Menu app
  detection; `os.startfile` launch; pywinauto / UI Automation for desktop execution;
  ffmpeg fallback swaps `avfoundation` → `gdigrab`/`ddagrab`. Select the platform
  layer via a factory keyed on `platform.system()`.

---

## Contributing

PRs welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)** for dev setup, the codebase
map, and conventions. The highest-value contribution right now is the **Windows
port**: full guide and quick-start in **[docs/WINDOWS.md](docs/WINDOWS.md)**.
