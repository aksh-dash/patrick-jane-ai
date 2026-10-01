# Week 8 — The Frontend & Capstone

> Goal: understand the browser half — how a single honest state store drives a cinematic, accessible UI in vanilla JavaScript — then build your own new feature end to end. Files: `web/index.html`, `web/js/store.js`, `web/js/bus.js`, `web/js/app.js`, `web/css/*`.

---

## Objectives

- Structure a frontend with ES modules and no framework.
- Build a single **state store** that everything reads from and nothing bypasses.
- Drive CSS from state via `data-*` attributes.
- Respect accessibility and `prefers-reduced-motion`.
- Ship a complete new capability across the whole stack (the capstone).

---

## 1. No framework here either

The frontend is plain ES modules — `<script type="module">` in `index.html` importing `.js` files that `export`/`import` from each other. No React, no build step, no bundler. The browser loads modules directly. For a UI this size, that's all you need, and — like the backend choice — it keeps every mechanism visible.

The modules divide by job:
- `store.js` — the single source of truth for "what is Jane doing right now."
- `bus.js` — the SSE client; turns server events into `on(event, fn)` callbacks.
- `voice.js` — ears and mouth (Week 6).
- `app.js` — the wiring: connect bus events and voice to the store and the UI.
- layer/UI modules — render pieces of the screen from the store.

## 2. The state store — one source of truth

`store.js` holds *all* live state in one object and lets modules subscribe to changes. This is the single most important frontend idea in Jane:

```js
const state = {
  mode: STATES.IDLE,          // the lifecycle: idle → listening → processing → …
  context: null,              // which panel is pulled into focus
  micLive: false,
  data: { telemetry: {}, weather: null, news: [], ledger: [], /* … */ },
};

const subs = new Set();
export function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }
function notify(kind) { for (const fn of subs) fn(state, kind); }

export function setMode(mode) {
  if (state.mode === mode) return;   // no-op if unchanged → no needless renders
  state.mode = mode;
  notify('mode');
}
```

The rule the file states plainly: *"Everything visual reads from here; nothing visual owns state of its own."* When state changes, `notify` tells every subscriber what slice changed, and each decides whether it needs to re-render. This is exactly the idea behind every state library (Redux, Vuex, signals) — Jane just does it in 100 readable lines so you can *see* it. `patch(slice, value)` merges fresh server data and fires `data:telemetry`, `data:weather`, etc., so a subscriber can listen for only the slice it cares about.

## 3. The SSE client

`bus.js` is the browser mirror of Week 3's server bus. It opens the `EventSource`, and exposes:

```js
on('telemetry', (data) => store.patch('telemetry', data));
on('speak',  ({ text }) => voice.say(text));
on('voice',  ({ url })  => voice.playAudio(url));      // neural audio (Week 6)
on('transcript_delta', layers.transcriptDelta);
```

Every server event you learned to *publish* in Python has a matching `on(...)` here that *consumes* it. `app.js` is essentially a wiring diagram connecting those two halves: bus event → store update or voice action → UI reacts. Read `app.js`'s block of `on(...)` calls as the definitive list of "everything the server can tell the browser."

## 4. State-driven CSS with `data-*` attributes

Here's how state becomes pixels without per-element JavaScript. A subscriber writes the current mode onto a single element as a data attribute:

```js
subscribe((state) => { app.dataset.mode = state.mode; app.dataset.context = state.context || ''; });
```

Then CSS reacts to it:

```css
#app[data-mode="listening"] .waveform { opacity: 1; }
#app[data-mode="idle"]      .waveform { opacity: 0; }
#app[data-context="subject"] .tile-subject { transform: scale(1); }
```

The JavaScript's whole job is to set one or two attributes; **CSS does the animating**. This is fast (the browser's compositor handles transitions), clean (visual logic lives in the stylesheet), and easy to reason about. Changing how "listening" looks means editing CSS, not JS.

## 5. Accessibility & reduced motion

