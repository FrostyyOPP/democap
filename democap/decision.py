"""Browser-vs-desktop routing for each step.

Policy (honoring config.routing.prefer_browser):
  - Steps with no tool and a narration verb (say/verify-only) -> NARRATION.
  - A step whose tools are all browser_capable -> BROWSER (when prefer_browser).
  - A step touching any desktop_required tool -> DESKTOP.
  - Mixed/uncertain -> UNDECIDED (surfaced to you rather than guessed).

This only *plans* the route; execution (Phase 4) consumes it. Routing also drives
which recorder backend is used per step: browser->playwright, desktop->obs.
"""

from __future__ import annotations

from .models import Action, Classification, DemoScript, Route


def route_steps(script: DemoScript, catalog: dict, prefer_browser: bool = True) -> DemoScript:
    for step in script.steps:
        step.route = _route_one(step, catalog, prefer_browser)
    return script


def _route_one(step, catalog: dict, prefer_browser: bool) -> Route:
    # Video-script segments carry an explicit demo-intent verdict; honor it.
    if step.demo_needed is False:
        return Route.NARRATION

    # Spoken narration is never executed/recorded as an action, regardless of
    # any tool names that happen to appear in the sentence.
    if step.action == Action.SAY and step.demo_needed is not True:
        return Route.NARRATION

    if not step.target_tools:
        # A demo IS needed but we couldn't identify the app -> flag for review,
        # don't silently downgrade to narration.
        if step.demo_needed is True:
            return Route.UNDECIDED
        if step.action in (Action.VERIFY, Action.WAIT):
            return Route.NARRATION
        return Route.UNDECIDED

    classes = []
    for key in step.target_tools:
        spec = catalog.get(key, {})
        classes.append(Classification(spec.get("classification", "optional")))

    has_desktop_required = Classification.DESKTOP_REQUIRED in classes
    all_browser = all(c == Classification.BROWSER_CAPABLE for c in classes)

    if has_desktop_required:
        return Route.DESKTOP
    if all_browser and prefer_browser:
        return Route.BROWSER
    if all_browser:
        return Route.DESKTOP  # browser-capable but user opted out of browser-first
    return Route.UNDECIDED
