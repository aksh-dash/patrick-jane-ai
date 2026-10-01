"""Configuration for J.A.N.E. — read once at import from .env / environment."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _load_dotenv() -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Real environment always wins over the file.
        os.environ.setdefault(key, value)


_load_dotenv()


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
# A real Anthropic key looks like "sk-ant-…" and is long. Treat the placeholder
# from .env.example (or anything obviously not a key) as absent, so Jane says so
# once instead of hammering the API with an invalid key on every utterance.
if "..." in API_KEY or len(API_KEY) < 24:
    API_KEY = ""
MODEL = os.environ.get("JANE_MODEL", "claude-opus-5").strip()
# Optional: point the Anthropic SDK at a compatible gateway instead of
# api.anthropic.com. When set, Jane talks to that host with the same key.
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
EFFORT = os.environ.get("JANE_EFFORT", "medium").strip()
PORT = int(os.environ.get("JANE_PORT", "8765"))
CITY = os.environ.get("JANE_CITY", "Pune").strip()
COUNTRY = os.environ.get("JANE_COUNTRY", "IN").strip().upper()
ALLOW_LAUNCH = _flag("JANE_ALLOW_LAUNCH", "1")

# --- workspace: the one folder tree Jane may read and write ----------------
# She can list, read, write and append files anywhere under WORKSPACE, and
# nowhere else. Default is the user's Desktop, so "go to the patrick jane
# folder and add a line to that file" resolves to something real. Override
# with JANE_WORKSPACE in .env to point her at a different root.
_default_ws = Path.home() / "Desktop"
WORKSPACE = Path(os.environ.get("JANE_WORKSPACE", str(_default_ws))).expanduser()
try:
    WORKSPACE = WORKSPACE.resolve()
except OSError:
    WORKSPACE = _default_ws.resolve()
# File tools on by default (that's the whole point of the desktop assistant).
# Shell execution is a bigger hammer, so it stays off unless explicitly asked for.
ALLOW_FILES = _flag("JANE_ALLOW_FILES", "1")
ALLOW_SHELL = _flag("JANE_ALLOW_SHELL", "0")

# --- read reach: where Jane may LOOK (read + search), as opposed to WRITE -----
# Writing stays penned inside WORKSPACE above. Reading and searching, though, is
# the "eyes on everything" power: by default she may read and search anywhere
# under the user's home folder. Point JANE_READ_ROOT at a drive root (e.g. C:\)
# to widen it to the whole machine, or back at WORKSPACE to lock it down again.
# Reading is still gated by ALLOW_FILES, and this never grants write or execute.
_default_read = Path.home()
READ_ROOT = Path(os.environ.get("JANE_READ_ROOT", str(_default_read))).expanduser()
try:
    READ_ROOT = READ_ROOT.resolve()
except OSError:
    READ_ROOT = _default_read.resolve()

# --- email: compose → read back → send, only on the user's confirmation ----
# Jane may draft freely; she may only *send* what she has read back and been
# told to send. Off until you give her an outbox to send from.
ALLOW_EMAIL = _flag("JANE_ALLOW_EMAIL", "0")
SMTP_HOST = os.environ.get("JANE_SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("JANE_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("JANE_SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("JANE_SMTP_PASS", "").strip()
EMAIL_FROM = os.environ.get("JANE_EMAIL_FROM", "").strip() or SMTP_USER

# --- desktop control: installed apps, WhatsApp, games ----------------------
ALLOW_DESKTOP = _flag("JANE_ALLOW_DESKTOP", "1")
# After the user confirms a message, actually press send (a synthesised Enter
# to the focused WhatsApp window). Off → Jane pre-fills the chat and the user
# hits Enter themselves. On by default: the confirmation already happened.
WHATSAPP_AUTOSEND = _flag("JANE_WHATSAPP_AUTOSEND", "1")
CONTACTS_FILE = DATA_DIR / "contacts.json"
GAMES_FILE = DATA_DIR / "games.json"
APPS_FILE = DATA_DIR / "apps.json"

# --- voice / text-to-speech ------------------------------------------------
# "auto"  → use the natural edge-tts neural voice if the package is installed,
#           otherwise fall back to the browser's built-in speech.
# "edge"  → require edge-tts.   "browser" → always use the browser voice.
# "eleven"→ ElevenLabs cloud voices (needs ELEVENLABS_API_KEY + a voice id).
#           Never chosen by "auto" — it's a paid API, so you opt in explicitly.
TTS = os.environ.get("JANE_TTS", "auto").strip().lower()
TTS_VOICE = os.environ.get("JANE_TTS_VOICE", "en-GB-RyanNeural").strip()
TTS_RATE = os.environ.get("JANE_TTS_RATE", "-4%").strip()      # a touch unhurried
TTS_PITCH = os.environ.get("JANE_TTS_PITCH", "-2Hz").strip()

# ElevenLabs: set JANE_TTS=eleven, drop your key + chosen voice id in .env.
# ELEVENLABS_API_KEY is the conventional name; JANE_ELEVEN_KEY also works.
ELEVEN_API_KEY = (os.environ.get("ELEVENLABS_API_KEY", "")
                  or os.environ.get("JANE_ELEVEN_KEY", "")).strip()
ELEVEN_VOICE_ID = os.environ.get("JANE_ELEVEN_VOICE", "").strip()
ELEVEN_MODEL = os.environ.get("JANE_ELEVEN_MODEL", "eleven_turbo_v2_5").strip()

# Regenerated every boot; only ever shown as a masked fingerprint in the UI.
SESSION_KEY = secrets.token_hex(32)
VERSION = "7.3"

LEDGER_FILE = DATA_DIR / "ledger.json"
MEMORY_FILE = DATA_DIR / "memory.json"
