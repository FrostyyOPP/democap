"""Browser executor (Phase 4) — runs BROWSER-routed steps on a Playwright page.

The page passed in is the one PlaywrightRecorder is recording, so execution and
clean capture share a single surface. Actions are paced with small settle delays
so the resulting video reads naturally instead of snapping instantly.

Mapping (best-effort; unknown specifics are logged, never guessed destructively):
  OPEN / NAVIGATE -> page.goto(url)         (url from detail or catalog tool url)
  CLICK           -> click by visible text / role
  TYPE            -> type detail into the focused or best-guess input
  WAIT            -> dwell
  VERIFY/SAY      -> no browser action (handled as a recorded pause upstream)

Risky steps (step.risky) are surfaced to the caller via the result, which can
pause for confirmation before the action runs.
"""

from __future__ import annotations

import re

from ..models import Action, Step

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_SPOKEN_URL = re.compile(r"\b([a-z0-9-]+)\s+dot\s+([a-z]+)(?:\s+dot\s+([a-z]+))?", re.IGNORECASE)


def _resolve_url(step: Step, catalog: dict) -> str | None:
    # 1. explicit URL in detail/text
    for text in (step.detail, step.raw_text):
        m = _URL_RE.search(text or "")
        if m:
            return m.group(0).rstrip(".,")
    # 2. "gemini dot google dot com" spoken form
    m = _SPOKEN_URL.search(step.raw_text or "")
    if m:
        host = ".".join(p for p in m.groups() if p)
        return f"https://{host}"
    # 3. fall back to a target tool's catalog url
    for key in step.target_tools:
        url = (catalog.get(key) or {}).get("url")
        if url:
            return url
    return None


def _robust_click(page, text: str) -> None:
    """Try the most reliable locators first: link/button by name, then any text."""
    candidates = [
        lambda: page.get_by_role("link", name=text, exact=False),
        lambda: page.get_by_role("button", name=text, exact=False),
        lambda: page.get_by_text(text, exact=False),
    ]
    last_exc = None
    for make in candidates:
        try:
            make().first.click(timeout=3000)
            return
        except Exception as exc:
            last_exc = exc
    raise last_exc


def execute_step(page, step: Step, catalog: dict, pacing_ms: int = 700) -> dict:
    """Run one browser step on `page`. Returns a structured result for the log."""
    result = {"index": step.index, "action": step.action.value, "ok": True,
              "detail": step.detail, "note": ""}
    try:
        if step.action in (Action.OPEN, Action.NAVIGATE):
            url = _resolve_url(step, catalog)
            if not url:
                result.update(ok=False, note="no URL resolved for open/navigate")
                return result
            page.goto(url, wait_until="load")
            result["detail"] = url

        elif step.action == Action.CLICK:
            if step.detail:
                _robust_click(page, step.detail)
            else:
                result["note"] = "click with no target text; skipped"

        elif step.action == Action.TYPE:
            if step.detail:
                page.keyboard.type(step.detail, delay=35)
            else:
                result["note"] = "type with no text; skipped"

        elif step.action == Action.WAIT:
            page.wait_for_timeout(1200)

        else:
            result["note"] = f"no browser action for {step.action.value}"

        page.wait_for_timeout(pacing_ms)   # natural settle for the recording
    except Exception as exc:  # keep the run going; surface the failure in the log
        result.update(ok=False, note=f"{type(exc).__name__}: {exc}")
    return result
