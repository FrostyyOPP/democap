"""Desktop executor (Phase 4) — DESKTOP-routed steps (Excel / Copilot) on macOS.

Two kinds of desktop action, by reliability:
  - App activation + keyboard input -> done locally here via AppleScript (osascript),
    no extra dependencies. This covers launching Excel and TYPING Copilot prompts.
  - Precise element clicks (the Copilot icon, a specific ribbon button) -> these are
    best handled by Claude Code computer-use, which can see the screen and click
    accurately. democap exposes the step; the computer-use driver performs it.

Recording is handled OUTSIDE this module by ObsRecorder (window capture of Excel),
so nothing here needs to think about capture — and the Claude overlay never lands
in the recorded window.

TODO(windows): replace osascript with pywinauto / SendKeys; element clicks via UIA.
"""

from __future__ import annotations

import subprocess

from ..models import Action, Step


def _osascript(script: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        return p.returncode == 0, (p.stderr or p.stdout).strip()
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return False, str(exc)


def activate_app(app_name: str) -> tuple[bool, str]:
    """Bring an app to the front (launching it if needed)."""
    return _osascript(f'tell application "{app_name}" to activate')


def type_text(text: str) -> tuple[bool, str]:
    """Type into the frontmost app via System Events keystroke.
    Requires Accessibility permission for the controlling process (one-time)."""
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    return _osascript(f'tell application "System Events" to keystroke "{safe}"')


def press_key(key_code: int) -> tuple[bool, str]:
    return _osascript(f'tell application "System Events" to key code {key_code}')


# Steps a local backend can perform unattended vs. those needing computer-use.
_LOCAL = {Action.OPEN, Action.TYPE, Action.WAIT}


def execute_step(step: Step, app_hint: str = "Microsoft Excel") -> dict:
    """Perform one desktop step. Element clicks are flagged for the computer-use
    driver rather than guessed at blindly."""
    result = {"index": step.index, "action": step.action.value, "ok": True,
              "detail": step.detail, "note": "", "needs_computer_use": False}

    if step.action == Action.OPEN:
        ok, msg = activate_app(app_hint)
        result.update(ok=ok, note=msg or f"activated {app_hint}")
    elif step.action == Action.TYPE and step.detail:
        ok, msg = type_text(step.detail)
        result.update(ok=ok, note=msg or "typed")
    elif step.action == Action.WAIT:
        result["note"] = "dwell (handled by caller pacing)"
    elif step.action == Action.CLICK:
        # Locating a specific control reliably needs vision -> defer to computer-use.
        result.update(needs_computer_use=True,
                      note=f"click target '{step.detail or step.raw_text[:40]}' -> computer-use")
    else:
        result["note"] = f"no local desktop action for {step.action.value}; review"
    return result
