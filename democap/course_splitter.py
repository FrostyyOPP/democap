"""Split a combined course .docx into individual lessons.

A "complete course" script concatenates many lessons into one document. Each
lesson should become its own clean MP4, so we must cut the block stream into
lessons before extraction.

Boundary markers observed in these scripts (all driven by the document, not
hard-coded positions):
  - `Prompt Ledger — lesson X.Y`  -> closes lesson X.Y (carries its id)
  - `Total spoken words: ≈NNN (≈M min ...)` -> that lesson's duration estimate
  - A title table at the end: `X.Y — Lesson Title` -> id -> title map
The ledger / word-count lines are metadata and are dropped from the steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .docx_parser import RawBlock

_LEDGER = re.compile(r"^\s*Prompt Ledger\s*[—\-]\s*lesson\s*([0-9]+\.[0-9]+)", re.IGNORECASE)
_WORDCNT = re.compile(r"Total spoken words.*?≈?\s*([0-9.]+)\s*min", re.IGNORECASE)
_TITLE = re.compile(r"^\s*([0-9]+\.[0-9]+)\s*[—\-]\s*(.+?)\s*$")


@dataclass
class LessonBlocks:
    lesson_id: str
    title: str = ""
    est_minutes: float = 0.0
    blocks: list[RawBlock] = field(default_factory=list)


def _title_map(blocks: list[RawBlock]) -> dict[str, str]:
    """Build id -> title from the end-of-doc title table.
    Only accept short title lines (the appendix), not narration that happens to
    start with a number."""
    titles: dict[str, str] = {}
    for b in blocks:
        m = _TITLE.match(b.text.strip())
        if m and len(b.text.strip()) < 80 and "VO:" not in b.text:
            titles.setdefault(m.group(1), m.group(2))
    return titles


def split_course(blocks: list[RawBlock]) -> list[LessonBlocks]:
    """Cut the block stream into lessons using the ledger markers."""
    titles = _title_map(blocks)
    lessons: list[LessonBlocks] = []
    current: list[RawBlock] = []

    for b in blocks:
        ledger = _LEDGER.match(b.text)
        if ledger:
            lesson_id = ledger.group(1)
            lessons.append(
                LessonBlocks(
                    lesson_id=lesson_id,
                    title=titles.get(lesson_id, f"Lesson {lesson_id}"),
                    blocks=current,
                )
            )
            current = []
            continue

        wc = _WORDCNT.search(b.text)
        if wc and lessons:
            try:
                lessons[-1].est_minutes = float(wc.group(1))
            except ValueError:
                pass
            continue

        # Skip the trailing title-table appendix (after the last ledger).
        if _TITLE.match(b.text.strip()) and len(b.text.strip()) < 80 and "VO:" not in b.text:
            continue

        current.append(b)

    # Trailing content with no closing ledger is a lesson ONLY if it actually
    # contains spoken narration. Otherwise it's an appendix (checklists, prompt
    # tables, TOC) and must not be mistaken for a recordable lesson.
    if _has_voiceover(current):
        lessons.append(LessonBlocks(lesson_id="end", title="Course Wrap-Up", blocks=current))

    return lessons


def _has_voiceover(blocks: list[RawBlock]) -> bool:
    return any(re.match(r"^\s*(VOICE\s*OVER|VO)\s*:", b.text, re.IGNORECASE) for b in blocks)