Jane is deliberately cinematic — glows, scans, motion. That can be actively harmful to people with vestibular disorders, so the CSS honours the OS setting:

```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition-duration: 0.01ms !important; }
}
```

Other habits to notice: text keeps real contrast, interactive elements are reachable and labelled, and nothing critical is conveyed by colour or motion *alone* (the transcript is always there in text). Accessibility isn't a feature you bolt on — it's a constraint you design under from the start.

## 6. The bootstrap handshake

On load, the page can't wait for slow SSE events to paint itself. So `app.js` first calls `GET /api/bootstrap` (Week 2), which returns *everything the UI needs at once* — model, city, greeting, current telemetry, weather, news, ledger, memory, the log. `store.seed(bootstrap)` fills the store, the UI paints, and *then* the SSE stream keeps it live. First paint from a snapshot, updates from the stream — a common and effective pattern.

## 7. Putting the whole stack together

Trace one full utterance and you'll see all eight weeks fire in sequence:

1. **You speak** → `voice.js` `SpeechRecognition` → final text (Week 6).
2. `app.js` sends it → `POST /api/say` (Weeks 2 & 8).
3. `server.py` spawns a thread → `brain.ask(text)` (Weeks 3 & 4).
4. **Brain** streams from the Anthropic API, maybe looping through **tools** (Weeks 4 & 5).
5. Each sentence → `speech.say` → neural mp3 or browser voice (Week 6).
6. Sentences and deltas → the **bus** → SSE → the browser (Week 3).
7. `bus.js` routes events → `store` updates → `data-*` attributes change → **CSS animates** (Week 8).
8. If Jane sends an email or opens WhatsApp, the **confirmation boundary** holds (Week 7).

That's Jane, whole. Every arrow is now code you can read and change.

## 8. Capstone — ship a feature end to end

Build **one new capability that touches every layer**. A good choice: a **"focus timer" panel** — say "start a 25 minute focus timer," Jane confirms, a live countdown tile appears, and she announces completion aloud.

Steps, using everything you learned:
1. **Tool (Week 5):** you already have `set_timer`; extend it (or add `focus_timer`) with a schema and a `run` branch.
2. **Real-time (Week 3):** publish a `focus` event each second with the remaining time from a background thread.
3. **Frontend (Week 8):** `on('focus', …)` → `store.patch('focus', …)`; a subscriber sets a `data-*` attribute; CSS shows/animates the countdown tile.
4. **Voice (Week 6):** on completion, `speech.say("That's twenty-five minutes. Break.")`.
5. **Accessibility (Week 8):** ensure the countdown is readable text, and the animation respects reduced motion.

If you can build that unaided, you understand Jane completely — which was the point.

## 9. Where to go next

- **Harden it:** add tests, rate-limit `/api/say`, put real auth on the server if it ever leaves localhost (right now it binds `127.0.0.1` precisely so it can't be reached from outside — never expose it without adding authentication).
- **Extend the mind:** new tools are the highest-leverage additions (a calendar, a to-do sync, home automation).
- **Swap the voice:** try different `edge-tts` voices, or a different neural TTS entirely — the `speech.say` seam makes it a one-file change.
- **Read the code you didn't touch:** `metrics.py`, `netmap.py`, `weather.py`, `news.py` are small, self-contained tools that reinforce every pattern here.

---

## Checkpoint

1. Why does "nothing visual owns state of its own" make the UI easier to reason about?
2. How does a state change in `store.js` end up animating an element, without per-element JS?
3. What does `/api/bootstrap` solve that the SSE stream alone can't?
4. Trace a full utterance through all eight weeks from memory.
5. For your capstone, which layer was hardest, and why? (That's where to keep practising.)

---

*You've reached the end. You started at an empty folder and a one-line HTTP server; you can now read, explain, and extend every part of a thinking, talking, acting assistant. Go build something of your own.* → back to the [syllabus](README.md).

