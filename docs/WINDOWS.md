# democap on Windows — quick start & port guide

democap is macOS-first today, but Windows is the **recommended next platform**: the
two things that fight macOS automation (OBS screen capture, driving Excel Copilot)
tend to be easier on Windows. This page is both a user quick-start and a porter's
checklist.

## Why Windows is likely smoother

- **Capture:** OBS uses **Windows Graphics Capture** — it grabs a specific window
  handle and follows it across monitors, without the ScreenCaptureKit
  black-frame-on-display-change failure that plagues macOS. The warm-up/trim logic in
  `obs_control.py` still applies, but the "re-toggle permission" recovery dance
  largely disappears.
- **Driving Copilot:** Windows `SendInput` generally **reaches WebView2 controls**, so
  typing a question into Excel's Copilot pane is likely to work — the exact thing the
  macOS embedded web view rejected.

## Quick start

Prerequisites: **Python 3.11+**, **winget** (ships with Windows 10/11). OBS, ffmpeg,
Chrome, and Office are installed for you by bootstrap where possible.

```powershell
git clone https://github.com/FrostyyOPP/democap.git
cd democap
python bootstrap.py                  # installs ffmpeg + OBS via winget, venv, deps, Chromium
.venv\Scripts\democap setup-obs      # enable OBS WebSocket + create capture scenes
.venv\Scripts\democap doctor         # verify everything is ready
```

The one unavoidable manual step is the same as macOS: grant OBS the screen-recording
permission when Windows/OBS prompts, then relaunch OBS.

Try the parser (no recording):

```powershell
.venv\Scripts\democap analyze samples\sample_script.docx
```

### Driving the real Chrome over CDP (for Gemini-style browser demos)

Launch Chrome once with remote debugging, then democap attaches to it:

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\democap\.chrome-cdp"
```

`config/default.yaml` already defaults to `recording.browser.connect: cdp`.

## Port checklist (`democap/platform/windows.py`)

The file is stubbed. Implement these and wire a platform factory keyed on
`platform.system()`:

| Area | macOS (done) | Windows (to do) |
|---|---|---|
| App detection | `/Applications`, `mdfind`, bundle id | registry uninstall keys, `where`, Start-Menu `.lnk` scan |
| Launch app | `open -a` | `os.startfile` / `start` |
| Foreground/window | AppleScript bounds | `pywinauto` / Win32 `SetForegroundWindow` |
| Type / keys | AppleScript System Events | `SendInput` (reaches WebView2 → Copilot) |
| Desktop element clicks | computer-use | UI Automation (`pywinauto`/`uiautomation`) |
| OBS capture kind | `screen_capture` type 2 (application) | `window_capture` (verify the matcher) |
| ffmpeg screen fallback | `avfoundation` | `gdigrab` / `ddagrab` |

### Already cross-platform (no change needed)

- `obs_setup.py` — detects the OBS config dir (`%APPDATA%\obs-studio`) and picks
  `window_capture` on Windows. **Verify the window match string**: OBS Windows window
  capture matches by `Title:WindowClass:Executable.exe`. The current stub uses
  `::<exe>`; refine to a robust matcher (e.g. enumerate windows for the target exe).
- `obs_control.py` — warm-up/trim/preflight all OS-agnostic.
- `bootstrap.py` — already uses winget/choco on Windows.
- The whole parsing/classification/course pipeline — pure Python, OS-agnostic.

### Suggested first PRs

1. `window_capture` matcher in `obs_setup.py` that reliably binds to Excel/Chrome.
2. `platform/windows.py` app detection + launch + `SendInput` typing.
3. Re-run the Excel **Copilot** demo on Windows end-to-end (the macOS blocker) and
   record a clean MP4 to prove the path.
