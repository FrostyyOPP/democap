"""democap CLI.

  democap analyze SCRIPT.docx [--json OUT] [--no-prompt]
      Phase 1-3: parse, extract steps, detect tools, print readiness report,
      and (unless --no-prompt) ask how to handle any missing desktop tools.

  democap run SCRIPT.docx
      Phase 4-5: execute + record. Not yet implemented (prints guidance).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import orchestrator
from .readiness import print_report, prompt_on_gaps

app = typer.Typer(add_completion=False, help="Turn a Word demo script into a clean MP4 demo (macOS).")


@app.command()
def analyze(
    script: Path = typer.Argument(..., help="Path to the .docx demo script."),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Write parsed steps JSON here."),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Skip interactive missing-tool prompts."),
    config: Optional[Path] = typer.Option(None, "--config", help="Override config YAML."),
    catalog: Optional[Path] = typer.Option(None, "--catalog", help="Override tools catalog YAML."),
):
    """Parse a script and print a readiness report (no recording, safe to run)."""
    result = orchestrator.analyze(str(script), config_path=str(config) if config else None,
                                  catalog_path=str(catalog) if catalog else None)
    print_report(result.script, result.report)

    typer.echo("")
    typer.secho("Clean-capture plan (no recording performed):", bold=True)
    for route, summary in result.capture_preview.items():
        typer.echo(f"  {route:8s} -> {summary}")

    if json_out:
        path = orchestrator.write_json(result.script, str(json_out))
        typer.secho(f"\nParsed steps written to {path}", fg="green")

    if not no_prompt:
        decisions = prompt_on_gaps(result.report)
        if decisions:
            typer.echo("")
            typer.secho("Recorded your choices for missing tools:", bold=True)
            for tool, choice in decisions.items():
                typer.echo(f"  {tool}: {choice}")


@app.command()
def course(
    script: Path = typer.Argument(..., help="Path to a combined multi-lesson course .docx."),
    json_dir: Optional[Path] = typer.Option(None, "--json-dir", help="Write per-lesson JSON here."),
    config: Optional[Path] = typer.Option(None, "--config"),
    catalog: Optional[Path] = typer.Option(None, "--catalog"),
):
    """Split a full course into lessons and show a per-lesson recording plan."""
    from rich.console import Console
    from rich.table import Table

    result = orchestrator.analyze_course(
        str(script), config_path=str(config) if config else None,
        catalog_path=str(catalog) if catalog else None,
    )
    course = result.course
    console = Console()

    tbl = Table(title=f"Course: {course.title}  ({len(course.lessons)} lessons)")
    tbl.add_column("Lesson", style="cyan")
    tbl.add_column("Title", overflow="fold", max_width=42)
    tbl.add_column("~min", justify="right")
    tbl.add_column("Demos", justify="right", style="green")
    tbl.add_column("Narr", justify="right", style="blue")
    tbl.add_column("Tools")
    total_demos = total_min = 0.0
    for L in course.lessons:
        total_demos += L.demo_count
        total_min += L.est_minutes
        tbl.add_row(L.lesson_id, L.title, f"{L.est_minutes:g}" if L.est_minutes else "—",
                    str(L.demo_count), str(L.narration_count), ", ".join(L.required_tools) or "—")
    console.print(tbl)
    console.print(f"[bold]Total:[/bold] {len(course.lessons)} lessons · "
                  f"~{total_min:g} min · {int(total_demos)} demo segments to record")

    # Course-wide readiness verdict.
    from rich.panel import Panel

    from .readiness import console as rconsole
    if result.report.ready:
        rconsole.print(Panel.fit(
            f"[green]READY[/green] — course tools available: {', '.join(course.required_tools)}",
            title="Verdict"))
    else:
        names = ", ".join(b.key for b in result.report.blockers)
        rconsole.print(Panel.fit(f"[red]NOT READY[/red] — missing: {names}", title="Verdict"))

    if json_dir:
        paths = orchestrator.write_course_json(course, str(json_dir))
        typer.secho(f"\nWrote {len(paths)} files to {json_dir}", fg="green")


@app.command(name="run-lesson")
def run_lesson_cmd(
    script: Path = typer.Argument(..., help="Combined course .docx."),
    lesson_id: str = typer.Argument(..., help="Lesson id to record, e.g. 1.1"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output MP4 path."),
    config: Optional[Path] = typer.Option(None, "--config"),
    catalog: Optional[Path] = typer.Option(None, "--catalog"),
):
    """Execute + record ONE lesson's browser steps into a clean MP4.

    Desktop (Excel/Copilot) steps are deferred and listed in the run log; record
    those via the OBS desktop path. Browser recording follows recording.browser.connect
    (cdp = your real Chrome via OBS; launch = Playwright video)."""
    import json as _json

    result = orchestrator.analyze_course(
        str(script), config_path=str(config) if config else None,
        catalog_path=str(catalog) if catalog else None,
    )
    lesson = next((L for L in result.course.lessons if L.lesson_id == lesson_id), None)
    if lesson is None:
        ids = ", ".join(L.lesson_id for L in result.course.lessons)
        typer.secho(f"Lesson {lesson_id!r} not found. Available: {ids}", fg="red")
        raise typer.Exit(1)

    out_path = str(out) if out else f"runs/{lesson.lesson_id.replace('.', '_')}.mp4"
    typer.secho(f"Recording lesson {lesson.lesson_id} — {lesson.title}", bold=True)
    typer.echo(f"  browser steps: {sum(s.route.value=='browser' for s in lesson.steps)}  "
               f"deferred desktop: {sum(s.route.value=='desktop' for s in lesson.steps)}")
    log = orchestrator.run_lesson(
        lesson, out_path, config_path=str(config) if config else None,
        catalog_path=str(catalog) if catalog else None,
    )
    ok = sum(a["ok"] for a in log["actions"])
    typer.secho(f"\nDone: {ok}/{len(log['actions'])} browser actions ok · "
                f"{len(log['deferred'])} desktop steps deferred", fg="green")
    typer.echo(f"  MP4: {log['mp4']}")
    log_path = out_path.rsplit(".", 1)[0] + ".runlog.json"
    with open(log_path, "w") as f:
        _json.dump(log, f, indent=2)
    typer.echo(f"  log: {log_path}")


@app.command(name="setup-obs")
def setup_obs(
    keep_password: bool = typer.Option(False, "--keep-password",
        help="Reuse the password already in config instead of generating a new one."),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Automatically enable OBS WebSocket and create the democap capture scenes.

    Quits OBS, writes the WebSocket config (server on + password), relaunches OBS,
    waits for it, then creates one clean app-window-capture scene per app in
    config (`recording.obs.scenes`). The only manual step left is granting OBS the
    OS screen-recording permission (it can't be scripted) — this opens that pane.
    """
    from . import config as cfg
    from . import obs_setup
    from .config import DEFAULT_CONFIG

    conf = cfg.load_config(str(config) if config else None)
    obs_cfg = conf["recording"]["obs"]
    scenes = obs_cfg.get("scenes", {})
    config_file = str(config) if config else str(DEFAULT_CONFIG)

    typer.secho("Setting up OBS (this will quit & relaunch OBS)...", bold=True)
    obs_setup.quit_obs()
    if keep_password:
        password = obs_cfg["password"]
    else:
        password = obs_setup.enable_websocket(port=obs_cfg["port"])
        obs_setup.set_config_password(password, config_file)
        typer.echo(f"  WebSocket enabled on port {obs_cfg['port']} (password saved to config)")
    if keep_password:
        obs_setup.enable_websocket(port=obs_cfg["port"], password=password)

    obs_setup.launch_obs()
    typer.echo("  launched OBS, waiting for WebSocket...")
    if not obs_setup.wait_for_websocket(obs_cfg["port"]):
        typer.secho("  WebSocket didn't come up. Is OBS installed? Launch it once, then re-run.", fg="red")
        raise typer.Exit(1)

    # reload config to pick up the new password for the API call
    obs_cfg = cfg.load_config(config_file)["recording"]["obs"]
    created = obs_setup.create_scenes(obs_cfg, scenes)
    typer.secho(f"  created/verified scenes: {', '.join(created) or '(none configured)'}", fg="green")

    typer.echo("")
    typer.secho("One unavoidable manual step (OS security):", fg="yellow", bold=True)
    typer.echo("  Grant OBS 'Screen & System Audio Recording' permission, then quit & reopen OBS.")
    typer.echo("  Opening that settings pane now...")
    obs_setup.open_screen_recording_settings()
    typer.echo("\nThen verify with:  democap doctor")


