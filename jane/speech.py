"""Jane's voice, server side.

By default she speaks through the browser's built-in speech (no dependency).
If the `edge-tts` package is installed, she instead speaks in a natural neural
voice synthesised here and streamed to the page as audio — smoother, warmer,
and guaranteed to be a single voice because exactly one audio file is produced
per sentence and sent to exactly one client. With `JANE_TTS=eleven` she uses
ElevenLabs' cloud voices over their HTTP API (no extra package — plain urllib).

`say(text)` is the one entry point. It decides which backend to use and never
emits both, so the browser voice and any neural voice can't talk over one
another. Every neural path publishes the same `voice` event with an mp3 URL, so
adding a new provider only means teaching `_render` how to return mp3 bytes.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
import urllib.request
from collections import OrderedDict
from queue import Queue

from . import config
from .logbus import bus

_CACHE_CAP = 64
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_cache_lock = threading.Lock()
_ids = itertools.count(1)
_jobs: "Queue[tuple[str, str]]" = Queue()

# Decide the backend once, at import: "eleven", "edge", or "browser".
# edge-tts is optional; if a neural path is wanted but unavailable we say so and
# quietly fall back to the browser voice rather than going mute. "auto" never
# picks ElevenLabs — that's a paid API you opt into with JANE_TTS=eleven.
_edge = None
_backend = "browser"

if config.TTS == "eleven":
    if config.ELEVEN_API_KEY and config.ELEVEN_VOICE_ID:
        _backend = "eleven"
    else:
        bus.log("JANE_TTS=eleven but ELEVENLABS_API_KEY / JANE_ELEVEN_VOICE "
                "is missing; using browser voice", "warn")
elif config.TTS != "browser":
    try:
        import edge_tts  # type: ignore
        _edge = edge_tts
        _backend = "edge"
    except ImportError:
        if config.TTS == "edge":
            bus.log("JANE_TTS=edge but edge-tts isn't installed; using browser voice", "warn")

ENABLED = _backend != "browser"

_ELEVEN_URL = ("https://api.elevenlabs.io/v1/text-to-speech/{vid}"
               "?output_format=mp3_44100_128")


def _store(audio: bytes) -> str:
    token = f"{next(_ids)}"
    with _cache_lock:
        _cache[token] = audio
        while len(_cache) > _CACHE_CAP:
            _cache.popitem(last=False)
    return token


def get(token: str) -> bytes | None:
    with _cache_lock:
        return _cache.get(token)


async def _synth_edge(text: str) -> bytes:
    comm = _edge.Communicate(text, voice=config.TTS_VOICE,
                             rate=config.TTS_RATE, pitch=config.TTS_PITCH)
    audio = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return bytes(audio)


def _synth_eleven(text: str) -> bytes:
    """One sentence → mp3 bytes from ElevenLabs, over stdlib urllib."""
    url = _ELEVEN_URL.format(vid=config.ELEVEN_VOICE_ID)
    payload = json.dumps({
        "text": text,
        "model_id": config.ELEVEN_MODEL,
        "voice_settings": {
            "stability": 0.4, "similarity_boost": 0.8,
            "style": 0.0, "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "xi-api-key": config.ELEVEN_API_KEY,
        "content-type": "application/json",
        "accept": "audio/mpeg",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _worker() -> None:
    """Synthesise queued sentences in order, publishing one audio event each."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        _seq, text = _jobs.get()
        try:
            if _backend == "eleven":
                audio = _synth_eleven(text)
            else:
                audio = loop.run_until_complete(_synth_edge(text))
            if not audio:
                raise RuntimeError("empty audio")
            token = _store(audio)
            bus.publish("voice", {"url": f"/api/tts/{token}.mp3"})
        except Exception as exc:  # a bad synth must not silence Jane
            bus.log(f"Neural voice fell back to browser: {exc}", "warn")
            bus.publish("speak", {"text": text})
        finally:
            _jobs.task_done()


if ENABLED:
    threading.Thread(target=_worker, daemon=True, name="tts").start()


def say(text: str) -> None:
    """Speak one sentence. Neural if configured, browser otherwise — never both."""
    text = (text or "").strip()
    if not text:
        return
    if ENABLED:
        _jobs.put((next(_ids), text))
    else:
        bus.publish("speak", {"text": text})
