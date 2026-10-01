"""Keyless weather via Open-Meteo (no API key, no account)."""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from . import config

_TTL = 600  # seconds
_lock = threading.Lock()
_cache: dict = {"t": 0.0, "data": None}
_geo_cache: dict[str, tuple[float, float, str]] = {}

# Open-Meteo WMO weather codes -> short label
_CODES = {
    0: "CLEAR", 1: "MAINLY CLEAR", 2: "PARTLY CLOUDY", 3: "OVERCAST",
    45: "FOG", 48: "RIME FOG", 51: "LIGHT DRIZZLE", 53: "DRIZZLE",
    55: "HEAVY DRIZZLE", 56: "FREEZING DRIZZLE", 57: "FREEZING DRIZZLE",
    61: "LIGHT RAIN", 63: "RAIN", 65: "HEAVY RAIN", 66: "FREEZING RAIN",
    67: "FREEZING RAIN", 71: "LIGHT SNOW", 73: "SNOW", 75: "HEAVY SNOW",
    77: "SNOW GRAINS", 80: "RAIN SHOWERS", 81: "RAIN SHOWERS",
    82: "VIOLENT SHOWERS", 85: "SNOW SHOWERS", 86: "SNOW SHOWERS",
    95: "THUNDERSTORM", 96: "THUNDERSTORM + HAIL", 99: "THUNDERSTORM + HAIL",
}


def _get_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "JANE/7.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(city: str) -> tuple[float, float, str] | None:
    key = city.strip().lower()
    if key in _geo_cache:
        return _geo_cache[key]
    q = urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
    try:
        data = _get_json(f"https://geocoding-api.open-meteo.com/v1/search?{q}")
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    found = (top["latitude"], top["longitude"], top.get("name", city))
    _geo_cache[key] = found
    return found


def fetch(city: str | None = None) -> dict:
    """Current conditions. Cached for 10 minutes for the default city."""
    target = city or config.CITY
    is_default = city is None or target.lower() == config.CITY.lower()

    with _lock:
        if is_default and _cache["data"] and time.time() - _cache["t"] < _TTL:
            return _cache["data"]

    place = geocode(target)
    if place is None:
        return {"ok": False, "city": target, "error": "location not found"}

    lat, lon, name = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,surface_pressure,"
                   "wind_speed_10m,weather_code,apparent_temperature",
        "hourly": "visibility",
        "timezone": "auto", "forecast_days": 1,
    })
    try:
        data = _get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
    except Exception as exc:
        return {"ok": False, "city": name, "error": str(exc)}

    cur = data.get("current", {})
    vis_series = (data.get("hourly") or {}).get("visibility") or []
    visibility_km = round(vis_series[0] / 1000) if vis_series else None

    out = {
        "ok": True,
        "city": name.upper(),
        "temp": round(cur.get("temperature_2m", 0)),
        "feels": round(cur.get("apparent_temperature", 0)),
        "humidity": round(cur.get("relative_humidity_2m", 0)),
        "pressure": round(cur.get("surface_pressure", 0)),
        "wind": round(cur.get("wind_speed_10m", 0)),
        "visibility": visibility_km,
        "condition": _CODES.get(cur.get("weather_code"), "UNKNOWN"),
    }
    if is_default:
        with _lock:
            _cache.update(t=time.time(), data=out)
    return out


def summary(city: str | None = None) -> str:
    w = fetch(city)
    if not w.get("ok"):
        return f"I couldn't read the weather for {w.get('city')}: {w.get('error')}"
    return (f"{w['city']}: {w['temp']} degrees, {w['condition'].lower()}, "
            f"humidity {w['humidity']} percent, wind {w['wind']} km/h")
