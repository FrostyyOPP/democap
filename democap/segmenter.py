"""Detect the script format and label each block.

Two genres are supported:
  - NUMBERED_DEMO : imperative "Step 1: Open Chrome" lists (original MVP path).
  - VIDEO_SCRIPT  : Starweaver-style scripts with `VOICEOVER:` narration and
                    bracketed `[SCREEN CAPTURE]` / `[ZOOM]` / `[TYPE-ALONG]`
                    production directions, plus optional `PROMPT:` payloads.

For video scripts there is usually NO line that says "demo here" — so we segment
the text and hand each VOICEOVER block to the demo-intent classifier, which reads
what the voice is actually saying and decides whether a screen demo is needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .docx_parser import RawBlock
from .models import ScriptKind, SegmentType

_VOICEOVER = re.compile(r"^\s*VOICE\s*OVER\s*:\s*(.*)$", re.IGNORECASE)
_VO_SHORT = re.compile(r"^\s*VO\s*:\s*(.*)$", re.IGNORECASE)
_PROMPT = re.compile(r"^\s*PROMPT\s*:\s*(.*)$", re.IGNORECASE)
# A bracketed direction like "[SCREEN CAPTURE: ...]" or "[ZOOM: highlight ...]".
_DIRECTION = re.compile(r"^\s*\[\s*([A-Z][A-Z \-/]+?)\s*[:\]]\s*(.*?)\s*\]?\s*$")


@dataclass
class Segment:
    type: SegmentType
    text: str                  # cleaned text (label stripped)
    raw_text: str              # original line
    label: str = ""            # e.g. "SCREEN CAPTURE" for directions
    hint: str = field(default="")   # nearest direction tag attached to a voiceover


def detect_kind(blocks: list[RawBlock]) -> ScriptKind:
    """Heuristic: a video script has VOICEOVER lines and/or bracketed directions."""
    vo = sum(1 for b in blocks if _VOICEOVER.match(b.text) or _VO_SHORT.match(b.text))
    directions = sum(1 for b in blocks if _DIRECTION.match(b.text))
    if vo >= 2 or (vo >= 1 and directions >= 1):
        return ScriptKind.VIDEO_SCRIPT
    return ScriptKind.NUMBERED_DEMO


def _label_block(block: RawBlock) -> Segment:
    text = block.text.strip()

    m = _VOICEOVER.match(text) or _VO_SHORT.match(text)
    if m:
        return Segment(SegmentType.VOICEOVER, m.group(1).strip(), block.text)

    m = _PROMPT.match(text)
    if m:
        return Segment(SegmentType.PROMPT, m.group(1).strip(), block.text)

    m = _DIRECTION.match(text)
    if m:
        return Segment(SegmentType.DIRECTION, m.group(2).strip(), block.text, label=m.group(1).strip())

    # Headers / titles / stray lines.
    return Segment(SegmentType.META, text, block.text)


def segment_video_script(blocks: list[RawBlock]) -> list[Segment]:
    """Label every block, then attach each voiceover's nearest following direction
    as a `hint` (directions usually annotate the narration around them)."""
    segments = [_label_block(b) for b in blocks]

    # Attach a direction hint to the preceding voiceover when adjacent.
    for i, seg in enumerate(segments):
        if seg.type == SegmentType.DIRECTION:
            # look back to the closest voiceover within 1-2 lines
            for j in range(i - 1, max(-1, i - 3), -1):
                if segments[j].type == SegmentType.VOICEOVER and not segments[j].hint:
                    segments[j].hint = seg.label
                    break
    return segments
