"""Long-term notes Jane keeps about the user, persisted to data/memory.json.

Kept deliberately small: it is injected into every system prompt, so it lives
behind the cache breakpoint and stays cheap.
"""
from __future__ import annotations

import json
import threading
import time

from . import config

_lock = threading.RLock()
_MAX = 40


def _load() -> list[dict]:
    if not config.MEMORY_FILE.exists():
        return []
    try:
        return json.loads(config.MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(notes: list[dict]) -> None:
    config.MEMORY_FILE.write_text(json.dumps(notes, indent=2), encoding="utf-8")


def all_notes() -> list[dict]:
    with _lock:
        return _load()


def remember(fact: str) -> dict:
    fact = fact.strip()
    if not fact:
        raise ValueError("empty note")
    with _lock:
        notes = _load()
        if any(n["fact"].lower() == fact.lower() for n in notes):
            return {"fact": fact, "at": time.time(), "duplicate": True}
        entry = {"fact": fact, "at": time.time()}
        notes.append(entry)
        _save(notes[-_MAX:])
        return entry


def forget(needle: str) -> int:
    needle = needle.strip().lower()
    with _lock:
        notes = _load()
        keep = [n for n in notes if needle not in n["fact"].lower()]
        removed = len(notes) - len(keep)
        if removed:
            _save(keep)
        return removed


def as_prompt_block() -> str:
    notes = all_notes()
    if not notes:
        return "(nothing yet)"
    return "\n".join(f"- {n['fact']}" for n in notes)
