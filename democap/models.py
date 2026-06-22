"""Structured data models shared across democap.

These pydantic models are the contract between phases: the parser/extractor
produce a DemoScript, tool detection annotates ToolStatus, and the readiness
report consumes both. Everything serializes cleanly to the JSON schema in
samples/parsed_steps.schema.json.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Action(str, Enum):
    OPEN = "open"
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    WAIT = "wait"
    VERIFY = "verify"
    SAY = "say"          # narration only, no machine action
    OTHER = "other"


class Route(str, Enum):
    BROWSER = "browser"
    DESKTOP = "desktop"
    NARRATION = "narration"
    UNDECIDED = "undecided"


class ScriptKind(str, Enum):
    """How the source document is organized."""
    NUMBERED_DEMO = "numbered_demo"   # imperative "Step 1: ..." lists
    VIDEO_SCRIPT = "video_script"     # VOICEOVER: narration + [DIRECTION] blocks


class SegmentType(str, Enum):
    """What a block is, in a video script."""
    META = "meta"              # title / header lines
    VOICEOVER = "voiceover"    # spoken narration
    DIRECTION = "direction"    # [SCREEN CAPTURE], [ZOOM], [TYPE-ALONG], ...
    PROMPT = "prompt"          # PROMPT: text the demo should type
    STEP = "step"             # imperative step (numbered-demo scripts)


class Classification(str, Enum):
    DESKTOP_REQUIRED = "desktop_required"
    BROWSER_CAPABLE = "browser_capable"
    OPTIONAL = "optional"


class Step(BaseModel):
    index: int
    raw_text: str
    action: Action = Action.OTHER
    detail: str = ""
    target_tools: list[str] = Field(default_factory=list)
    route: Route = Route.UNDECIDED
    risky: bool = False
    notes: str = ""

    # --- Video-script / demo-intent fields (unused by numbered-demo scripts) ---
    segment_type: SegmentType = SegmentType.STEP
    demo_needed: Optional[bool] = None     # None = not a candidate (meta/transition)
    confidence: float = 0.0                # 0..1 confidence in demo_needed
    classified_by: str = ""                # "heuristic" | "claude" | "rule" | "direction"
    ambiguous: bool = False                # low confidence -> good candidate for Claude pass
    reason: str = ""                       # short why, for the report


class DemoScript(BaseModel):
    title: str
    source_file: str = ""
    required_tools: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)


class Lesson(BaseModel):
    """One recordable unit of a course -> one clean MP4."""

    lesson_id: str                 # e.g. "1.2"
    title: str
    est_minutes: float = 0.0       # from the script's word-count note, if present
    required_tools: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)

    @property
    def demo_count(self) -> int:
        return sum(1 for s in self.steps if s.demo_needed is True)

    @property
    def narration_count(self) -> int:
        return sum(1 for s in self.steps if s.demo_needed is False)


class Course(BaseModel):
    title: str
    source_file: str = ""
    lessons: list[Lesson] = Field(default_factory=list)

    @property
    def required_tools(self) -> list[str]:
        seen: list[str] = []
        for lesson in self.lessons:
            for t in lesson.required_tools:
                if t not in seen:
                    seen.append(t)
        return seen


class ToolStatus(BaseModel):
    """Result of detecting one required tool on the machine."""

    key: str
    classification: Classification
    installed: bool
    detected_via: Optional[str] = None       # "app", "bundle_id", "cli", or None
    app_path: Optional[str] = None
    browser_alt_name: Optional[str] = None
    browser_alt_url: Optional[str] = None

    @property
    def blocking(self) -> bool:
        """A missing desktop-required tool with no browser alternative blocks a run."""
        return (
            not self.installed
            and self.classification == Classification.DESKTOP_REQUIRED
            and not self.browser_alt_url
        )


class ReadinessReport(BaseModel):
    script_title: str
    tools: list[ToolStatus] = Field(default_factory=list)
    recording_backend_browser: str = "playwright"
    recording_backend_desktop: str = "obs"

    @property
    def blockers(self) -> list[ToolStatus]:
        return [t for t in self.tools if t.blocking]

    @property
    def ready(self) -> bool:
        return len(self.blockers) == 0
