"""Automated OBS setup — enable the WebSocket server and create democap scenes.

Removes the manual OBS clicking from setup:
  * `enable_websocket()` writes OBS's obs-websocket config (server on + password),
    so after one OBS (re)launch democap can control it. Cross-platform config path.
  * `create_scenes()` connects over the WebSocket and creates one clean
    window/application-capture scene per app in config (`recording.obs.scenes`),
    framed to fit the canvas. API-driven, so it's reliable across OBS versions.

The ONE thing that can't be scripted is granting OBS macOS Screen Recording
permission (protected by the OS) — `open_screen_recording_settings()` jumps you
straight to the right System Settings pane.
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import subprocess
import time


def obs_config_dir() -> str:
    sysname = platform.system()
    if sysname == "Darwin":
        return os.path.expanduser("~/Library/Application Support/obs-studio")
    if sysname == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "obs-studio")
    return os.path.expanduser("~/.config/obs-studio")  # Linux


def gen_password(n: int = 18) -> str:
    return secrets.token_urlsafe(n)[:n]


def enable_websocket(port: int = 4455, password: str | None = None) -> str:
    """Enable obs-websocket with auth. Returns the password (generated if None).

    OBS must NOT be running when this writes (it overwrites on quit otherwise);
    launch/relaunch OBS afterwards for it to take effect.
    """
    password = password or gen_password()
    cfg_path = os.path.join(obs_config_dir(), "plugin_config", "obs-websocket", "config.json")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    data = {
        "alerts_enabled": False,
        "auth_required": True,
        "first_load": False,
        "server_enabled": True,
        "server_password": password,
        "server_port": int(port),
    }
    with open(cfg_path, "w") as f:
        json.dump(data, f, indent=4)
    return password


def open_screen_recording_settings() -> None:
    """Jump to the OS screen-recording permission pane (the one manual step)."""
    if platform.system() == "Darwin":
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
            check=False,
        )


# ---- OBS process control ----------------------------------------------------

def quit_obs() -> None:
    if platform.system() == "Darwin":
        subprocess.run(["osascript", "-e", 'quit app "OBS"'], check=False)
        time.sleep(2)
        subprocess.run(["pkill", "-f", "OBS.app/Contents/MacOS/OBS"], check=False)
    elif platform.system() == "Windows":
        subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], check=False)
    else:
        subprocess.run(["pkill", "-x", "obs"], check=False)
    time.sleep(1)


def launch_obs() -> None:
    sysname = platform.system()
    if sysname == "Darwin":
        subprocess.run(["open", "-a", "OBS"], check=False)
    elif sysname == "Windows":
        # OBS must be launched from its own dir; best-effort via Start.
        subprocess.run(["cmd", "/c", "start", "", "obs64.exe"], check=False)
    else:
        subprocess.Popen(["obs"])


def wait_for_websocket(port: int = 4455, timeout: int = 30) -> bool:
    import socket
    for _ in range(timeout):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(1)
    return False


def set_config_password(password: str, config_path: str) -> None:
    """Write the generated password into democap's config (line-targeted, keeps comments)."""
    import re
    with open(config_path) as f:
        text = f.read()
    text = re.sub(r'(\n\s*password:\s*)"[^"]*"', rf'\1"{password}"', text, count=1)
    with open(config_path, "w") as f:
        f.write(text)


# ---- scene creation over the WebSocket --------------------------------------

def _input_kind_and_settings(spec: dict) -> tuple[str, dict]:
    """Per-OS capture input kind + settings for an app spec."""
    sysname = platform.system()
    if sysname == "Darwin":
        # macOS Screen Capture, type 2 = application capture
        return "screen_capture", {"type": 2, "application": spec.get("bundle_id", "")}
    if sysname == "Windows":
        # Windows window capture; match by executable (best-effort).
        return "window_capture", {"method": 2, "window": f"::{spec.get('exe', '')}"}
    return "xcomposite_input", {}  # Linux placeholder


def create_scenes(obs_cfg: dict, scenes: dict, canvas=(1920, 1080)) -> list[str]:
    """Create one capture scene per entry in `scenes` via obs-websocket.

    scenes: {scene_name: {app, bundle_id, exe}}. Returns created scene names.
    Existing scenes/inputs are skipped, so this is safe to re-run.
    """
    import obsws_python as obs

    cl = obs.ReqClient(host=obs_cfg["host"], port=obs_cfg["port"],
                       password=obs_cfg["password"], timeout=5)
    existing = {s["sceneName"] for s in cl.get_scene_list().scenes}
    created = []
    for scene_name, spec in scenes.items():
        if scene_name not in existing:
            cl.create_scene(scene_name)
        kind, settings = _input_kind_and_settings(spec)
        input_name = f"{spec.get('app', scene_name)} capture"
        try:
            cl.create_input(scene_name, input_name, kind, settings, True)
            time.sleep(1.0)
        except Exception:
            pass  # input may already exist
        # Fit + center the source in the canvas.
        try:
            for it in cl.get_scene_item_list(scene_name).scene_items:
                cl.set_scene_item_transform(scene_name, it["sceneItemId"], {
                    "positionX": 0.0, "positionY": 0.0, "alignment": 5,
                    "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                    "boundsWidth": float(canvas[0]), "boundsHeight": float(canvas[1]),
                })
        except Exception:
            pass
        created.append(scene_name)
    return created
