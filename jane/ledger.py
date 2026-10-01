"""THE LEDGER — Jane's case to-do list, persisted to data/ledger.json."""
from __future__ import annotations

import json
import threading
import time
import uuid

from . import config

_lock = threading.RLock()

_SEED = [
    "Review Lt. Gordon file",
    "Analyze forensic report",
    "Cross-check witness statements",
]


def _load() -> list[dict]:
    if not config.LEDGER_FILE.exists():
        items = [{"id": uuid.uuid4().hex[:8], "text": t, "done": False, "at": time.time()}
                 for t in _SEED]
        _save(items)
        return items
    try:
        return json.loads(config.LEDGER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    config.LEDGER_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def all_items() -> list[dict]:
    with _lock:
        return _load()


def add(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("empty ledger entry")
    with _lock:
        items = _load()
        entry = {"id": uuid.uuid4().hex[:8], "text": text, "done": False, "at": time.time()}
        items.append(entry)
        _save(items)
    return entry


def _match(items: list[dict], needle: str) -> dict | None:
    needle = needle.strip().lower()
    for it in items:
        if it["id"] == needle:
            return it
    for it in items:
        if needle and needle in it["text"].lower():
            return it
    return None


def set_done(needle: str, done: bool = True) -> dict | None:
    with _lock:
        items = _load()
        target = _match(items, needle)
        if target is None:
            return None
        target["done"] = done
        _save(items)
        return target


def remove(needle: str) -> dict | None:
    with _lock:
        items = _load()
        target = _match(items, needle)
        if target is None:
            return None
        items = [it for it in items if it["id"] != target["id"]]
        _save(items)
        return target


def summary() -> str:
    items = all_items()
    if not items:
        return "The ledger is empty."
    return "\n".join(f"[{'x' if it['done'] else ' '}] {it['text']}" for it in items)
