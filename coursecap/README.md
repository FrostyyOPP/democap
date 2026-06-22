# coursecap — script-to-video course capture (app-agnostic)

A small, open pipeline that turns a course **script** into a finished lesson
**video**: record the on-screen demos, (optionally) generate a voiceover, then
assemble a synced or visual-only walkthrough with focus highlights and slide
placeholders.

## Not tied to any one app

This is the important part: **coursecap is not an "Excel tool."** The capture
engine works for whatever a given lesson needs, decided **course by course,
script by script** — never hard-coded:

| What the lesson shows | How it's captured |
|---|---|
| Any **desktop app** (Excel, PowerPoint, Word, an IDE, a design tool, …) | OBS Studio **Window Capture** bound to that app's window by executable/title — captures the app's own surface, so other apps' overlays never appear |
| Any **web app / browser flow** (Gemini, a SaaS dashboard, docs, …) | **Playwright** driving a real browser (msedge/chrome/chromium), recorded as native viewport video |

A single lesson can mix both — e.g. lesson 1.1 records an **Excel** segment *and*
a **browser (Gemini)** segment, and the assembler treats them identically (see
[`lessons/lesson_1_1.json`](lessons/lesson_1_1.json)). The only app-specific
data — which window to capture, the on-screen coordinates to highlight, the cut
points — lives in the per-lesson JSON spec, which is exactly where course
specifics belong.

## Pipeline

```
script ──► record ──► (tts) ──► assemble ──► lesson video
```

1. **record** ([`recorder.py`](recorder.py)) — drive the app/browser while
   capturing. `bind_window()` points OBS at *any* window; `record_browser()`
   captures *any* browser. The driving (clicks/typing) is supplied by the caller
   (a computer-use / UI-automation layer), so it's not bound to one app.
2. **tts** ([`tts.py`](tts.py), optional) — ElevenLabs voiceover, one mp3 per
   script segment. Key via `ELEVENLABS_API_KEY` env var (never written to disk).
3. **assemble** ([`assemble.py`](assemble.py)) — reads a lesson JSON spec and
   builds the video with ffmpeg. Two modes:
   - **`synced`** — the voiceover drives the timeline. Each clip is
     **anchor-aligned** (piecewise time-warp) so on-screen events land on their
     narration beat; slides fill non-recorded beats; focus boxes highlight the UI
     element the script is talking about.
   - **`screenshare`** — no audio; clean visual-only walkthrough. Clips are cut to
     the listed segments (dropping dead time) and concatenated; slides get a fixed
     duration.

## Add a new lesson

1. Record the demo segment(s) for the app(s) the script uses → save under `runs/`.
2. (synced only) Put the narration in a JSON list and run `tts.py`.
3. Write a spec in `lessons/` (copy an existing one); set `mode`, the clip paths,
   the cut points / align anchors, and any focus `boxes`.
4. `python -m coursecap.assemble lessons/<your_lesson>.json`

## Requirements

System Python 3.11+, ffmpeg, OBS Studio (with obs-websocket), and a browser for
Playwright. See the repo root [README](../README.md) and `bootstrap.py`. On
Windows, set `PYTHONUTF8=1`.

## Notes / known gotchas

- Outputs (`runs/`, `*.mp4`, `*.webm`) are git-ignored — only code + specs are tracked.
- Excel Copilot performs data *transforms* by generating a **new cloud file**, not
  by editing the sheet live; reproduce the cleaned result locally for the reveal
  shot if needed (see `make_cleaned.py`).
- OBS Window Capture (WGC) needs a brief warm-up to avoid black opening frames —
  `recorder.record()` handles it.
