"""Decide, per voiceover segment, whether a screen demo is needed.

This is the layer the user asked for: the script does NOT label demos, so we read
what the voice is actually talking about and infer it.

Design: a small pluggable interface so the engine can change without touching
callers. Today the heuristic backend is active. When ANTHROPIC_API_KEY is present
the hybrid backend uses Claude to resolve only the segments the heuristic is unsure
about (cheapest accurate option). With no key, everything degrades to heuristic.

    classifier = get_classifier(config)        # picks backend from env/config
    verdict = classifier.classify(text, hint)  # -> DemoVerdict
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# ---- Heuristic signal vocabulary -------------------------------------------------

# Imperative UI verbs that strongly imply something happens on screen.
_UI_VERBS = re.compile(
    r"\b(click|tap|press|type|enter|select|choose|open|launch|go to|navigate|"
    r"visit|sign in|log in|drag|drop|scroll|hover|right[- ]?click|double[- ]?click|"
    r"copy|paste|save|download|upload|highlight|find the|look at)\b",
    re.IGNORECASE,
)
# UI nouns — the things you act on.
_UI_NOUNS = re.compile(
    r"\b(tab|button|icon|panel|pane|ribbon|menu|toolbar|cell|column|row|sheet|"
    r"dialog|field|box|address bar|browser tab|window|sidebar|dropdown|checkbox|"
    r"home tab|formula bar)\b",
    re.IGNORECASE,
)
# "on screen" deixis — the voice is pointing at the screen.
_SCREEN_DEIXIS = re.compile(
    r"\b(on (the|your) screen|at the top of the screen|on the right|on the left|"
    r"in the panel|in the pane|here is|notice the|you will see|you can see)\b",
    re.IGNORECASE,
)
# Narration / story / transition language — usually NO demo.
_NARRATION = re.compile(
    r"\b(imagine|it is (early|nine|morning|late)|a few weeks|by the end|"
    r"in the next (\w+ )?(minute|minutes|seconds)|you will learn|let us recap|"
    r"to recap|in this (lesson|video|module)|welcome|think about|remember that|"
    r"next,? we|coming up|up next|do not worry|story)\b",
    re.IGNORECASE,
)
# Directions that, when attached as a hint, are decisive about recording.
_DEMO_DIRECTIONS = {"SCREEN CAPTURE", "TYPE-ALONG", "TYPE ALONG", "ZOOM", "DEMO", "SCREENCAST"}
_NONDEMO_DIRECTIONS = {"UP NEXT SLIDE", "CALLOUT BANNER", "SLIDE", "TITLE CARD", "LOWER THIRD"}


@dataclass
class DemoVerdict:
    demo_needed: bool
    confidence: float          # 0..1
    classified_by: str         # "heuristic" | "claude" | "direction"
    reason: str
    ambiguous: bool = False


class DemoIntentClassifier:
    def classify(self, text: str, hint: str = "") -> DemoVerdict:  # pragma: no cover
        raise NotImplementedError


# ---- Heuristic backend (active now) ---------------------------------------------

class HeuristicClassifier(DemoIntentClassifier):
    LOW, HIGH = 0.45, 0.7      # confidence band edges; inside = ambiguous

    def classify(self, text: str, hint: str = "") -> DemoVerdict:
        # A decisive bracketed direction overrides text analysis.
        h = (hint or "").upper().strip()
        if h in _DEMO_DIRECTIONS:
            return DemoVerdict(True, 0.95, "direction", f"[{hint}] direction present")
        if h in _NONDEMO_DIRECTIONS:
            return DemoVerdict(False, 0.9, "direction", f"[{hint}] is a slide/overlay, not a demo")

        verbs = len(_UI_VERBS.findall(text))
        nouns = len(_UI_NOUNS.findall(text))
        deixis = len(_SCREEN_DEIXIS.findall(text))
        narration = len(_NARRATION.findall(text))

        # Weighted score in favor of demo; narration pulls it down.
        score = 0.0
        score += min(verbs, 3) * 0.22
        score += min(nouns, 3) * 0.18
        score += min(deixis, 2) * 0.15
        score -= min(narration, 3) * 0.25
        confidence = max(0.0, min(1.0, 0.5 + score))

        demo = confidence >= 0.5
        ambiguous = self.LOW <= confidence <= self.HIGH
        bits = []
        if verbs: bits.append(f"{verbs} UI verb(s)")
        if nouns: bits.append(f"{nouns} UI noun(s)")
        if deixis: bits.append("screen reference")
        if narration: bits.append(f"{narration} narration cue(s)")
        reason = ", ".join(bits) or "no strong signal"
        return DemoVerdict(demo, round(confidence, 2), "heuristic", reason, ambiguous)


# ---- Claude backend (drops in when a key exists) --------------------------------

_CLAUDE_SYSTEM = (
    "You classify one line of a video-course VOICEOVER. Decide if it narrates an "
    "ON-SCREEN action that must be screen-recorded as a demo (clicking, typing, "
    "navigating, showing an app/website), versus pure narration/story/transition "
    "shown over a slide. Reply with strict JSON: "
    '{\"demo_needed\": bool, \"confidence\": 0..1, \"reason\": \"short\"}.'
)


class ClaudeClassifier(DemoIntentClassifier):
    """Uses the Anthropic API. Only constructed when a key is configured.

    Implementation note (kept minimal on purpose): the call is wired so that as
    soon as `anthropic` + a key are present, it works. Until then get_classifier()
    won't select it, so the heuristic path is what actually runs.
    """

    def __init__(self, model: str = "claude-opus-4-8"):
        self.model = model
        self._fallback = HeuristicClassifier()
        try:
            import anthropic  # noqa: F401
            self._client = anthropic.Anthropic()
            self._ready = True
        except Exception:
            self._ready = False

    def classify(self, text: str, hint: str = "") -> DemoVerdict:
        if not self._ready:
            return self._fallback.classify(text, hint)
        import json as _json
        prompt = text if not hint else f"{text}\n\n(production hint: [{hint}])"
        try:
            msg = self._client.messages.create(
                model=self.model, max_tokens=200, system=_CLAUDE_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            data = _json.loads(msg.content[0].text)
            return DemoVerdict(
                bool(data["demo_needed"]), float(data.get("confidence", 0.8)),
                "claude", data.get("reason", ""),
            )
        except Exception:
            return self._fallback.classify(text, hint)


# ---- Hybrid backend: heuristic first, Claude only for ambiguous -----------------

class HybridClassifier(DemoIntentClassifier):
    def __init__(self, model: str = "claude-opus-4-8"):
        self.heuristic = HeuristicClassifier()
        self.claude = ClaudeClassifier(model)

    def classify(self, text: str, hint: str = "") -> DemoVerdict:
        verdict = self.heuristic.classify(text, hint)
        if verdict.ambiguous and getattr(self.claude, "_ready", False):
            return self.claude.classify(text, hint)
        return verdict


def get_classifier(config: dict | None = None) -> DemoIntentClassifier:
    """Pick a backend. Hybrid when a key is available; heuristic otherwise."""
    cfg = (config or {}).get("classifier", {}) if config else {}
    mode = cfg.get("mode", "auto")            # auto | heuristic | claude | hybrid
    model = cfg.get("model", "claude-opus-4-8")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if mode == "heuristic":
        return HeuristicClassifier()
    if mode == "claude":
        return ClaudeClassifier(model)
    if mode == "hybrid":
        return HybridClassifier(model)
    # auto: hybrid if a key exists, else heuristic-only.
    return HybridClassifier(model) if has_key else HeuristicClassifier()
