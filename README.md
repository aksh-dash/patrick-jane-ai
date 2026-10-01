# J.A.N.E.

A voice assistant that thinks, talks, and deflects like Patrick Jane.

Black screen, red accents, real telemetry. You talk; it answers out loud, in
character, in one or two sentences, and it uses tools instead of guessing.

```
J.A.N.E.                                              MODEL claude-opus-5
┌────────────────┐  ┌──────────────────────────┐  ┌──────────────────────┐
│ SYSTEM STATUS  │  │                          │  │ CASE CALENDAR        │
│ RED JOHN       │  │        ( sonar )         │  │ HEADLINES / LEDGER   │
│ ENCRYPTION     │  │                          │  │ ENVIRONMENT          │
│ SYSTEM LOG     │  │  TRANSCRIPT — LIVE       │  │ NETWORK MAP          │
└────────────────┘  └──────────────────────────┘  └──────────────────────┘
  VOICE COMMAND  ▏|||▕ ▁▂▃▅▂▇▃▁▂▅▃▂▁▃▅▂▁▂▃▅▇▃▁ ▏|||▕
```

## Setup

Two dependencies. That's the whole install.

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and put your key in it:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Then, from this folder:

```bash
python -m jane
```

A browser opens at `http://127.0.0.1:8765`. On Windows you can double-click
`start.bat` instead — it copies `.env`, installs what's missing, and launches.

**Open it through the server, not by double-clicking `web/index.html`.** As a
`file://` page the browser blocks ES modules and there is no API to talk to, so
you get an unstyled wall of text.

## Using it

| Action | How |
| --- | --- |
| Talk | Click **MIC**, or press **Space** |
| Type | Press **/**, or just start typing in the box |
| Cut Jane off mid-sentence | **Esc** |
| Close out a ledger item | Click it |
| Arm the camera | Click the Red John panel |

Chrome or Edge — speech recognition is a Chromium API. In Firefox and Safari
the microphone button falls back to the text box and everything else works.

You can address it directly ("Jane, what's the weather") or not; the wake word
is stripped either way.

## What it can do

Jane carries a toolbox and decides on her own when to reach for one — she acts
only when you ask, and never on her own between questions:

- `get_weather`, `get_headlines` — Open-Meteo and Google News, no keys needed
- `get_system_status`, `network_latency` — this machine, right now
- `ledger_list` / `ledger_add` / `ledger_complete` / `ledger_remove` — the board on the right
- `remember` / `forget` — durable notes across restarts, in `data/memory.json`
- `list_dir` / `read_file` / `find_files` — read and search across your machine
  (home folder by default, the whole drive if you widen `JANE_READ_ROOT`)
- `write_file` / `append_file` — create and edit files inside the workspace folder
- `run_command` — shell access, **off by default** (`JANE_ALLOW_SHELL=1`)
- `launch_app`, `open_url`, `play_game` — a fixed allow-list of apps, sites and games
- `compose_email` / `send_email`, `whatsapp_message` — she drafts and reads back,
  and only sends after you say yes
- `set_timer`
- `web_search` — Anthropic's server-side search, for anything the rest can't answer

**The line:** reading and looking are free — she just does them and tells you
what she found. Anything that changes something or leaves the machine (writing,
deleting, installing, sending, logging in) she states first and waits for a
clear yes. And everything she reads is treated as evidence, never as orders.

## Voice

Jane speaks every reply out loud. Three backends, chosen by `JANE_TTS`:

- `auto` *(default)* — a natural neural voice via `edge-tts` if it's installed,
  otherwise the browser's built-in speech. No key, no cost.
- `eleven` — [ElevenLabs](https://elevenlabs.io) cloud voices. Set
  `ELEVENLABS_API_KEY` and `JANE_ELEVEN_VOICE`. Note: a free ElevenLabs plan can
  only use the **premade** voices via the API; Voice Library voices need a paid plan.
- `browser` — always the browser voice.

## Honest notes

Three panels could easily lie to you. They don't:

- **RED JOHN — TRACKING** is *presence* detection, not identity. It uses the
  browser's `FaceDetector` where it exists and a frame-difference score where it
  doesn't. It recognises nobody, so "NO MATCH FOUND" is a fact rather than
  suspense. The camera is off until you click the panel, and no frame ever
  leaves your machine — only a boolean does.
- **GPU_USR** reads `nvidia-smi`. On a machine without it the row says `N/A`
  instead of inventing a number.
- **NETWORK MAP** is four real TCP handshakes to AWS regional endpoints. When a
  node says `NO LINK`, the connection genuinely failed.

`ENCRYPTION STATUS` describes the uplink: `MAXIMUM / SECURE` when there's a key
and TLS to the API, `LOCAL ONLY / OFFLINE` when there isn't. The KEY line is a
SHA-256 fingerprint of a per-boot random session key — it's a real hash of a
real value, and it decrypts nothing.

## SF Pro

The UI asks for SF Pro and SF Mono, which Apple doesn't allow anyone to
redistribute. So `web/css/fonts.css` tries `local()` first and falls back:

- **macOS** — pixel-exact immediately, the fonts are already installed
- **Windows** — download the two families from
  [developer.apple.com/fonts](https://developer.apple.com/fonts/) and either
  install them or drop the `.otf` files into `web/fonts/`
  (see [web/fonts/README.md](web/fonts/README.md) for the filenames)
- **Neither** — Segoe UI Variable Display and Cascadia Mono, which are metrically
  close enough that the layout doesn't shift

## Layout

```
jane/
  __main__.py   banner, browser launch
  server.py     ThreadingHTTPServer + SSE — stdlib only, binds 127.0.0.1
  brain.py      the streaming Messages API loop, tools, prompt caching
  persona.py    who Jane is
  tools.py      the fourteen tools
  metrics.py    psutil + nvidia-smi
  weather.py    Open-Meteo        news.py     Google News RSS
  netmap.py     TCP latency       ledger.py   the board
  memory.py     durable notes     logbus.py   pub/sub for the SSE fan-out
web/
  index.html    css/    js/{app,panels,radar,waveform,voice,spark,bus}.js
data/           ledger.json, memory.json — created on first run
```

No framework, front or back. The server is `http.server`; live data arrives over
one Server-Sent Events channel.

## Configuration

Everything in `.env` is optional except the key.

| Variable | Default | |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | required for thinking; without it the dashboard still runs |
| `JANE_MODEL` | `claude-opus-5` | |
| `JANE_EFFORT` | `medium` | `low` is snappier, `high` is sharper |
| `JANE_PORT` | `8765` | |
| `JANE_CITY` | `Pune` | drives ENVIRONMENT and HEADLINES |
| `JANE_COUNTRY` | `IN` | news locale |
| `JANE_ALLOW_LAUNCH` | `1` | set `0` to disable `launch_app` and `open_url` |
| `JANE_ALLOW_FILES` | `1` | read / write / search tools |
| `JANE_WORKSPACE` | Desktop | the one folder tree Jane may **write** to |
| `JANE_READ_ROOT` | home folder | how far Jane may **read & search**; set `C:\` for the whole drive |
| `JANE_ALLOW_SHELL` | `0` | set `1` to let Jane run shell commands |
| `JANE_TTS` | `auto` | `auto`, `eleven`, `edge`, or `browser` |
| `ELEVENLABS_API_KEY` | — | required when `JANE_TTS=eleven` |
| `JANE_ELEVEN_VOICE` | — | ElevenLabs voice id |
