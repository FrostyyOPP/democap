"""Desktop recorder — OBS Window Capture via obs-websocket (clean for native apps).

Used for Excel/Copilot steps. OBS macOS Window Capture (ScreenCaptureKit) records
the target app window's own surface, so the Claude control overlay / orange border
(drawn by another app on top of the screen) is NOT in the recording.

Design choice for reliability: rather than create capture sources programmatically
(brittle across OBS versions), democap switches to a clean scene you set up ONCE in
the OBS UI, then automates record start/stop. See README "OBS scene setup".

Lifecycle:
    rec = ObsRecorder(settings, export_cfg)
    rec.start()    # connect, select clean scene, start recording
    # ... computer-use drives Excel/Copilot ...
    rec.stop()     # stop recording, capture OBS's output file path
    rec.export("final.mp4")   # remux/transcode to the course MP4
"""

from __future__ import annotations

import os

from .base import Recorder
from .encode import to_mp4


class ObsRecorder(Recorder):
    def __init__(self, settings, export_cfg: dict | None = None):
        super().__init__(settings)
        self.export_cfg = export_cfg or {}
        self._raw_path = None

    def _client(self):
        import obsws_python as obs
        e = self.settings.extra
        return obs.ReqClient(host=e.get("host", "localhost"), port=int(e.get("port", 4455)),
                             password=e.get("password", ""), timeout=5)

    def start(self) -> None:
        e = self.settings.extra
        self.cl = self._client()
        scene = e.get("scene")
        if scene:
            try:
                self.cl.set_current_program_scene(scene)
            except Exception as exc:
                raise RuntimeError(
                    f"OBS scene {scene!r} not found. Create a Window-Capture scene named "
                    f"{scene!r} bound to the target app (see README)."
                ) from exc
        self.cl.start_record()

    def stop(self) -> None:
        resp = self.cl.stop_record()
        # obsws-python exposes the written file as output_path on the response.
        self._raw_path = getattr(resp, "output_path", None)

    def export(self, final_mp4_path: str) -> str:
        if not self._raw_path or not os.path.exists(self._raw_path):
            raise RuntimeError(
                "OBS did not report a recording file. Check OBS recording output settings."
            )
        # If OBS already wrote .mp4 we still normalize via ffmpeg for codec/pixfmt parity.
        return to_mp4(self._raw_path, final_mp4_path, self.export_cfg)
