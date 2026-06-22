"""Get a Playwright page to drive, in one of two connect modes.

  launch : Playwright starts its own Chromium against a PERSISTENT profile dir, so
           you sign into Google/Gemini once and stay logged in. This context can be
           recorded with Playwright's native viewport video (cleanest).

  cdp    : Attach to your REAL Chrome over the DevTools protocol, reusing your
           logged-in session. Playwright cannot video-record a browser it didn't
           launch, so in this mode the Chrome WINDOW is recorded via OBS instead.

To use cdp mode, start Chrome once with remote debugging enabled, e.g.:
    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 --user-data-dir="$HOME/democap/.chrome-cdp"
(A dedicated --user-data-dir avoids clashing with an already-running Chrome.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BrowserSession:
    page: object
    records_with_playwright: bool   # True=launch(video), False=cdp(OBS records window)
    _close: object

    def close(self):
        try:
            self._close()
        except Exception:
            pass


def open_session(config: dict, video_dir: str | None = None):
    """Return a BrowserSession with a ready-to-drive .page."""
    from playwright.sync_api import sync_playwright

    rec = config["recording"]
    bcfg = rec.get("browser", {})
    mode = bcfg.get("connect", "launch")
    vp = rec["playwright"]["viewport"]
    pw = sync_playwright().start()

    if mode == "cdp":
        browser = pw.chromium.connect_over_cdp(bcfg.get("cdp_url", "http://localhost:9222"))
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def _close():
            browser.close(); pw.stop()
        return BrowserSession(page=page, records_with_playwright=False, _close=_close)

    # launch mode: persistent profile + native video recording
    profile = os.path.expanduser(bcfg.get("profile_dir", "~/democap/.chrome-profile"))
    os.makedirs(profile, exist_ok=True)
    kwargs = dict(headless=bool(rec["playwright"].get("headless", False)),
                  viewport={"width": int(vp["width"]), "height": int(vp["height"])})
    # Optional browser channel (e.g. "msedge"/"chrome") — use a system-installed
    # Chromium instead of the bundled one. Helpful on Windows where the bundled
    # Chromium can hit side-by-side runtime issues.
    channel = rec["playwright"].get("channel")
    if channel:
        kwargs["channel"] = channel
    if video_dir:
        os.makedirs(video_dir, exist_ok=True)
        kwargs["record_video_dir"] = video_dir
        kwargs["record_video_size"] = {"width": int(vp["width"]), "height": int(vp["height"])}
    ctx = pw.chromium.launch_persistent_context(profile, **kwargs)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def _close():
        ctx.close(); pw.stop()
    return BrowserSession(page=page, records_with_playwright=True, _close=_close)
