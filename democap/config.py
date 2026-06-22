"""Config + tool-catalog loading. Thin wrapper around YAML with ~ expansion."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_PKG_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = _PKG_ROOT / "config" / "default.yaml"
DEFAULT_CATALOG = _PKG_ROOT / "config" / "tools_catalog.yaml"


def _expand(obj):
    if isinstance(obj, dict):
        return {k: _expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("~"):
        return os.path.expanduser(obj)
    return obj


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path) as f:
        return _expand(yaml.safe_load(f))


def load_catalog(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CATALOG
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("tools", {})
