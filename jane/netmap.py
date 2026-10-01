"""NETWORK MAP — real TCP handshake latency to region-pinned endpoints.

Each node is an AWS regional S3 endpoint, so the number on screen is an honest
round-trip to that part of the world rather than a decorative animation.
"""
from __future__ import annotations

import socket
import threading

NODES = [
    ("N.AMERICA", "s3.us-east-1.amazonaws.com"),
    ("EUROPE", "s3.eu-west-1.amazonaws.com"),
    ("ASIA", "s3.ap-south-1.amazonaws.com"),
    ("SACRAMENTO", "s3.us-west-1.amazonaws.com"),
]

_TIMEOUT = 3.0
_lock = threading.Lock()
_latest: list[dict] = [{"name": name, "ms": None, "host": host} for name, host in NODES]


def _probe(host: str) -> float | None:
    """TCP connect time to :443 in milliseconds, or None if unreachable."""
    import time
    try:
        start = time.perf_counter()
        with socket.create_connection((host, 443), timeout=_TIMEOUT):
            pass
        return round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return None


def measure() -> list[dict]:
    """Probe every node in parallel and return the fresh readings."""
    results: dict[str, float | None] = {}
    threads = []

    def run(name: str, host: str) -> None:
        results[name] = _probe(host)

    for name, host in NODES:
        t = threading.Thread(target=run, args=(name, host), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=_TIMEOUT + 1)

    out = [{"name": name, "host": host, "ms": results.get(name)} for name, host in NODES]
    with _lock:
        _latest[:] = out
    return out


def latest() -> list[dict]:
    with _lock:
        return list(_latest)


def summary() -> str:
    parts = []
    for node in latest():
        parts.append(f"{node['name']} {node['ms']}ms" if node["ms"] is not None
                     else f"{node['name']} unreachable")
    return ", ".join(parts)
