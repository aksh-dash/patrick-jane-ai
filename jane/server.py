"""The local server: static files, a JSON API, and one SSE channel for live data.

Standard library only — no web framework to install. Binds to 127.0.0.1, so
nothing here is reachable from outside this machine.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, ledger, memory, metrics, netmap, news, persona, speech, weather
from .brain import brain
from .logbus import bus

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("video/mp4", ".mp4")

_START = time.time()


def key_fingerprint() -> str:
    """A stable, non-reversible fingerprint of this boot's session key."""
    return hashlib.sha256(config.SESSION_KEY.encode()).hexdigest()[:24].upper()


def encryption_state() -> dict:
    return {
        "level": "MAXIMUM" if config.API_KEY else "LOCAL ONLY",
        "key": key_fingerprint(),
        "signal": "SECURE" if config.API_KEY else "OFFLINE",
        "transport": "TLS 1.3 → api.anthropic.com" if config.API_KEY else "no uplink",
    }


def bootstrap() -> dict:
    """Everything the UI needs to paint itself on first load."""
    return {
        "version": config.VERSION,
        "model": config.MODEL,
        "city": config.CITY,
        "greeting": persona.greeting(),
        "has_key": bool(config.API_KEY),
        "telemetry": metrics.sample(),
        "weather": weather.fetch(),
        "news": news.fetch(),
        "ledger": ledger.all_items(),
        "memory": memory.all_notes(),
        "netmap": netmap.latest(),
        "encryption": encryption_state(),
        "log": list(bus.log_lines),
        "uptime": int(time.time() - _START),
    }


# --- background workers -------------------------------------------------
def _telemetry_loop() -> None:
    while True:
        try:
            if bus.listeners:
                bus.publish("telemetry", metrics.sample())
        except Exception as exc:
            bus.log(f"Telemetry error: {exc}", "error")
        time.sleep(1.0)


def _slow_loop() -> None:
    """Network-bound refreshes. Staggered so they never all fire together."""
    tick = 0
    while True:
        try:
            if tick % 10 == 0:
                netmap.measure()
                bus.publish("netmap", netmap.latest())
            if tick % 600 == 0:
                bus.publish("weather", weather.fetch())
            if tick % 900 == 0:
                bus.publish("news", news.fetch())
        except Exception as exc:
            bus.log(f"Refresh error: {exc}", "error")
        tick += 10
        time.sleep(10.0)


def start_workers() -> None:
    threading.Thread(target=_telemetry_loop, daemon=True, name="telemetry").start()
    threading.Thread(target=_slow_loop, daemon=True, name="refresh").start()


# --- request handler ----------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"JANE/{config.VERSION}"

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        pass

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        extra = extra or {}
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in extra:
            self.send_header("Cache-Control", "no-store")
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # -- static files ----------------------------------------------------
    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (config.WEB_DIR / rel).resolve()
        try:
            target.relative_to(config.WEB_DIR.resolve())   # no path traversal
        except ValueError:
            self._json({"error": "forbidden"}, 403)
            return
        if not target.is_file():
            self._json({"error": "not found", "path": rel}, 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith(("text/", "application/javascript", "application/json")):
            ctype += "; charset=utf-8"
        # Media needs byte ranges — without them a <video> can't seek or loop cleanly.
        if ctype.startswith(("video/", "audio/")):
            self._serve_media(target, ctype)
            return
        self._send(200, target.read_bytes(), ctype)

    def _serve_media(self, target, ctype: str) -> None:
        """Serve a media file, honouring a single-range Range request."""
        total = target.stat().st_size
        head = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}
        spec = (self.headers.get("Range") or "").strip()

        start, end = 0, total - 1
        partial = spec.startswith("bytes=") and "," not in spec
        if partial:
            first, _, last = spec[6:].partition("-")
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else total - 1
                else:
                    start = max(0, total - int(last))      # suffix range: bytes=-500
            except ValueError:
                partial = False
        end = min(end, total - 1)

        if partial and start > end:
            self._send(416, b"", ctype, {**head, "Content-Range": f"bytes */{total}"})
            return

        with target.open("rb") as fh:
            fh.seek(start)
            body = fh.read(end - start + 1)
        if partial:
            head["Content-Range"] = f"bytes {start}-{end}/{total}"
        self._send(206 if partial else 200, body, ctype, head)

    # -- synthesised voice ----------------------------------------------
    def _serve_tts(self, path: str) -> None:
        """Serve one cached, server-synthesised speech clip by token."""
        token = path.rsplit("/", 1)[-1].split(".")[0]
        audio = speech.get(token)
        if audio is None:
            self._json({"error": "expired"}, 404)
            return
        self._send(200, audio, "audio/mpeg", {"Cache-Control": "no-store"})

    # -- SSE -------------------------------------------------------------
    def _serve_stream(self) -> None:
        q = bus.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        bus.log("Interface attached", "ok")
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    payload = q.get(timeout=15.0)
                except queue.Empty:
                    payload = ": keepalive\n\n"      # keeps proxies and tabs awake
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            bus.unsubscribe(q)

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/stream":
            self._serve_stream()
        elif path == "/api/bootstrap":
            self._json(bootstrap())
        elif path == "/api/health":
            self._json({"ok": True, "uptime": int(time.time() - _START)})
        elif path.startswith("/api/tts/"):
            self._serve_tts(path)
        else:
            self._serve_static(path)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        body = self._read_json()

        if path == "/api/say":
            text = (body.get("text") or "").strip()
            if not text:
                self._json({"error": "empty utterance"}, 400)
                return
            # Answered asynchronously; the reply arrives over /api/stream.
            threading.Thread(target=brain.ask, args=(text,), daemon=True).start()
            self._json({"accepted": True})

        elif path == "/api/reset":
            brain.reset()
            self._json({"ok": True})

        elif path == "/api/vision":
            state = {
                "present": bool(body.get("present")),
                "faces": int(body.get("faces") or 0),
                "method": str(body.get("method") or "unknown"),
                "at": time.time(),
            }
            bus.publish("vision", state)
            self._json({"ok": True})

        elif path == "/api/ledger":
            action = body.get("action")
            try:
                if action == "add":
                    ledger.add(body.get("text", ""))
                elif action == "toggle":
                    item = ledger.set_done(body.get("item", ""), bool(body.get("done", True)))
                    if item is None:
                        self._json({"error": "no match"}, 404)
                        return
                elif action == "remove":
                    ledger.remove(body.get("item", ""))
                else:
                    self._json({"error": "unknown action"}, 400)
                    return
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return
            items = ledger.all_items()
            bus.publish("ledger", items)
            self._json({"ok": True, "ledger": items})

        else:
            self._json({"error": "not found"}, 404)


def serve() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler)
    httpd.daemon_threads = True
    start_workers()
    for line in (
        f"System Boot: JANE v{config.VERSION}",
        "Neural Interface: Online",
        f"Speech Model: {'Loaded' if config.API_KEY else 'No key'}",
        "Encryption: Active",
        "All Systems: Operational",
    ):
        bus.log(line, "boot")
    print(f"  J.A.N.E. v{config.VERSION} listening on http://127.0.0.1:{config.PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Jane: 'Going quiet. Try not to miss me.'")
    finally:
        httpd.server_close()
