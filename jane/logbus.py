"""A tiny pub/sub bus. Publishers are worker threads, subscribers are SSE clients."""
from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from typing import Any

_MAX_LOG = 200


class Bus:
    def __init__(self) -> None:
        # Ordered: the most recently connected client is the designated
        # "speaker" — the only one that receives `speak` events, so audio
        # never doubles no matter how many windows, tabs, profiles or
        # browsers are pointed at Jane. Everything else goes to everyone.
        self._subs: list[queue.Queue] = []
        self._speaker: queue.Queue | None = None
        self._lock = threading.Lock()
        self.log_lines: deque[dict] = deque(maxlen=_MAX_LOG)

    # -- subscriber side -------------------------------------------------
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subs.append(q)
            self._speaker = q          # newest window takes the voice
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)
            if self._speaker is q:
                # Hand the voice to whoever's left (newest first), if anyone.
                self._speaker = self._subs[-1] if self._subs else None

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._subs)

    # -- publisher side --------------------------------------------------
    def publish(self, event: str, data: Any) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        with self._lock:
            # Spoken audio (text or synthesised) goes to exactly one client so
            # no window doubles the voice; all else is broadcast.
            voice_events = event in ("speak", "voice")
            targets = [self._speaker] if voice_events and self._speaker else self._subs
            dead = []
            for q in targets:
                if q is None:
                    continue
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                if q in self._subs:
                    self._subs.remove(q)
                if self._speaker is q:
                    self._speaker = self._subs[-1] if self._subs else None

    def log(self, message: str, level: str = "info") -> None:
        line = {"t": time.strftime("%H:%M:%S"), "msg": message, "level": level}
        self.log_lines.append(line)
        self.publish("log", line)


bus = Bus()
