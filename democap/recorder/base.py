"""Recorder interface + clean-capture settings preparation.

CLEAN-CAPTURE PRINCIPLE (the whole point of this project):
The Claude control overlay / orange border is a separate floating window drawn
ON TOP of the screen. We avoid it by never recording the full display:
  - browser steps  -> Playwright records the page viewport directly (no OS overlay
                      is ever in that stream).
  - desktop steps  -> OBS *Window Capture* pulls the target app's own window from
                      the compositor, which excludes other apps' overlays/borders.
  - fallback       -> FFmpeg crops a fixed region; least safe, used only if OBS is
                      unavailable, and refused when forbid_fullscreen_capture is set.

Phase 3 only PREPARES and validates these settings. The start/stop/export methods
are implemented in Phase 5 (playwright_rec / obs_rec / ffmpeg_rec).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CaptureSettings:
    backend: str                 # "playwright" | "obs" | "ffmpeg"
    capture_type: str            # "viewport" | "window" | "crop"  (never "display")
    fps: int
    width: int
    height: int
    output_path: str
    extra: dict                  # backend-specific knobs


class Recorder(ABC):
    """Lifecycle: prepare() -> start() -> [actions happen] -> stop() -> export()."""

    def __init__(self, settings: CaptureSettings):
        self.settings = settings

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def export(self, final_mp4_path: str) -> str:
        """Produce the final clean MP4. Returns its path."""
        ...


def prepare_settings(config: dict, route: str, output_path: str) -> CaptureSettings:
    """Translate config + step route into a concrete, clean CaptureSettings.

    Enforces the no-fullscreen rule and picks the per-route backend.
    """
    rec = config["recording"]
    w, h = (int(x) for x in str(rec["resolution"]).lower().split("x"))
    fps = int(rec["fps"])

    if route == "browser":
        vp = rec["playwright"]["viewport"]
        return CaptureSettings(
            backend="playwright", capture_type="viewport", fps=fps,
            width=int(vp["width"]), height=int(vp["height"]),
            output_path=output_path, extra=dict(rec["playwright"]),
        )

    if route == "desktop":
        obs = rec["obs"]
        if obs.get("capture_type") == "display" and rec.get("forbid_fullscreen_capture", True):
            raise ValueError("Refusing display capture: would include Claude overlay. Use window capture.")
        return CaptureSettings(
            backend="obs", capture_type=obs.get("capture_type", "window"), fps=fps,
            width=w, height=h, output_path=output_path, extra=dict(obs),
        )

    # Fallback / narration with visuals -> ffmpeg crop (never full display).
    if rec.get("forbid_fullscreen_capture", True):
        ff = rec["ffmpeg"]["crop"]
        return CaptureSettings(
            backend="ffmpeg", capture_type="crop", fps=fps,
            width=int(ff["width"]), height=int(ff["height"]),
            output_path=output_path, extra=dict(rec["ffmpeg"]),
        )
    raise ValueError(f"No clean capture backend available for route={route!r}")
