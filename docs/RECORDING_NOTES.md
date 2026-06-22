# Recording notes & gotchas

Hard-won lessons from driving OBS + app automation for clean demo capture. Read
this before debugging a "black recording" or a demo that won't drive itself.

## The clean-capture principle

Never record the full display. The Claude/computer-use control overlay and orange
border are separate floating windows drawn *on top* of the screen, so:

- **Browser demos** → Playwright viewport video (the stream is the page render, not
  the screen — no overlay can appear), or OBS **Window Capture** of the browser.
- **Desktop app demos** → OBS **Window/Application Capture** of the target app. The
  compositor hands OBS the app's own surface, excluding other apps' overlays.
- **Never** Display capture when a window option exists — it catches the overlay.

## macOS gotchas (ScreenCaptureKit)

These cost real debugging time. `democap/obs_control.py` encodes the fixes.

1. **Warm-up = black frames.** OBS recordings are solid black for the first ~4–5
   seconds, then show real content. Always record a warm-up buffer and trim it off
   (`WARMUP_SECONDS`, auto-trimmed by `clean_recording`). A 2-second test clip
   samples only warm-up and *looks* black even when capture is fine — verify
   brightness at `ss >= WARMUP`, not `ss = 1` (`obs_control.brightness/preflight`).

2. **Sticky black-frame state.** Changing the display arrangement (plugging in /
   rearranging a monitor) or **resizing/moving the captured window** mid-session can
   drop ScreenCaptureKit into a black state that does **not** recover via OBS
   restart, source re-acquire, or removing the display pin. Recovery needs:
   - System Settings → Privacy & Security → **Screen & System Audio Recording** →
     toggle **OBS off then on** → quit & relaunch OBS, **or**
   - a reboot.
   Rule of thumb: once a scene previews/records content, **don't touch the window** —
   just record.

3. **Multi-monitor.** OBS's macOS Application Capture is pinned to a display UUID. If
   the app window is on monitor B but the source watches monitor A, you get black.
   Keep the captured app on the display the OBS source targets (or pick the app's
   current display in the source's properties).

4. **Occlusion.** A fullscreen app (e.g. a video player opened with `open file.mp4`)
   over the captured window makes the capture black. Don't auto-open the output MP4
   in a player if more recording is coming — use `open -R` to reveal in Finder.

## App-driving gotchas

- **Gemini (browser) is fully automatable.** Drive the *real* Chrome over CDP
  (`--remote-debugging-port=9222`) — type, submit, scroll all work, and OBS captures
  the Chrome window. This is the smoothest path.

- **Excel Copilot resists automation on macOS.** The Copilot pane is an embedded web
  control that **ignores synthetic keystrokes** (computer-use `type` doesn't reach
  it). Its "Analyse data" action also runs a long, self-recreating multi-step build
  that's hard to reset between takes. For Copilot specifically, the reliable path is
  **"you perform, I record"**: a human clicks/types in the pane while `obs_control`
  handles start → warm-up → stop → trim → export.

## "You perform, I record" recipe

```python
from democap.obs_control import clean_recording
with clean_recording("democap_clean", "runs/lesson.mp4"):
    input("Perform the demo in the app, then press Enter to stop...")
# -> runs/lesson.mp4, warm-up trimmed, capture-health pre-checked
```

## Windows outlook

The two macOS-hostile pieces above are usually easier on Windows:
- OBS uses **Windows Graphics Capture** (per-window handle), which follows a window
  across monitors and doesn't exhibit the same display-change black-frame failure.
- Synthetic input (SendInput) generally **does** reach WebView2 controls, so typing
  into Excel Copilot is more likely to work.

See `democap/platform/windows.py` for the (stubbed) port points.
