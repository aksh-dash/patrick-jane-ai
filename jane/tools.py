"""The tools Jane can actually reach for, plus their dispatch table."""
from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser

from . import config, desktop, ledger, mailer, memory, metrics, netmap, news, speech, weather, workspace
from .logbus import bus

# --- app launcher -------------------------------------------------------
# Deliberately a fixed map, not free-form shell. Jane cannot run arbitrary
# commands on the host; she can only open things on this list.
_APPS: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "file manager": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "paint": ["mspaint.exe"],
    "settings": ["cmd", "/c", "start", "ms-settings:"],
    "camera": ["cmd", "/c", "start", "microsoft.windows.camera:"],
    "terminal": ["cmd", "/c", "start", "cmd"],
    "chrome": ["cmd", "/c", "start", "chrome"],
    "edge": ["cmd", "/c", "start", "msedge"],
    "spotify": ["cmd", "/c", "start", "spotify:"],
    "vs code": ["cmd", "/c", "start", "code"],
    "code": ["cmd", "/c", "start", "code"],
    "whatsapp": ["cmd", "/c", "start", "whatsapp:"],
    "steam": ["cmd", "/c", "start", "steam://open/main"],
    "discord": ["cmd", "/c", "start", "discord:"],
}

# The user can add their own {name: ["command", "arg", …]} entries in
# data/apps.json — merged on top of the built-ins above.
try:
    if config.APPS_FILE.is_file():
        import json as _json
        _custom = _json.loads(config.APPS_FILE.read_text(encoding="utf-8"))
        for _k, _v in (_custom or {}).items():
            _APPS[str(_k).strip().lower()] = _v if isinstance(_v, list) else [str(_v)]
except (ValueError, OSError):
    pass

_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "maps": "https://maps.google.com",
}


def _launch_app(app: str) -> str:
    if not config.ALLOW_LAUNCH:
        return "App launching is disabled. Set JANE_ALLOW_LAUNCH=1 in .env to enable it."
    key = app.strip().lower()
    if key in _SITES:
        webbrowser.open(_SITES[key])
        bus.log(f"Opened {key}", "ok")
        return f"Opened {key}."
    cmd = _APPS.get(key)
    if cmd is None:
        return (f"'{app}' is not on the allow-list. Available: "
                f"{', '.join(sorted(set(_APPS) | set(_SITES)))}.")
    if sys.platform != "win32" and cmd[0] in {"cmd", "notepad.exe", "calc.exe"}:
        return f"'{app}' is Windows-only and this host is {sys.platform}."
    try:
        subprocess.Popen(cmd, shell=False)
    except OSError as exc:
        return f"Couldn't launch {app}: {exc}"
    bus.log(f"Launched {key}", "ok")
    return f"Launched {app}."


def _open_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not config.ALLOW_LAUNCH:
        return "Opening links is disabled. Set JANE_ALLOW_LAUNCH=1 in .env to enable it."
    webbrowser.open(url)
    bus.log(f"Opened {url}", "ok")
    return f"Opened {url}."


def _set_timer(seconds: int, label: str = "timer") -> str:
    seconds = max(1, min(int(seconds), 24 * 3600))

    def fire() -> None:
        bus.log(f"Timer elapsed: {label}", "warn")
        speech.say(f"That's your {label}. Time's up.")
        bus.publish("transcript", {"who": "JANE", "text": f"That's your {label}. Time's up."})

    threading.Timer(seconds, fire).start()
    bus.log(f"Timer armed: {label} — {seconds}s", "info")
    return f"Timer set for {seconds} seconds ({label})."


