"""Jane's reach into the rest of the desktop: installed apps, WhatsApp, games.

Everything here drives programs the user already has, through their own launch
protocols (whatsapp://, steam://) or a small editable alias file — never by
poking at their windows blindly. Names → targets live in data/*.json so the
user can extend the list without touching code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from urllib.parse import quote

from . import config
from .logbus import bus


def _load_aliases(path) -> dict:
    """Read a {name: target} JSON map, tolerating a missing or broken file."""
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except (json.JSONDecodeError, OSError) as exc:
        bus.log(f"Couldn't read {path.name}: {exc}", "warn")
    return {}


def contacts() -> dict:
    return _load_aliases(config.CONTACTS_FILE)


def games() -> dict:
    return _load_aliases(config.GAMES_FILE)


def _open_target(target: str) -> None:
    """Open a URI (whatsapp://, steam://…) or a filesystem path, cross-platform."""
    if sys.platform == "win32":
        # os.startfile handles both protocol URIs and executables on Windows.
        os.startfile(target)  # noqa: S606 — user-scoped desktop action
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def _digits(raw: str) -> str:
    """Keep a WhatsApp number as digits only (country code included, no +)."""
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _press_enter_soon(delay: float = 1.6) -> None:
    """Best-effort: send an Enter keystroke to the foreground window shortly.

    WhatsApp's send-URI pre-fills the message but never sends it on its own, so
    after the window has focused we synthesise the one keystroke that does. This
    runs only once the user has already confirmed the wording.
    """
    if sys.platform != "win32":
        return

    def fire() -> None:
        time.sleep(delay)
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')"],
                check=False, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            bus.log(f"Auto-send keystroke failed: {exc}", "warn")

    threading.Thread(target=fire, daemon=True).start()


# --- WhatsApp -----------------------------------------------------------
def whatsapp_message(to: str, text: str) -> str:
    """Open the WhatsApp desktop chat for `to`, message pre-filled.

    `to` is a saved contact name (data/contacts.json) or a phone number with
    country code. If auto-send is on, the message is sent; otherwise it waits
    in the box for the user to press Enter.
    """
    if not config.ALLOW_DESKTOP:
        return "Desktop control is off. Set JANE_ALLOW_DESKTOP=1 in .env to enable it."
    text = (text or "").strip()
    if not text:
        return "There's no message to send. Tell me what to say."

    key = (to or "").strip().lower()
    number = _digits(contacts().get(key, to))
    if not number:
        return (f"I don't have a number for '{to}'. Add it to data/contacts.json "
                f"as \"name\": \"<country code + number>\", or give me the number.")

    uri = f"whatsapp://send?phone={number}&text={quote(text)}"
    try:
        _open_target(uri)
    except OSError as exc:
        return f"Couldn't open WhatsApp: {exc}. Is the desktop app installed?"

    who = to if key in contacts() else number
    if config.WHATSAPP_AUTOSEND:
        _press_enter_soon()
        bus.log(f"WhatsApp → {who}", "ok")
        return f"Sent to {who} on WhatsApp."
    bus.log(f"WhatsApp draft → {who}", "info")
    return f"It's in the chat with {who}, ready — press Enter to send."


# --- games --------------------------------------------------------------
def play_game(name: str) -> str:
    """Launch a game by alias (data/games.json → steam:// URI or exe path)."""
    if not config.ALLOW_DESKTOP:
        return "Desktop control is off. Set JANE_ALLOW_DESKTOP=1 in .env to enable it."
    key = (name or "").strip().lower()
    table = games()
    target = table.get(key)
    # Bare 'steam' / a steam app id still works without an alias.
    if not target and key.isdigit():
        target = f"steam://rungameid/{key}"
    if not target:
        known = ", ".join(sorted(table)) or "none yet"
        return (f"I don't know '{name}'. Add it to data/games.json (name → a "
                f"steam://rungameid/… link or the game's .exe). Known: {known}.")
    try:
        _open_target(target)
    except OSError as exc:
        return f"Couldn't launch {name}: {exc}"
    bus.log(f"Launched game: {key}", "ok")
    return f"Launching {name}. Queuing you in."
