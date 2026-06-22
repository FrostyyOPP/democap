"""Tool detection layer (macOS).

Given the tool keys a script requires, decide for each whether it is available
on this machine. Detection order per tool:
  1. app bundle present in /Applications or /System/Applications
  2. Spotlight (mdfind) lookup by bundle id  -> catches non-standard locations
  3. CLI on PATH (e.g. `code`)

Pure-browser tools (no app_names / bundle_id) are considered "installed" as long
as a browser exists, since they run on the web.

TODO(windows): implement a platform/windows.py detector using the registry /
`where` / Start-Menu shortcuts, and select it via platform.system().
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .models import Classification, ToolStatus

_APP_DIRS = ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]


def _app_installed(app_names: list[str]) -> str | None:
    for name in app_names:
        for base in _APP_DIRS:
            path = os.path.join(base, f"{name}.app")
            if os.path.isdir(path):
                return path
    return None


def _mdfind_bundle(bundle_id: str) -> str | None:
    try:
        out = subprocess.run(
            ["mdfind", f"kMDItemCFBundleIdentifier == '{bundle_id}'"],
            capture_output=True, text=True, timeout=8,
        )
        first = out.stdout.strip().splitlines()
        return first[0] if first else None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def detect_tool(key: str, spec: dict) -> ToolStatus:
    classification = Classification(spec.get("classification", "optional"))
    app_names = spec.get("app_names", []) or []
    bundle_id = spec.get("bundle_id")
    cli = spec.get("cli")
    alt = spec.get("browser_alt") or {}

    status = ToolStatus(
        key=key,
        classification=classification,
        installed=False,
        browser_alt_name=alt.get("name"),
        browser_alt_url=alt.get("url"),
    )

    # 1. App bundle in standard locations.
    if app_names:
        path = _app_installed(app_names)
        if path:
            return status.model_copy(update={"installed": True, "detected_via": "app", "app_path": path})

    # 2. Spotlight by bundle id.
    if bundle_id:
        path = _mdfind_bundle(bundle_id)
        if path:
            return status.model_copy(update={"installed": True, "detected_via": "bundle_id", "app_path": path})

    # 3. CLI on PATH.
    if cli and shutil.which(cli):
        return status.model_copy(update={"installed": True, "detected_via": "cli", "app_path": shutil.which(cli)})

    # 4. Pure web tool (no native footprint expected) -> available via browser.
    if not app_names and not bundle_id and not cli:
        return status.model_copy(update={"installed": True, "detected_via": "browser"})

    return status


def detect_tools(keys: list[str], catalog: dict) -> list[ToolStatus]:
    """Detect each requested tool key. Unknown keys are reported as optional/missing."""
    results: list[ToolStatus] = []
    for key in keys:
        spec = catalog.get(key)
        if spec is None:
            results.append(ToolStatus(key=key, classification=Classification.OPTIONAL, installed=False))
            continue
        results.append(detect_tool(key, spec))
    return results
