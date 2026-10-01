"""Keyless headlines via the Google News RSS feed."""
from __future__ import annotations

import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config

_TTL = 900  # 15 minutes
_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}


def _feed_url(topic: str) -> str:
    lang = "en-IN" if config.COUNTRY == "IN" else "en-US"
    ceid = f"{config.COUNTRY}:en"
    q = urllib.parse.urlencode({"q": topic, "hl": lang, "gl": config.COUNTRY, "ceid": ceid})
    return f"https://news.google.com/rss/search?{q}"


def fetch(topic: str | None = None, limit: int = 3) -> list[dict]:
    """Latest headlines for a topic. Defaults to the configured city."""
    topic = (topic or config.CITY).strip()
    key = f"{topic}|{limit}"

    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]

    req = urllib.request.Request(_feed_url(topic), headers={"User-Agent": "JANE/7.2"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []

    out: list[dict] = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        # Some feeds suffix the outlet onto the title; drop the duplicate.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        out.append({
            "title": title,
            "source": source.upper(),
            "link": (item.findtext("link") or "").strip(),
            "date": (item.findtext("pubDate") or "").strip(),
        })

    with _lock:
        _cache[key] = (time.time(), out)
    return out


def summary(topic: str | None = None, limit: int = 3) -> str:
    items = fetch(topic, limit)
    if not items:
        return "The wire is quiet — nothing came back."
    lines = [f"{i}. {it['title']} ({it['source']})" for i, it in enumerate(items, 1)]
    return "\n".join(lines)
