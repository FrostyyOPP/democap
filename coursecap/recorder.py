"""App-agnostic screen recorder for course capture.

This engine is NOT tied to any one application. It records:

  * ANY desktop app  -> OBS Studio "Window Capture" bound to that app's window
                        (matched by executable and/or title). Excel, PowerPoint,
                        Word, a code editor, a native design tool -- anything with
                        a window. The capture is the app's own window surface, so
                        other apps' overlays/borders never appear in the recording.
  * ANY web app      -> Playwright (a real browser, channel-configurable: msedge,
                        chrome, chromium) recorded via its native viewport video.

Which backend a given lesson uses is decided per course/script, not hard-coded.
Pass the target window (exe/title) or the URL; nothing here knows about Excel.
"""
from __future__ import annotations

import os
import time


# --------------------------------------------------------------------------- #
# Desktop apps -> OBS window capture (works for any windowed application)
# --------------------------------------------------------------------------- #
def obs_client(obs_cfg: dict):
    import obsws_python as obs
    return obs.ReqClient(host=obs_cfg.get("host", "localhost"),
                         port=int(obs_cfg.get("port", 4455)),
                         password=obs_cfg.get("password", ""), timeout=5)


def bind_window(cl, input_name: str, *, title: str = "", win_class: str = "",
                exe: str, method: int = 2, priority: int = 1, cursor: bool = True):
    """Point an OBS window-capture source at ANY app window.

    `exe` is the only required field (e.g. "EXCEL.EXE", "POWERPNT.EXE",
    "Code.exe", "chrome.exe"). title/class refine the match. method 2 = Windows
    Graphics Capture; priority 1 = match title then fall back to same executable.
    """
    window = f"{title}:{win_class}:{exe}"
    cl.set_input_settings(input_name, {"window": window, "method": method,
                                       "priority": priority,
                                       "capture_cursor": cursor}, overlay=True)


def record(cl, scene: str, do_actions, *, warmup: float = 1.5):
    """Select `scene`, start recording, run do_actions(), stop, return raw path.

    `do_actions` is a zero-arg callable that drives the app (e.g. via a
    computer-use / UI-automation layer) while OBS records. Returns the file OBS
    wrote, ready to transcode with assemble.to_mp4().
    """
    cl.set_current_program_scene(scene)
    time.sleep(0.5)
    cl.start_record()
    time.sleep(warmup)            # WGC warm-up: discard the first black frames
    try:
        do_actions()
    finally:
        resp = cl.stop_record()
    return getattr(resp, "output_path", None)


# --------------------------------------------------------------------------- #
# Web apps -> Playwright (any browser, native viewport video)
# --------------------------------------------------------------------------- #
def record_browser(steps, *, video_dir: str, profile_dir: str,
                   channel: str | None = "msedge", width: int = 1920,
                   height: int = 1080, headless: bool = False):
    """Drive `steps(page)` in a real browser and capture native viewport video.

    `channel` picks the browser (msedge/chrome/chromium). Returns the .webm path.
    No OBS needed -- Playwright records the page surface directly (clean).
    """
    from playwright.sync_api import sync_playwright

    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(profile_dir, exist_ok=True)
    with sync_playwright() as p:
        kwargs = dict(headless=headless, viewport={"width": width, "height": height},
                      record_video_dir=video_dir,
                      record_video_size={"width": width, "height": height})
        if channel:
            kwargs["channel"] = channel
        ctx = p.chromium.launch_persistent_context(profile_dir, **kwargs)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            steps(page)
            raw = page.video.path() if page.video else None
        finally:
            ctx.close()
    return raw
