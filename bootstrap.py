#!/usr/bin/env python3
"""democap one-command setup. Run with system Python from the repo root:

    python3 bootstrap.py

Does everything automatically:
  1. system deps (ffmpeg, OBS) via the OS package manager (brew / winget / apt)
  2. a project virtualenv (.venv)
  3. democap + its Python deps (editable install)
  4. the Playwright Chromium browser

After it finishes, two commands complete OBS setup:
    .venv/bin/democap setup-obs      # enable WebSocket + create capture scenes
    .venv/bin/democap doctor         # verify everything is ready
(On Windows use .venv\\Scripts\\democap.exe)

The only step that cannot be automated is granting OBS the OS screen-recording
permission (protected by macOS/Windows); `setup-obs` opens that pane for you.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import venv

ROOT = os.path.dirname(os.path.abspath(__file__))
SYS = platform.system()
IS_WIN = SYS == "Windows"


def run(cmd, **kw):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, **kw)


def have(exe: str) -> bool:
    return shutil.which(exe) is not None


def pkg_manager() -> str | None:
    for pm in (["brew"] if SYS == "Darwin" else ["winget", "choco"] if IS_WIN else ["apt-get", "dnf", "pacman"]):
        if have(pm):
            return pm
    return None


def install_system_deps():
    print("\n[1/4] System dependencies (ffmpeg, OBS)")
    pm = pkg_manager()
    need_ffmpeg = not have("ffmpeg")
    need_obs = not _obs_installed()
    if not need_ffmpeg and not need_obs:
        print("  ✓ ffmpeg and OBS already present")
        return
    if pm is None:
        print(f"  ! No package manager found. Install manually:")
        if need_ffmpeg: print("    - ffmpeg: https://ffmpeg.org/download.html")
        if need_obs: print("    - OBS Studio: https://obsproject.com/download")
        return
    if pm == "brew":
        if need_ffmpeg: run(["brew", "install", "ffmpeg"])
        if need_obs: run(["brew", "install", "--cask", "obs"])
    elif pm == "winget":
        if need_ffmpeg: run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-package-agreements", "--accept-source-agreements"])
        if need_obs: run(["winget", "install", "-e", "--id", "OBSProject.OBSStudio", "--accept-package-agreements", "--accept-source-agreements"])
    elif pm == "choco":
        if need_ffmpeg: run(["choco", "install", "ffmpeg", "-y"])
        if need_obs: run(["choco", "install", "obs-studio", "-y"])
    else:  # apt/dnf/pacman
        installer = {"apt-get": ["sudo", "apt-get", "install", "-y"],
                     "dnf": ["sudo", "dnf", "install", "-y"],
                     "pacman": ["sudo", "pacman", "-S", "--noconfirm"]}[pm]
        pkgs = (["ffmpeg"] if need_ffmpeg else []) + (["obs-studio"] if need_obs else [])
        if pkgs: run(installer + pkgs)


def _obs_installed() -> bool:
    if SYS == "Darwin":
        return os.path.isdir("/Applications/OBS.app")
    if IS_WIN:
        return any(os.path.exists(os.path.join(p, "obs-studio")) for p in
                   [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")])
    return have("obs")


def venv_python() -> str:
    return os.path.join(ROOT, ".venv", "Scripts" if IS_WIN else "bin", "python.exe" if IS_WIN else "python")


def make_venv():
    print("\n[2/4] Virtualenv (.venv)")
    if not os.path.exists(venv_python()):
        venv.create(os.path.join(ROOT, ".venv"), with_pip=True)
        print("  ✓ created .venv")
    else:
        print("  ✓ .venv already exists")


def install_python():
    print("\n[3/4] democap + Python dependencies")
    py = venv_python()
    run([py, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    run([py, "-m", "pip", "install", "-e", ".", "-q"], cwd=ROOT)
    print("  ✓ installed")


def install_chromium():
    print("\n[4/4] Playwright Chromium")
    run([venv_python(), "-m", "playwright", "install", "chromium"])


def main():
    print("democap bootstrap —", SYS)
    install_system_deps()
    make_venv()
    install_python()
    install_chromium()
    dem = os.path.join(".venv", "Scripts" if IS_WIN else "bin", "democap")
    print("\n✅ Setup complete. Next:")
    print(f"   {dem} setup-obs     # enable OBS WebSocket + create capture scenes")
    print(f"   {dem} doctor        # verify everything is ready")
    print(f"   {dem} analyze samples/sample_script.docx   # try the parser")


if __name__ == "__main__":
    sys.exit(main())
