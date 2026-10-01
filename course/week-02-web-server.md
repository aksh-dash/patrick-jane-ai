# Week 2 — The Web Server from Scratch

> Goal: turn last week's toy server into Jane's real one — routing, static files, a JSON API, path-traversal safety, MIME types, and byte-range streaming for media. Everything in `jane/server.py`.

---

## Objectives

- Subclass `BaseHTTPRequestHandler` and route requests by method and path.
- Serve files from disk safely, defending against path-traversal attacks.
- Send and receive JSON.
- Understand MIME types and why they matter.
- Serve media with HTTP **range requests** so `<video>` can seek and loop.

---

## 1. The handler class

Python's `http.server` gives you a base class. You subclass it and define `do_GET`, `do_POST`, etc. The server creates **one handler instance per request** and calls the method matching the HTTP verb.

Jane's handler starts like this (`jane/server.py`):

```python
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # enables keep-alive & streaming
    server_version = f"JANE/{config.VERSION}"

    def log_message(self, fmt, *args):     # silence the default noisy logging
        pass
```

Setting `protocol_version = "HTTP/1.1"` matters: HTTP/1.0 closes the connection after each response, which would break the live event stream in Week 3. 1.1 keeps connections alive.

## 2. Helpers: sending bytes and JSON

Notice Jane never repeats the send-response boilerplate. It's factored into `_send` and `_json`:

```python
def _send(self, code, body, ctype, extra=None):
    extra = extra or {}
    self.send_response(code)
    self.send_header("Content-Type", ctype)
    self.send_header("Content-Length", str(len(body)))
    if "Cache-Control" not in extra:
        self.send_header("Cache-Control", "no-store")
    for k, v in extra.items():
        self.send_header(k, v)
    self.end_headers()
    if self.command != "HEAD":            # HEAD = headers only, no body
        self.wfile.write(body)

def _json(self, payload, code=200):
    self._send(code, json.dumps(payload, default=str).encode("utf-8"),
               "application/json; charset=utf-8")
```

Two ideas to carry forward:

- **Factor out repetition.** Every response needs a status, `Content-Type`, and `Content-Length`. Write it once.
- **`default=str`** in `json.dumps` means "if you hit something you can't serialise (like a datetime), call `str()` on it." A small robustness trick.

## 3. Routing

Routing is just: look at the path, decide what to do. Jane's `do_GET`:

```python
def do_GET(self):
    path = self.path.split("?")[0]        # drop the query string
    if path == "/api/stream":
        self._serve_stream()              # SSE — Week 3
    elif path == "/api/bootstrap":
        self._json(bootstrap())           # everything the UI needs on load
    elif path == "/api/health":
        self._json({"ok": True, "uptime": int(time.time() - _START)})
    elif path.startswith("/api/tts/"):
        self._serve_tts(path)             # neural audio — Week 6
    else:
        self._serve_static(path)          # fall through to files on disk
```

No framework, no decorators — an `if`/`elif` ladder. The `else` branch is the key pattern: **anything that isn't an API route is treated as a request for a file** (a stylesheet, a script, the HTML page).

## 4. Serving static files — safely

This is the most security-sensitive code in the server. When a browser asks for `/js/app.js`, you map that to a file on disk and send it back. The danger: what if it asks for `/../../../../etc/passwd`? Naively joining paths would let a caller escape your web folder and read anything. This is a **path-traversal attack**.

Jane's defence (`_serve_static`):

```python
def _serve_static(self, path):
    rel = "index.html" if path in ("/", "") else path.lstrip("/")
    target = (config.WEB_DIR / rel).resolve()      # resolve() collapses ../
    try:
        target.relative_to(config.WEB_DIR.resolve())  # must stay inside WEB_DIR
    except ValueError:
        self._json({"error": "forbidden"}, 403)     # tried to escape
        return
    if not target.is_file():
        self._json({"error": "not found", "path": rel}, 404)
        return
    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    ...
    self._send(200, target.read_bytes(), ctype)
```

The trick: `.resolve()` turns `web/../../secret` into a real absolute path, and `relative_to()` **raises `ValueError` if the result isn't inside `WEB_DIR`**. Escape attempts become a clean 403. Learn this pattern — you'll use it any time user input picks a file.

## 5. MIME types

A browser needs to know *what kind* of bytes it's getting. A `.js` file sent as `text/plain` won't run; a `.woff2` font sent wrong won't load. That label is the **MIME type**, in the `Content-Type` header.

`mimetypes.guess_type` maps extensions to types, but its defaults are incomplete, so Jane teaches it a few at the top of `server.py`:

```python
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("video/mp4", ".mp4")
```

And for text types it appends `; charset=utf-8` so accented characters and em-dashes render correctly.

## 6. Range requests (media that can seek)

A `<video>` element doesn't download the whole file — it asks for byte ranges as you scrub the timeline (`Range: bytes=2000000-`). If the server ignores that and always sends the whole file from the start, seeking and looping stutter.

Jane's `_serve_media` parses the `Range` header, sends back **`206 Partial Content`** with a `Content-Range` header and just the requested slice, and handles the "unsatisfiable range" case with `416`. Read it in `server.py` — you don't need to memorise it, but understand *why* it exists: **streaming media is a negotiation, not a single download.**

## 7. Receiving data: reading JSON from a POST

`GET` has no body. `POST` does. To read it you must know its length first:

```python
def _read_json(self):
    length = int(self.headers.get("Content-Length") or 0)
    if not length:
        return {}
    try:
        return json.loads(self.rfile.read(length).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
```

`self.rfile` is the incoming byte stream; you read exactly `Content-Length` bytes. Reading more would hang; reading fewer would leave garbage for the next request. Wrapping the parse in try/except means malformed input yields `{}` instead of a crash — **never trust the client**.

## 8. Lab — build a mini static server

Write a server that:
1. Serves files from a `public/` folder with correct MIME types.
2. Blocks path traversal (test it: request `/../server.py` and confirm you get 403).
3. Answers `GET /api/time` with `{"now": "..."}`.
4. Answers `POST /api/echo` by returning the JSON body you sent it.

Then compare every method against `jane/server.py`. You should be able to point to the line in Jane that does each thing yours does.

---

## Checkpoint

1. Why is `protocol_version = "HTTP/1.1"` necessary for Jane specifically?
2. Explain the path-traversal defence. What does `.resolve()` do, and what does `relative_to()` raise?
3. What breaks if you serve `app.js` with `Content-Type: text/plain`?
4. Why must you read exactly `Content-Length` bytes from `self.rfile`, no more and no less?
5. What status code says "here's part of the file you asked for"?

→ [Week 3](week-03-realtime-sse.md)

