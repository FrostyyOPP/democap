"""macOS platform helpers. Detection lives in tool_detector; this holds
mac-specific launch/window utilities used by executors and recorders."""

from __future__ import annotations

import subprocess


def open_app(app_name: str) -> None:
    """Bring/launch a native app to the foreground (`open -a`)."""
    subprocess.run(["open", "-a", app_name], check=False)


def open_url(url: str, browser_app: str | None = None) -> None:
    """Open a URL, optionally in a specific browser app."""
    cmd = ["open"]
    if browser_app:
        cmd += ["-a", browser_app]
    cmd.append(url)
    subprocess.run(cmd, check=False)