# --- tool schemas -------------------------------------------------------
# Order is fixed: the tool list is part of the cached prefix, so it must be
# byte-identical between requests.
SCHEMAS: list[dict] = [
    {
        "name": "get_weather",
        "description": "Current weather conditions for a city. Omit the city for the "
                       "user's own location.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name."}},
        },
    },
    {
        "name": "get_headlines",
        "description": "Latest news headlines for a topic, place, or person. Use this "
                       "for 'what's happening' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Search topic. Defaults to the user's city."},
                "limit": {"type": "integer", "description": "How many headlines, 1-8."},
            },
        },
    },
    {
        "name": "get_system_status",
        "description": "CPU, memory, disk, GPU and network usage of this machine.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "network_latency",
        "description": "Round-trip latency from this machine to each region on the network map.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ledger_list",
        "description": "Read the ledger — the user's open and completed case items.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ledger_add",
        "description": "Add an item to the ledger. Use for 'remind me to', 'add to my list', tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "ledger_complete",
        "description": "Tick an item off the ledger. Match on any part of its text.",
        "input_schema": {
            "type": "object",
            "properties": {"item": {"type": "string", "description": "Text fragment or id."}},
            "required": ["item"],
        },
    },
    {
        "name": "ledger_remove",
        "description": "Delete an item from the ledger entirely.",
        "input_schema": {
            "type": "object",
            "properties": {"item": {"type": "string"}},
            "required": ["item"],
        },
    },
    {
        "name": "remember",
        "description": "Store a durable fact about the user (name, preferences, ongoing work). "
                       "Only for things worth recalling in future sessions.",
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
    {
        "name": "forget",
        "description": "Delete remembered facts matching a phrase.",
        "input_schema": {
            "type": "object",
            "properties": {"about": {"type": "string"}},
            "required": ["about"],
        },
    },
    {
        "name": "launch_app",
        "description": "Open a desktop application or a known website on the user's machine. "
                       "Only allow-listed names work; call it and read the error if unsure.",
        "input_schema": {
            "type": "object",
            "properties": {"app": {"type": "string", "description": "e.g. notepad, spotify, youtube."}},
            "required": ["app"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a specific web address in the user's browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "set_timer",
        "description": "Set a countdown timer. Jane announces it out loud when it elapses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer"},
                "label": {"type": "string"},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "compose_email",
        "description": "Write and stage an email, ready to send. This does NOT send it — "
                       "it drafts it and reads it back. Always compose first, tell the user "
                       "what it says, and wait for them to confirm before sending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "The full message text."},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "send_email",
        "description": "Send the email that compose_email last staged. Call this ONLY after "
                       "the user has explicitly confirmed they want it sent. Takes no arguments; "
                       "it sends exactly the draft you already read back to them.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "discard_email",
        "description": "Throw away the staged email draft without sending it.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "whatsapp_message",
        "description": "Send a WhatsApp message via the desktop app to a saved contact name "
                       "or a phone number (with country code). When acting on the user's behalf, "
                       "first ask what they want to say, then confirm the wording before sending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Contact name or phone number."},
                "text": {"type": "string", "description": "The message to send."},
            },
            "required": ["to", "text"],
        },
    },
    {
        "name": "play_game",
        "description": "Launch a game on the user's machine by name (e.g. valorant, dota). "
                       "Opens it so they're queued up and ready to play.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the files and folders in a directory of the user's workspace. "
                       "Paths are relative to the workspace root. Use '.' for the root. "
                       "Call this first to find your way around before reading or writing.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Folder path, e.g. '.' or 'patrick jane ai/web'."}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the user's workspace so you can see its "
                       "current contents before changing it.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create a file or replace its entire contents. For a change to an "
                       "existing file, read it first, then write back the full new version. "
                       "Creates parent folders as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string", "description": "The complete file contents."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "append_file",
        "description": "Add text to the end of a file (creating it if needed) without "
                       "touching what's already there. Use for 'add this line to that file'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string", "description": "Text to append."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "find_files",
        "description": "Search the user's machine for files or folders whose name matches "
                       "a query, recursively. Use for 'find the folder on my C drive that has…' "
                       "or 'where is that file'. Read-only: it locates things, it changes nothing. "
                       "Searches under Jane's read root (the home folder, or the whole drive if "
                       "widened). Give a narrower 'root' when you already know roughly where to look.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name fragment to match, e.g. 'invoices' or '.pdf'."},
                "root": {"type": "string", "description": "Where to start, e.g. '.' or an absolute folder. Default: read root."},
                "limit": {"type": "integer", "description": "Max matches to return, 1-200."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the workspace and read its output. Only works "
                       "if the user has turned shell access on; otherwise it returns a notice.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    # Anthropic-hosted: runs on Anthropic's side, no local execution needed.
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 4},
]


# --- dispatch -----------------------------------------------------------
def _ledger_changed() -> None:
    bus.publish("ledger", ledger.all_items())


def run(name: str, args: dict) -> str:
    """Execute one local tool call and return a plain-text result for the model."""
    bus.log(f"Tool: {name}", "tool")

    if name == "get_weather":
        data = weather.fetch(args.get("city"))
        if args.get("city") in (None, "") and data.get("ok"):
            bus.publish("weather", data)
        return weather.summary(args.get("city"))

    if name == "get_headlines":
        limit = max(1, min(int(args.get("limit", 3)), 8))
        topic = args.get("topic")
        items = news.fetch(topic, limit)
        if topic in (None, "") and items:
            bus.publish("news", items)
        return news.summary(topic, limit)

    if name == "get_system_status":
        return metrics.summary()

    if name == "network_latency":
        netmap.measure()
        bus.publish("netmap", netmap.latest())
        return netmap.summary()

    if name == "ledger_list":
        return ledger.summary()

    if name == "ledger_add":
        entry = ledger.add(args["text"])
        _ledger_changed()
        return f"Added to the ledger: {entry['text']}"

    if name == "ledger_complete":
        hit = ledger.set_done(args["item"], True)
        _ledger_changed()
        return f"Ticked off: {hit['text']}" if hit else f"No ledger item matches '{args['item']}'."

    if name == "ledger_remove":
        hit = ledger.remove(args["item"])
        _ledger_changed()
        return f"Removed: {hit['text']}" if hit else f"No ledger item matches '{args['item']}'."

    if name == "remember":
        entry = memory.remember(args["fact"])
        bus.publish("memory", memory.all_notes())
        return "Already knew that." if entry.get("duplicate") else f"Noted: {entry['fact']}"

    if name == "forget":
        n = memory.forget(args["about"])
        bus.publish("memory", memory.all_notes())
        return f"Forgot {n} note(s)." if n else "Nothing matched."

    if name == "launch_app":
        return _launch_app(args["app"])

    if name == "open_url":
        return _open_url(args["url"])

    if name == "set_timer":
        return _set_timer(args["seconds"], args.get("label", "timer"))

    if name == "compose_email":
        return mailer.compose(args["to"], args.get("subject", ""), args.get("body", ""))

    if name == "send_email":
        return mailer.send()

    if name == "discard_email":
        return mailer.discard()

    if name == "whatsapp_message":
        return desktop.whatsapp_message(args["to"], args["text"])

    if name == "play_game":
        return desktop.play_game(args["name"])

    if name == "list_dir":
        return workspace.list_dir(args.get("path", "."))

    if name == "read_file":
        return workspace.read_file(args["path"])

    if name == "write_file":
        return workspace.write_file(args["path"], args.get("content", ""))

    if name == "append_file":
        return workspace.append_file(args["path"], args.get("content", ""))

    if name == "find_files":
        return workspace.find(args["query"], args.get("root", "."), args.get("limit", 40))

    if name == "run_command":
        return workspace.run_command(args["command"])

    return f"Unknown tool: {name}"
