"""FFmpeg encode/remux helpers — turn raw captures into the final clean MP4."""

from __future__ import annotations

import os
import shutil
import subprocess


def to_mp4(src: str, dst: str, export: dict) -> str:
    """Transcode any capture (webm/mov/…) to a course-friendly MP4.

    export keys: video_codec, crf, preset, pixel_format.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH.")
    dst = os.path.expanduser(dst)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", os.path.expanduser(src),
        "-c:v", export.get("video_codec", "libx264"),
        "-crf", str(export.get("crf", 18)),
        "-preset", export.get("preset", "medium"),
        "-pix_fmt", export.get("pixel_format", "yuv420p"),
        "-movflags", "+faststart",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-1500:]}")
    return dst
