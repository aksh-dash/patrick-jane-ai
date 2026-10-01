# Week 3 — Real-Time: Server-Sent Events & Pub/Sub

> Goal: make the server *push* to the browser without being asked. This is how telemetry, logs, transcripts, and Jane's voice all reach the page live. Files: `jane/logbus.py`, the SSE parts of `jane/server.py`, `web/js/bus.js`, `jane/metrics.py`.

---

## Objectives

- Understand why a normal request/response can't push updates, and what SSE does about it.
- Read the SSE wire format and consume it with `EventSource` in the browser.
- Build a thread-safe **publish/subscribe bus**.
- Understand threads, `queue.Queue`, and why they're used here.
- Grasp Jane's "single-speaker election" so audio never doubles.

---

## 1. The problem: the server can't speak first

Everything in Week 2 was pull: the browser asks, the server answers, done. But Jane needs to *push* — new telemetry every second, a log line when a tool runs, each sentence as the model writes it. The browser didn't ask for those at that moment.

Three ways to solve this:
- **Polling** — the browser asks "anything new?" every second. Wasteful and laggy.
- **WebSockets** — a full two-way socket. Powerful, but overkill when only the *server* needs to push.
- **Server-Sent Events (SSE)** — a single long-lived HTTP response the server keeps writing to. One direction (server→browser), dead simple, built into every browser via `EventSource`.

Jane uses SSE because the traffic is almost entirely one-way. The browser's rare messages to the server go over ordinary POSTs (Week 2).

## 2. The SSE wire format

An SSE stream is just a normal HTTP response with `Content-Type: text/event-stream` that never ends. You write "events" as plain text:

```
event: telemetry
data: {"cpu": 12, "mem": 43}

event: log
data: {"msg": "Tool: get_weather", "level": "tool"}

```

Rules: an `event:` line names the channel, a `data:` line carries the payload (Jane always sends JSON there), and a **blank line terminates each event**. That's the entire protocol.

## 3. Consuming it in the browser

The browser side is tiny (`web/js/bus.js`):

```js
const source = new EventSource('/api/stream');
source.addEventListener('telemetry', (e) => {
  const data = JSON.parse(e.data);
  // update the UI...
});
```

`EventSource` also **reconnects automatically** if the connection drops — you get that for free, which is why Jane's `bus.js` can expose a simple `on(event, fn)` and not worry about reconnection logic itself.

## 4. Serving the stream

On the server, `_serve_stream` in `server.py` sends the SSE headers, then loops forever pulling from a queue and writing to the client:

```python
def _serve_stream(self):
    q = bus.subscribe()                    # get my own mailbox
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
    self.send_header("Cache-Control", "no-cache, no-transform")
    self.send_header("Connection", "keep-alive")
    self.end_headers()
    try:
        self.wfile.write(b": connected\n\n")   # a comment line; primes the stream
        self.wfile.flush()
        while True:
            try:
                payload = q.get(timeout=15.0)  # block until there's an event
            except queue.Empty:
                payload = ": keepalive\n\n"     # no news in 15s → nudge the pipe
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass                                   # the tab closed; that's fine
    finally:
        bus.unsubscribe(q)                     # always clean up
```

Two subtleties:

- **`flush()` after every write.** Without it Python buffers the output and the browser sees nothing until the buffer fills. For a live stream you must push each event out immediately.
- **The 15-second keepalive.** Proxies and browsers hang up "idle" connections. Sending a `:` comment line (SSE ignores comments) every 15s keeps the pipe warm without sending a real event.

## 5. Threads: why, and the danger

Here's the problem this raises. That `while True` loop **never returns** — it's parked, waiting for events, for as long as the tab is open. If the server handled one request at a time, that single streaming client would freeze the entire server.

The fix is `ThreadingHTTPServer` (in `serve()`): each request runs on its **own thread**, so a parked stream doesn't block new requests.

```python
httpd = ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler)
httpd.daemon_threads = True     # threads die when the program exits
```

Threads let many things happen "at once," but they introduce a hazard: if two threads touch the same data simultaneously, you get corruption. Jane has worker threads *publishing* events while stream threads *subscribe* and *unsubscribe*. They share one list of subscribers. That shared list must be protected — which is the whole point of the bus.

## 6. The pub/sub bus

`jane/logbus.py` is the heart of Jane's real-time layer. A **publisher** (any worker thread) calls `bus.publish(event, data)`; every **subscriber** (each open browser tab) receives it. Subscribers are `queue.Queue` objects — thread-safe mailboxes.

```python
class Bus:
    def __init__(self):
        self._subs = []                 # one queue per connected tab
        self._speaker = None            # the tab that gets the voice (see §7)
        self._lock = threading.Lock()   # guards _subs and _speaker

    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self._lock:                # only one thread mutates the list at a time
            self._subs.append(q)
            self._speaker = q           # newest tab becomes the speaker
        return q

    def publish(self, event, data):
        payload = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        with self._lock:
            for q in self._subs:
                try:
                    q.put_nowait(payload)      # drop into each mailbox
                except queue.Full:
                    ...                        # a stuck client; prune it
```

- **`queue.Queue` is thread-safe by design** — `put`/`get` are safe to call from different threads. That's why events travel through queues rather than shared lists.
- **`threading.Lock`** ensures that when one thread is editing `_subs`, no other thread reads or writes it mid-change. `with self._lock:` acquires and releases it automatically.
- **`maxsize=500` + `put_nowait`** means a browser that stopped reading can't make the server buffer forever; its queue fills and it gets pruned.

The background workers that feed the bus live in `server.py`: `_telemetry_loop` publishes system stats every second, `_slow_loop` refreshes network/weather/news on a stagger. Read `jane/metrics.py` to see `psutil` gather CPU/memory/disk — that's the one third-party library in this whole subsystem.

## 7. Single-speaker election (no double voice)

Here's a beautiful little design problem. If you open Jane in two tabs, both subscribe. A normal broadcast would send each spoken sentence to *both* tabs — and you'd hear Jane twice, slightly out of sync. Maddening.

Jane's fix: the bus tracks one `_speaker` — **the most recently connected tab** — and voice events go *only* to it:

```python
voice_events = event in ("speak", "voice")
targets = [self._speaker] if voice_events and self._speaker else self._subs
```

Everything visual (telemetry, logs, transcript) broadcasts to all tabs; only `speak`/`voice` are unicast to the single elected speaker. When that tab closes, `unsubscribe` hands the voice to whoever's left. This is why the newest window "takes the voice." Elegant, and it directly answers the user requirement *"make sure there aren't two voices."*

## 8. Lab — a live clock stream

Build a server with:
1. An `/api/stream` SSE endpoint using a bus like Jane's.
2. A background thread that publishes `event: tick` with the current time every second.
3. A one-page HTML client that uses `EventSource` to show the ticking time.
4. Open it in two tabs and confirm both update (broadcast). Then add a `whisper` event that only the newest tab receives (unicast) and prove it with a `console.log`.

---

## Checkpoint

1. Why SSE instead of WebSockets for Jane? When *would* you need WebSockets?
2. What terminates a single SSE event on the wire?
3. Why must you `flush()` after each write to the stream?
4. What two things does `threading.Lock` protect in the bus, and what goes wrong without it?
5. Explain single-speaker election as if to a teammate. Which events are unicast?

→ [Week 4](week-04-the-brain.md)

