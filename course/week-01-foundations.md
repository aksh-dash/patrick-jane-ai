# Week 1 — Foundations & Architecture

> Goal: understand *what Jane is* as a system, get your machine set up, and write your very first web server. By Friday you'll have a page served from Python that says hello.

---

## Objectives

- Explain, in one paragraph, how every piece of Jane fits together.
- Know why the project uses the Python standard library instead of a web framework.
- Have a working Python environment, the repo, and an editor.
- Understand the client/server model and the HTTP request/response cycle.
- Write and run a minimal HTTP server.

---

## 1. The big picture

Jane has two halves that talk over your own machine's network (`127.0.0.1`, "localhost" — a loopback address that never leaves your computer):

```
   BROWSER (the face)                 PYTHON (the mind)
   web/  — HTML, CSS, JS              jane/ — server, brain, tools
   ┌─────────────────────┐           ┌──────────────────────────┐
   │ microphone → text    │  POST     │ /api/say → brain.ask()    │
   │ speakers  ← text/audio│ ────────▶ │   → Anthropic API         │
   │ the cinematic UI      │  SSE      │   → tools (files, email…) │
   │                       │ ◀──────── │ /api/stream (live events) │
   └─────────────────────┘           └──────────────────────────┘
```

1. You **speak**. The browser turns speech into text (Week 6).
2. The browser **POSTs** that text to the Python server (Week 2).
3. The server hands it to the **brain**, which asks the Anthropic model what to say and do (Week 4), possibly calling **tools** (Week 5).
4. As the model writes, sentences stream back to the browser over a live **Server-Sent Events** channel (Week 3) and are **spoken aloud** (Week 6).

Everything else — weather, news, system stats, the ledger, memory, email, desktop control — is a tool the brain can reach for.

That's the whole system. Eight weeks from now every arrow in that diagram will be code you understand.

## 2. Why no framework?

Most tutorials reach for Flask or FastAPI on line one. Jane deliberately doesn't. Two reasons:

- **You learn what the framework hides.** Routing, headers, status codes, streaming, MIME types — a framework does these for you, so you never learn them. We do them by hand once. After that, every framework makes sense because you know what it's automating.
- **Zero install, zero magic.** Jane's server needs nothing but Python itself. `pip install` is only for two optional extras (`anthropic`, `psutil`). That keeps the project small and the moving parts visible.

This is a teaching choice, not a production recommendation. In a real high-traffic service you'd use a framework and a real web server. For a single-user local assistant, stdlib is perfect *and* educational.

## 3. Set up your environment

You need **Python 3.10+** (Jane uses `str | None` type syntax, which needs 3.10). Check:

```bash
python --version
```

Create an isolated environment so the project's packages don't pollute your system:

```bash
cd "PATRICK JANE AI"
python -m venv .venv
```

Activate it (Windows, the platform Jane targets):

```bash
.venv\Scripts\activate
```

On macOS/Linux it's `source .venv/bin/activate`. Then install the two real dependencies:

```bash
pip install -r requirements.txt
```

Open `requirements.txt` and read it. Notice `edge-tts` is commented out — it's *optional* (Week 6 explains why Jane works without it). This is your first lesson in **graceful degradation**: a good program does something sensible when an optional piece is missing, instead of crashing.

## 4. The client/server model & HTTP

A **server** is just a program that waits for requests and answers them. A **client** (your browser) sends requests. The language they speak is **HTTP**.

An HTTP request is plain text:

```
GET /api/health HTTP/1.1
Host: 127.0.0.1:8765
```

- **Method** (`GET`, `POST`, …) — what you want done. `GET` = "give me this." `POST` = "here's some data, do something."
- **Path** (`/api/health`) — which resource.
- **Headers** — metadata (who I am, what formats I accept).

The response comes back with a **status code** (200 = OK, 404 = not found, 500 = server broke), headers (like `Content-Type: application/json`), and a body.

That request/response dance is the entire foundation of the web, and of Jane's front-to-back communication. Memorise the four codes above; you'll use them all in Week 2.

## 5. Lab — your first server

Create `lab1.py` anywhere and run `python lab1.py`, then visit `http://127.0.0.1:8000` in your browser.

```python
from http.server import BaseHTTPRequestHandler, HTTPServer

class Hello(BaseHTTPRequestHandler):
    def do_GET(self):                       # called for every GET request
        body = b"<h1>Hello. Nothing escapes notice.</h1>"
        self.send_response(200)             # status line
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()                  # blank line = headers done
        self.wfile.write(body)              # the body

HTTPServer(("127.0.0.1", 8000), Hello).serve_forever()
```

Every line here reappears in Jane's real `server.py`. You just wrote the seed of the whole backend.

**Stretch:** make it answer `GET /api/health` with `{"ok": true}` and the right `Content-Type`. Peek at `jane/server.py`'s `do_GET` if you get stuck — you'll see the same shape.

## 6. Read Jane's map

Open these three files and just *skim* them — don't try to understand every line yet. You're building a mental index.

- `jane/config.py` — all the knobs (read Week 1's relevance: `_load_dotenv`, the flags).
- `jane/server.py` — the server you'll master in Week 2.
- `web/index.html` — the page the browser loads first.

Notice `config.py` reads settings from a `.env` file and the environment. Copy `.env.example` to `.env` now; we'll fill it in over the coming weeks.

---

## Checkpoint

1. Draw the two-halves diagram from memory. What travels over POST? What travels over SSE?
2. Why does Jane avoid Flask? Give the two reasons in your own words.
3. What are the four HTTP status codes you memorised, and what does each mean?
4. In your `lab1.py`, why must `Content-Length` match the body's length? (Hint: how does the browser know the response is finished?)

When those feel obvious, go to → [Week 2](week-02-web-server.md).

