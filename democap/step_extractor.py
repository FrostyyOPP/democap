"""Phase 2 of parsing: raw blocks -> ordered, structured Steps + required tools.

Heuristic, not AI: we normalize each script line into an Action verb, pull out
the obvious detail (URL / quoted text), and tag which catalog tools it touches.
The script is the source of truth; this layer just makes it machine-actionable.
Anything ambiguous stays Action.OTHER / Route.UNDECIDED so later phases (or you)
can resolve it rather than the system guessing wrong.
"""

from __future__ import annotations

import re

from .demo_intent import DemoIntentClassifier, HeuristicClassifier
from .docx_parser import RawBlock
from .models import Action, DemoScript, Route, ScriptKind, SegmentType, Step
from .segmenter import detect_kind, segment_video_script

# Leading list markers we strip: "1.", "1)", "-", "*", "Step 3:", etc.
_LIST_PREFIX = re.compile(r"^\s*(step\s*\d+\s*[:.)-]?|\d+[.)]|[-*•])\s*", re.IGNORECASE)
_URL = re.compile(r"https?://\S+|\b\w[\w.-]*\.(?:com|org|net|io|dev|app|co)\b\S*", re.IGNORECASE)
_QUOTED = re.compile(r'["“”\']([^"“”\']{1,200})["“”\']')

# Verb -> Action. First match in the (lowercased) line wins.
_VERB_MAP: list[tuple[re.Pattern, Action]] = [
    (re.compile(r"\b(open|launch|start)\b"), Action.OPEN),
    (re.compile(r"\b(go to|navigate|visit|browse to)\b"), Action.NAVIGATE),
    (re.compile(r"\b(click|press|tap|select the button|choose)\b"), Action.CLICK),
    (re.compile(r"\b(type|enter|input|fill in|write)\b"), Action.TYPE),
    (re.compile(r"\b(scroll)\b"), Action.SCROLL),
    (re.compile(r"\b(wait|pause)\b"), Action.WAIT),
    (re.compile(r"\b(verify|confirm|check that|ensure|notice|observe)\b"), Action.VERIFY),
    (re.compile(r"\b(say|explain|mention|note that|narrat)\b"), Action.SAY),
]

# Words that flag a step as risky -> needs confirmation before executing.
_RISKY = re.compile(
    r"\b(delete|remove|drop|format|wipe|uninstall|overwrite|purchase|buy|pay|"
    r"send|submit payment|sign in|log in|password|credential)\b",
    re.IGNORECASE,
)


def _classify_action(line: str) -> Action:
    low = line.lower()
    for pattern, action in _VERB_MAP:
        if pattern.search(low):
            return action
    return Action.OTHER


def _extract_detail(line: str, action: Action) -> str:
    url = _URL.search(line)
    if action in (Action.OPEN, Action.NAVIGATE) and url:
        return url.group(0)
    quoted = _QUOTED.search(line)
    if quoted:
        return quoted.group(1)
    if url:
        return url.group(0)
    return ""


def _match_tools(line: str, catalog: dict) -> list[str]:
    low = line.lower()
    hits: list[str] = []
    for key, spec in catalog.items():
        for alias in spec.get("aliases", []):
            if alias.lower() in low:
                hits.append(key)
                break
    return hits


def extract_steps(
    title: str,
    blocks: list[RawBlock],
    source_file: str,
    catalog: dict,
    classifier: DemoIntentClassifier | None = None,
) -> DemoScript:
    """Build a DemoScript from raw blocks. Dispatches on detected script genre."""
    kind = detect_kind(blocks)
    if kind == ScriptKind.VIDEO_SCRIPT:
        return _extract_video_script(
            title, blocks, source_file, catalog, classifier or HeuristicClassifier()
        )
    return _extract_numbered(title, blocks, source_file, catalog)


def _extract_numbered(
    title: str,
    blocks: list[RawBlock],
    source_file: str,
    catalog: dict,
) -> DemoScript:
    """Imperative 'Step 1: ...' lists (original MVP path)."""
    steps: list[Step] = []
    required: list[str] = []
    idx = 0

    for block in blocks:
        # Skip the heading we already used as title.
        if block.is_heading and block.text == title:
            continue

        clean = _LIST_PREFIX.sub("", block.text).strip()
        if not clean:
            continue

        idx += 1
        action = _classify_action(clean)
        tools = _match_tools(clean, catalog)
        for t in tools:
            if t not in required:
                required.append(t)

        steps.append(
            Step(
                index=idx,
                raw_text=block.text,
                action=action,
                detail=_extract_detail(clean, action),
                target_tools=tools,
                risky=bool(_RISKY.search(clean)),
            )
        )

    return DemoScript(
        title=title,
        source_file=source_file,
        required_tools=required,
        steps=steps,
    )


def _extract_video_script(
    title: str,
    blocks: list[RawBlock],
    source_file: str,
    catalog: dict,
    classifier: DemoIntentClassifier,
) -> DemoScript:
    """VOICEOVER + [DIRECTION] scripts. The classifier decides, per voiceover,
    whether a screen demo is needed; PROMPT blocks carry text to type; non-demo
    directions (slides, banners) and pure narration become NARRATION steps."""
    segments = segment_video_script(blocks)
    steps: list[Step] = []
    required: list[str] = []
    idx = 0
    pending_prompt = ""
    active_tools: list[str] = []   # sticky app context across segments

    for seg in segments:
        if seg.type == SegmentType.META:
            continue

        # Carry a PROMPT payload onto the next demo step as its type-detail.
        if seg.type == SegmentType.PROMPT:
            pending_prompt = seg.text
            continue

        idx += 1
        tools = _match_tools(seg.text + " " + seg.hint, catalog)
        inherited = False
        if tools:
            active_tools = tools                 # context switches to this app
        for t in tools:
            if t not in required:
                required.append(t)

        if seg.type == SegmentType.VOICEOVER:
            verdict = classifier.classify(seg.text, seg.hint)
            if verdict.demo_needed:
                action = _classify_action(seg.text)
                if action == Action.SAY:
                    action = Action.OTHER
                route = Route.UNDECIDED  # decided later by decision.route_steps
                # Demo step with no app named here -> inherit the active app.
                if not tools and active_tools:
                    tools = list(active_tools)
                    inherited = True
            else:
                action = Action.SAY
                route = Route.NARRATION
            detail = pending_prompt or _extract_detail(seg.text, action)
            pending_prompt = ""
            note = verdict.reason + (" (app inherited from context)" if inherited else "")
            steps.append(Step(
                index=idx, raw_text=seg.raw_text, action=action, detail=detail,
                target_tools=tools, route=route, risky=bool(_RISKY.search(seg.text)),
                segment_type=SegmentType.VOICEOVER, demo_needed=verdict.demo_needed,
                confidence=verdict.confidence, classified_by=verdict.classified_by,
                ambiguous=verdict.ambiguous, reason=note,
            ))
        else:  # DIRECTION block on its own line
            verdict = classifier.classify(seg.text, seg.label)
            steps.append(Step(
                index=idx, raw_text=seg.raw_text, action=Action.OTHER,
                detail=seg.text, target_tools=tools,
                route=Route.UNDECIDED if verdict.demo_needed else Route.NARRATION,
                segment_type=SegmentType.DIRECTION, demo_needed=verdict.demo_needed,
                confidence=verdict.confidence, classified_by=verdict.classified_by,
                reason=f"[{seg.label}] {verdict.reason}",
            ))

    return DemoScript(
        title=title, source_file=source_file, required_tools=required, steps=steps,
    )
