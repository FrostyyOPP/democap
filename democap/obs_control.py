"""OBS recording control — stateless helpers plus a clean-recording session.

Each function connects, sends one command, and disconnects; OBS itself holds the
recording between calls, so start/stop can span separate invocations (handy for
the "you perform, I record" workflow).

Hard-won macOS notes baked in here (see docs/RECORDING_NOTES.md for the full story):
  * OBS recordings are BLACK for the first ~4-5 seconds (ScreenCaptureKit warm-up),
    then show real content. Always record a WARM-UP buffer and trim it off. A short
    2s test clip samples only warm-up and looks (falsely) black.
  * Verify capture by sampling brightness PAST the warm-up (ss>=WARMUP), not at ss=1.
  * Don't resize/move the captured window mid-session and don't let a fullscreen app
    occlude it — either re-triggers a sticky black-frame state on macOS.
"""

from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager

import yaml

from .recorder.encode import to_mp4

# OBS/ScreenCaptureKit warm-up: recordings are black until ~this many seconds in.
WARMUP_SECONDS = 5.5

_DEFAULT_EXPORT = {"video_codec": "libx264", "crf": 18, "preset": "medium", "pixel_format": "yuv420p"}
_CFG = os.path.join(os.path.dirname(__file__), "..", "config", "default.yaml")


def _obs_cfg():
    with open(os.path.abspath(_CFG)) as f:
        return yaml.safe_load(f)["recording"]["obs"]


def _client():
    import obsws_python as obs
    c = _obs_cfg()
    return obs.ReqClient(host=c["host"], port=c["port"], password=c["password"], timeout=5)


# ---- low-level controls -----------------------------------------------------

def start_recording(scene: str) -> str:
    cl = _client()
    cl.set_current_program_scene(scene)
    cl.start_record()
    return f"recording started on scene {scene!r}"


def set_scene(scene: str) -> str:
    _client().set_current_program_scene(scene)
    return f"scene -> {scene!r}"


def stop_recording(final_mp4: str | None = None, export: dict | None = None,
                   trim_head: float = 0.0) -> dict:
    """Stop OBS recording; optionally trim the warm-up head and export to MP4."""
    raw = getattr(_client().stop_record(), "output_path", None)
    out = {"raw": raw}
    if final_mp4 and raw and os.path.exists(raw):
        out["mp4"] = _export(raw, final_mp4, export or _DEFAULT_EXPORT, trim_head)
    return out


def _export(raw: str, final_mp4: str, export: dict, trim_head: float) -> str:
    final_mp4 = os.path.expanduser(final_mp4)
    if trim_head and trim_head > 0:
        os.makedirs(os.path.dirname(final_mp4) or ".", exist_ok=True)
        cmd = ["ffmpeg", "-y", "-ss", str(trim_head), "-i", raw,
               "-c:v", export.get("video_codec", "libx264"),
               "-crf", str(export.get("crf", 18)), "-preset", export.get("preset", "medium"),
               "-pix_fmt", export.get("pixel_format", "yuv420p"),
               "-movflags", "+faststart", final_mp4]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg trim/export failed:\n{proc.stderr[-1500:]}")
        return final_mp4
    return to_mp4(raw, final_mp4, export)


# ---- capture health check ---------------------------------------------------

def brightness(video_path: str, at_seconds: float) -> float:
    """Mean luma (0-255) of a single frame. ~0 means a black/dead capture."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at_seconds), "-i", video_path, "-frames:v", "1",
         "-vf", "scale=2:2,format=gray", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    return sum(out) / len(out) if out else 0.0


def preflight(scene: str, dur: float = 7.0, threshold: float = 5.0) -> bool:
    """Record a short throwaway clip and confirm the capture is alive (not black).

    Samples PAST the warm-up. Returns True if the scene is actually capturing.
    """
    cl = _client()
    cl.set_current_program_scene(scene)
    time.sleep(0.6)
    cl.start_record()
    time.sleep(dur)
    raw = getattr(cl.stop_record(), "output_path", None)
    time.sleep(0.6)
    ok = bool(raw) and brightness(raw, WARMUP_SECONDS) > threshold
    if raw and os.path.exists(raw):
        os.remove(raw)
    return ok


# ---- high-level clean recording --------------------------------------------

@contextmanager
def clean_recording(scene: str, out_mp4: str, warmup: float = WARMUP_SECONDS,
                    export: dict | None = None, check: bool = True):
    """Context manager that records a clean MP4 of `scene`.

    Usage:
        with clean_recording("democap_chrome", "out.mp4"):
            ... drive the demo (the warm-up has already elapsed) ...
        # on exit: stops, trims the warm-up head, exports out.mp4

    The warm-up is recorded then trimmed, so your demo actions land on real frames.
    Set check=False to skip the pre-record capture-health preflight.
    """
    if check and not preflight(scene):
        raise RuntimeError(
            f"Scene {scene!r} is capturing black. On macOS, re-toggle OBS's Screen "
            f"Recording permission (System Settings) and relaunch OBS, then retry. "
            f"See docs/RECORDING_NOTES.md."
        )
    start_recording(scene)
    time.sleep(warmup)            # record + later trim the warm-up
    try:
        yield                    # caller performs/drives the demo here
    finally:
        stop_recording(final_mp4=out_mp4, export=export or _DEFAULT_EXPORT, trim_head=warmup)
