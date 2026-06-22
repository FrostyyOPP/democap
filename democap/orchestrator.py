"""Run orchestration. Phases 1-3 are wired here; 4-5 are placeholders.

analyze() is the Phase 3 MVP entry point: docx -> steps -> tools -> routing ->
readiness report (+ prepared clean-capture settings preview). It performs no GUI
actions and records nothing, so it is safe to run anytime.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import config as cfg
from .course_splitter import split_course
from .decision import route_steps
from .demo_intent import get_classifier
from .docx_parser import parse_docx
from .models import Course, DemoScript, Lesson, ReadinessReport
from .readiness import build_report
from .recorder.base import prepare_settings
from .step_extractor import extract_steps
from .tool_detector import detect_tools


@dataclass
class AnalysisResult:
    script: DemoScript
    report: ReadinessReport
    capture_preview: dict          # route -> human-readable backend summary


def analyze(docx_path: str, config_path: str | None = None, catalog_path: str | None = None) -> AnalysisResult:
    config = cfg.load_config(config_path)
    catalog = cfg.load_catalog(catalog_path)

    # Phase 1+2: parse & extract structured steps. For video scripts the
    # classifier reads each voiceover and decides whether a demo is needed.
    classifier = get_classifier(config)
    title, blocks = parse_docx(docx_path)
    script = extract_steps(title, blocks, os.path.expanduser(docx_path), catalog, classifier)

    # Routing (browser-vs-desktop) per step.
    prefer_browser = config["routing"].get("prefer_browser", True)
    script = route_steps(script, catalog, prefer_browser)

    # Tool detection + readiness.
    statuses = detect_tools(script.required_tools, catalog)
    report = build_report(script, statuses)

    # Preview the clean-capture settings we WOULD use (no recording happens).
    preview = {}
    for route in ("browser", "desktop"):
        try:
            s = prepare_settings(config, route, output_path="(prepared at run time)")
            preview[route] = f"{s.backend} / {s.capture_type} {s.width}x{s.height}@{s.fps}fps"
        except ValueError as e:
            preview[route] = f"unavailable: {e}"

    return AnalysisResult(script=script, report=report, capture_preview=preview)


@dataclass
class CourseAnalysis:
    course: Course
    report: ReadinessReport       # readiness across ALL lessons' tools


def analyze_course(docx_path: str, config_path: str | None = None,
                   catalog_path: str | None = None) -> CourseAnalysis:
    """Split a combined course doc into lessons and analyze each one.

    Each Lesson becomes its own recordable unit (one clean MP4 per lesson).
    """
    config = cfg.load_config(config_path)
    catalog = cfg.load_catalog(catalog_path)
    classifier = get_classifier(config)
    prefer_browser = config["routing"].get("prefer_browser", True)

    title, blocks = parse_docx(docx_path)
    lesson_blocks = split_course(blocks)

    lessons: list[Lesson] = []
    for lb in lesson_blocks:
        script = extract_steps(
            f"{lb.lesson_id} — {lb.title}", lb.blocks, os.path.expanduser(docx_path),
            catalog, classifier,
        )
        script = route_steps(script, catalog, prefer_browser)
        lessons.append(Lesson(
            lesson_id=lb.lesson_id, title=lb.title, est_minutes=lb.est_minutes,
            required_tools=script.required_tools, steps=script.steps,
        ))

    course = Course(title=title, source_file=os.path.expanduser(docx_path), lessons=lessons)

    # One readiness report for the whole course (union of tools).
    statuses = detect_tools(course.required_tools, catalog)
    report = build_report(DemoScript(title=title), statuses)
    return CourseAnalysis(course=course, report=report)


def write_course_json(course: Course, out_dir: str) -> list[str]:
    """Write one JSON per lesson plus a course index. Returns written paths."""
    out_dir = os.path.expanduser(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for lesson in course.lessons:
        p = os.path.join(out_dir, f"lesson_{lesson.lesson_id.replace('.', '_')}.json")
        with open(p, "w") as f:
            json.dump(lesson.model_dump(mode="json"), f, indent=2)
        paths.append(p)
    index = os.path.join(out_dir, "course_index.json")
    with open(index, "w") as f:
        json.dump(course.model_dump(mode="json"), f, indent=2)
    paths.append(index)
    return paths


def write_json(script: DemoScript, out_path: str) -> str:
    out_path = os.path.expanduser(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(script.model_dump(mode="json"), f, indent=2)
    return out_path


def _drive_browser_steps(page, lesson: Lesson, catalog: dict, log: dict) -> None:
    from .executor.browser_exec import execute_step
    for step in lesson.steps:
        if step.route.value == "browser":
            log["actions"].append(execute_step(page, step, catalog))
        elif step.route.value == "desktop":
            log["deferred"].append({"index": step.index, "reason": "desktop/OBS path",
                                    "text": step.raw_text[:120]})
        # narration/undecided: held as a recorded pause / skipped


def run_lesson(lesson: Lesson, out_mp4: str, config_path: str | None = None,
               catalog_path: str | None = None) -> dict:
    """Record a single lesson's BROWSER steps into one clean MP4.

    Recording backend follows recording.browser.connect:
      launch -> Playwright launches Chromium (persistent profile) + viewport video.
      cdp    -> drive your real Chrome over CDP; OBS records the Chrome window.
    Desktop (Excel/Copilot) steps are deferred to the OBS desktop path and listed
    in the log. Returns a run log dict to persist next to the MP4.
    """
    from .executor.browser_session import open_session
    from .recorder.encode import to_mp4

    config = cfg.load_config(config_path)
    catalog = cfg.load_catalog(catalog_path)
    out_mp4 = os.path.expanduser(out_mp4)
    os.makedirs(os.path.dirname(out_mp4) or ".", exist_ok=True)
    mode = config["recording"].get("browser", {}).get("connect", "launch")

    log: dict = {"lesson_id": lesson.lesson_id, "title": lesson.title,
                 "mode": mode, "actions": [], "deferred": []}

    if mode == "cdp":
        # Real Chrome recorded by OBS window capture; driven over CDP.
        from .recorder.base import prepare_settings
        from .recorder.obs_rec import ObsRecorder

        settings = prepare_settings(config, "desktop", out_mp4)
        chrome_scene = config["recording"]["browser"].get("obs_scene_chrome")
        if chrome_scene:
            settings.extra = {**settings.extra, "scene": chrome_scene}
        rec = ObsRecorder(settings, export_cfg=config["export"])
        sess = open_session(config)
        rec.start()
        try:
            _drive_browser_steps(sess.page, lesson, catalog, log)
        finally:
            rec.stop(); sess.close()
        log["mp4"] = rec.export(out_mp4)
        return log

    # launch mode: Playwright viewport video.
    video_dir = os.path.dirname(out_mp4) or "."
    sess = open_session(config, video_dir=video_dir)
    page = sess.page
    try:
        _drive_browser_steps(page, lesson, catalog, log)
        raw = page.video.path() if page.video else None
    finally:
        sess.close()   # finalizes the .webm
    if not raw or not os.path.exists(raw):
        raise RuntimeError("No Playwright video produced.")
    log["mp4"] = to_mp4(raw, out_mp4, config["export"])
    return log


def run(docx_path: str, **kwargs):  # pragma: no cover
    """Full course execute + record. Built on run_lesson per lesson (WIP)."""
    raise NotImplementedError("Use run_lesson() / `democap analyze|course` for now.")