@app.command()
def doctor(config: Optional[Path] = typer.Option(None, "--config")):
    """Check that everything democap needs is installed and reachable."""
    import shutil
    from . import config as cfg
    from . import obs_setup

    ok = True
    def check(label, good, hint=""):
        nonlocal ok
        ok = ok and good
        typer.echo(f"  [{'✓' if good else '✗'}] {label}" + (f"  → {hint}" if not good and hint else ""))

    typer.secho("democap doctor", bold=True)
    check("ffmpeg on PATH", shutil.which("ffmpeg") is not None, "install ffmpeg (brew/winget)")
    try:
        import playwright  # noqa
        check("playwright installed", True)
    except Exception:
        check("playwright installed", False, "pip install playwright && playwright install chromium")
    conf = cfg.load_config(str(config) if config else None)
    obs_cfg = conf["recording"]["obs"]
    ws = obs_setup.wait_for_websocket(obs_cfg["port"], timeout=2)
    check(f"OBS WebSocket on :{obs_cfg['port']}", ws, "run `democap setup-obs` and launch OBS")
    if ws:
        try:
            import obsws_python as obs
            c = obs.ReqClient(host=obs_cfg["host"], port=obs_cfg["port"], password=obs_cfg["password"], timeout=4)
            have = {s["sceneName"] for s in c.get_scene_list().scenes}
            for name in obs_cfg.get("scenes", {}):
                check(f"OBS scene '{name}'", name in have, "run `democap setup-obs`")
        except Exception as e:
            check("OBS WebSocket auth", False, f"password mismatch? ({e})")
    typer.secho("\nAll good — ready to record." if ok else "\nSome checks failed (see hints above).",
                fg="green" if ok else "yellow")


@app.command()
def run(script: Path = typer.Argument(..., help="Path to the .docx demo script.")):
    """Execute and record a full course (built on run-lesson; WIP)."""
    typer.secho("Full-course `run` is WIP. Use `democap run-lesson <course.docx> <id>`.", fg="yellow")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
