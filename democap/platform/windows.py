"""Windows platform layer — TODO (future port).

TODO(windows):
  - tool detection: registry uninstall keys, `where`, Start-Menu .lnk scan.
  - launch: os.startfile / `start`.
  - desktop recording: OBS window capture works cross-platform via obs-websocket;
    ffmpeg fallback uses gdigrab/ddagrab instead of avfoundation.
  - desktop execution: pywinauto / UI Automation instead of computer-use macOS.
Select this module from a platform factory based on platform.system() == 'Windows'.
"""

from __future__ import annotations


def open_app(app_name: str) -> None:
    raise NotImplementedError("TODO(windows): launch native app.")


def open_url(url: str, browser_app: str | None = None) -> None:
    raise NotImplementedError("TODO(windows): open URL in browser.")
