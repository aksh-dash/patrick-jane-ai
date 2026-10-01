"""Entry point: `python -m jane`."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from . import config
from .server import serve

BANNER = r"""
   ____   _____   _   _   _____
  |__ / \ |  _  | | \ | | |  ___|
   |_| |_||_|_|_| |_| \_| |_____|
        J . A . N . E .
   consulting intelligence — v{version}
"""

# Chromium browsers can open a chromeless single-window "app". That is what
# turns Jane from a browser tab into something that feels like a desktop
# program — and, because it is exactly one window, it also kills the
# double-voice you get from two tabs both talking at once.
_CHROME_CANDIDATES = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    shutil.which("chrome"),
    shutil.which("msedge"),
]


def _find_browser() -> str | None:
    for path in _CHROME_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def _open_app_window(url: str) -> bool:
    """Launch a dedicated chromeless window. Returns False if no Chromium found."""
    exe = _find_browser()
    if not exe:
        return False
    profile = str(config.DATA_DIR / "app-window")
    subprocess.Popen([
        exe,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
    ])
    return True


def main() -> int:
    print(BANNER.format(version=config.VERSION))
    if not config.API_KEY:
        print("  ! No ANTHROPIC_API_KEY found.")
        print("    Copy .env.example to .env and add your key, then restart.")
        print("    The dashboard still runs; Jane just won't talk back.\n")

    url = f"http://127.0.0.1:{config.PORT}"
    # --app  → dedicated desktop-style window (default when double-clicked via
    #          the launcher). --no-browser → open nothing. Otherwise, a tab.
    app_mode = "--app" in sys.argv
    no_browser = "--no-browser" in sys.argv

    def open_later() -> None:
        time.sleep(1.2)
        if app_mode and _open_app_window(url):
            return
        webbrowser.open(url)

    if not no_browser:
        threading.Thread(target=open_later, daemon=True).start()

    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
