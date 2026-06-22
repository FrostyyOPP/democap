"""Fallback recorder — FFmpeg avfoundation crop region.

Phase 5 implementation. Used only when OBS is unavailable. Captures a fixed
screen rectangle, so the region MUST be positioned over the target app and away
from any Claude overlay. Full-display capture is intentionally never offered.

Sketch:
    ffmpeg -f avfoundation -framerate {fps} -i "Capture screen 0:none" \
           -vf "crop={w}:{h}:{x}:{y}" -c:v libx264 -crf 18 -pix_fmt yuv420p out.mp4

TODO(windows): replace avfoundation with gdigrab/ddagrab region capture.
"""

from .base import Recorder


class FfmpegRecorder(Recorder):
    def start(self) -> None:
        raise NotImplementedError("Phase 5: implement ffmpeg avfoundation crop capture.")

    def stop(self) -> None:
        raise NotImplementedError("Phase 5")

    def export(self, final_mp4_path: str) -> str:
        raise NotImplementedError("Phase 5")
