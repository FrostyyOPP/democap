"""Browser recorder — Playwright native context video (the cleanest path).

The recorded stream is the browser's own page viewport, rendered by Chromium —
it is NOT a screen grab, so no OS overlay, orange border, or cursor chrome from
other apps can ever appear in it. This is why browser steps are recorded here.

Lifecycle:
    rec = PlaywrightRecorder(settings)
    rec.start()                 # launches browser, opens rec.page
    # ... executor drives rec.page (goto/click/type) ...
    rec.stop()                  # closes context -> flushes the .webm
    rec.export("final.mp4")     # ffmpeg webm -> clean mp4
"""

from __future__ import annotations

import os

from .base import Recorder
from .encode import to_mp4


class PlaywrightRecorder(Recorder):
    def __init__(self, settings, export_cfg: dict | None = None):
        super().__init__(settings)
        self.export_cfg = export_cfg or {}
        self.page = None
        self._video_dir = os.path.dirname(os.path.expanduser(settings.output_path)) or "."
        self._raw_video = None

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        os.makedirs(self._video_dir, exist_ok=True)
        e = self.settings.extra
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=bool(e.get("headless", False)))
        self._ctx = self._browser.new_context(
            viewport={"width": self.settings.width, "height": self.settings.height},
            record_video_dir=self._video_dir,
            record_video_size={"width": self.settings.width, "height": self.settings.height},
        )
        self.page = self._ctx.new_page()

    def stop(self) -> None:
        if self.page is not None:
            self._raw_video = self.page.video.path()
        self._ctx.close()          # finalizes the video file
        self._browser.close()
        self._pw.stop()

    def export(self, final_mp4_path: str) -> str:
        if not self._raw_video or not os.path.exists(self._raw_video):
            raise RuntimeError("No recorded video found; did start()/stop() run?")
        return to_mp4(self._raw_video, final_mp4_path, self.export_cfg)
