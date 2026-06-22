"""Phase 3: build and present the readiness report, and prompt on gaps.

The report answers: "Given this script, can democap record cleanly right now,
and if not, what's missing and what are my options?" It never auto-installs or
auto-substitutes — when a desktop tool is missing it stops and asks you, exactly
as the project requires.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Classification, DemoScript, ReadinessReport, Route, ToolStatus

console = Console()


def build_report(script: DemoScript, tool_statuses: list[ToolStatus]) -> ReadinessReport:
    return ReadinessReport(script_title=script.title, tools=tool_statuses)


def print_report(script: DemoScript, report: ReadinessReport) -> None:
    console.print(Panel.fit(f"[bold]Demo:[/bold] {script.title}", title="democap readiness"))

    # --- Steps overview ---
    steps_tbl = Table(title=f"Parsed steps ({len(script.steps)})", show_lines=False)
    steps_tbl.add_column("#", justify="right", style="cyan")
    steps_tbl.add_column("Action")
    steps_tbl.add_column("Route")
    steps_tbl.add_column("Tools")
    steps_tbl.add_column("Text", overflow="fold", max_width=48)
    for s in script.steps:
        route_style = {
            Route.BROWSER: "green", Route.DESKTOP: "yellow",
            Route.NARRATION: "blue", Route.UNDECIDED: "red",
        }.get(s.route, "white")
        risky = " [red]⚠[/red]" if s.risky else ""
        steps_tbl.add_row(
            str(s.index), s.action.value,
            f"[{route_style}]{s.route.value}[/{route_style}]",
            ", ".join(s.target_tools) or "—",
            s.raw_text + risky,
        )
    console.print(steps_tbl)

    # --- Tools / readiness ---
    tools_tbl = Table(title="Required tools")
    tools_tbl.add_column("Tool", style="bold")
    tools_tbl.add_column("Type")
    tools_tbl.add_column("Installed")
    tools_tbl.add_column("Detected via")
    tools_tbl.add_column("Browser alternative")
    for t in report.tools:
        installed = "[green]yes[/green]" if t.installed else "[red]no[/red]"
        alt = f"{t.browser_alt_name} ({t.browser_alt_url})" if t.browser_alt_url else "—"
        tools_tbl.add_row(t.key, t.classification.value, installed, t.detected_via or "—", alt)
    console.print(tools_tbl)

    # --- Verdict ---
    if report.ready:
        console.print(Panel.fit(
            "[green]READY[/green] — all required tools are available. "
            f"Browser steps → [green]{report.recording_backend_browser}[/green], "
            f"desktop steps → [yellow]{report.recording_backend_desktop}[/yellow].",
            title="Verdict",
        ))
    else:
        names = ", ".join(b.key for b in report.blockers)
        console.print(Panel.fit(
            f"[red]NOT READY[/red] — missing desktop-required tool(s): {names}",
            title="Verdict",
        ))


def prompt_on_gaps(report: ReadinessReport) -> dict:
    """Interactive resolution for blockers. Returns a dict of {tool_key: choice}.

    Choices: 'install' (you'll install it), 'alternative' (use browser alt if any),
    'skip' (drop steps needing it). Never installs anything itself.
    """
    decisions: dict[str, str] = {}
    if report.ready:
        return decisions

    from rich.prompt import Prompt

    console.print("\n[bold yellow]Some required tools are missing. Tell me how to proceed.[/bold yellow]")
    for blocker in report.blockers:
        opts = ["install", "skip"]
        if blocker.browser_alt_url:
            opts.insert(1, "alternative")
        choice = Prompt.ask(
            f"  [bold]{blocker.key}[/bold] is not installed. What should I do?",
            choices=opts, default=opts[0],
        )
        decisions[blocker.key] = choice
    return decisions
