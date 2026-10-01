# Week 6 — Voice: Ears & Mouth

> Goal: build the full speech pipeline — recognising what you say, speaking Jane's replies, and solving the two hard problems (stopping her from hearing herself, and making the voice smooth without doubling). Files: `web/js/voice.js`, `jane/speech.py`, the `/api/tts/` route in `server.py`.

---

## Objectives

- Use the browser's **Web Speech API** for recognition (`SpeechRecognition`) and synthesis (`speechSynthesis`).
- Solve echo — keep Jane from transcribing her own voice.
- Understand why browser TTS sounds robotic and how server-side **neural TTS** (edge-tts) fixes it.
- Use `asyncio` to drive an async library from a normal threaded server.
- Guarantee exactly one voice, and reduce latency.

---

## 1. Two speech APIs, both in the browser

The browser ships two separate capabilities, both used in `voice.js`:

```js
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
export const canListen = Boolean(SR);          // ears
export const canSpeak = 'speechSynthesis' in window;   // mouth
```

- **`SpeechRecognition`** — microphone → text. Chrome/Edge only, hence the fallback to typed input elsewhere.
- **`speechSynthesis`** — text → audio, using voices installed on the OS.

Feature-detect both and degrade gracefully — the recurring theme of this whole course.

## 2. Listening that stays alive

Recognition sessions end on their own (Chrome cuts them after a while). Jane wants *continuous* listening, so `spin()` creates a recognizer and re-creates it whenever it ends, as long as you still want to listen:

```js
rec.continuous = true;
rec.interimResults = true;         // get partial results as you speak
rec.onend = () => {
    this.listening = false;
    this.onStateChange(false);
    if (this.wantListening) setTimeout(() => this.spin(), 260);  // respawn
};
```

`wantListening` (the user's intent) is kept separate from `listening` (the actual state). The recognizer dying doesn't change your intent, so Jane just spins up a fresh one. This intent-vs-state split is a clean pattern for anything that can drop and needs to reconnect.

Results arrive as **interim** (live, changing) and **final** (settled) transcripts:

```js
if (result.isFinal) {
    const clean = strip(text);          // drop a "Jane," wake word if present
    if (this.echoedByJane(clean)) continue;   // §3
    this.onFinal(clean);                 // send to the brain
} else {
    interim += `${text} `;               // show live, don't act yet
}
```

## 3. The echo problem

Here's the classic voice-assistant headache: Jane speaks through the speakers, the microphone hears her, recognition transcribes it, and Jane replies to *herself*. An infinite conversation with no human in it.

Jane defends on two fronts:

**Front one — mute while speaking.** Whenever Jane talks, `this.muted = true`, and any result heard during that window is discarded:

```js
rec.onresult = (e) => {
    if (this.muted) return;    // anything heard while Jane talks is Jane
    ...
};
```

The mute is lifted a short delay *after* she finishes, so the tail of her voice doesn't sneak in.

**Front two — echo matching.** Even with muting, timing gaps leak. So Jane remembers what she recently said and drops any heard text that matches:

```js
echoedByJane(heard) {
    const now = Date.now();
    this.spoken = this.spoken.filter((s) => now - s.at < 6000);  // last 6s only
    const h = norm(heard);
    return this.spoken.some((s) => s.text.includes(h) || h.includes(s.text));
}
```

`norm` lowercases and strips punctuation so "About thirty degrees." matches "about thirty degrees". Two independent defences because neither alone is reliable — **defence in depth** applied to audio.

## 4. Why browser TTS sounds robotic — and the fix

`speechSynthesis` uses whatever voices the OS provides. They're serviceable but flat — the "very AI" sound. Jane tries to pick the best available male English voice from a preference list (`VOICE_HINTS`), tunes rate and pitch slightly (`u.rate = 0.99; u.pitch = 0.92`), but there's a ceiling to how human a built-in voice gets.

The upgrade is **neural TTS**: a model that generates genuinely natural speech. Jane uses **edge-tts** (Microsoft's neural voices, free, no key). But it runs in *Python*, server-side — so the architecture is:

```
brain writes a sentence
   → speech.say(sentence)          (Python, jane/speech.py)
   → edge-tts synthesises an mp3
   → cached, and a "voice" event with a URL is published to the ONE speaker tab
   → browser fetches /api/tts/<token>.mp3 and plays it   (voice.js playAudio)
```

Crucially, if edge-tts **isn't installed**, `speech.say` falls back to publishing a `speak` event and the browser uses `speechSynthesis`. One entry point, two possible paths, **never both** — that's the single-voice guarantee, backed by the single-speaker election from Week 3.

## 5. Driving async from a threaded server (`jane/speech.py`)

edge-tts is an **async** library — its functions must be `await`ed inside an event loop. But Jane's server is thread-based, not async. The bridge is a dedicated worker thread that owns its own event loop:

```python
def _worker():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        _seq, text = _jobs.get()                      # pull the next sentence
        try:
            audio = loop.run_until_complete(_synth(text))   # run async → get bytes
            token = _store(audio)
            bus.publish("voice", {"url": f"/api/tts/{token}.mp3"})
        except Exception as exc:
            bus.publish("speak", {"text": text})       # fall back to browser voice
```

- `_jobs` is a `queue.Queue` — the same thread-safe mailbox pattern from Week 3, now feeding the synthesiser **in order** so sentences never come out shuffled.
- `run_until_complete` runs one async coroutine to completion inside this thread's loop — the standard way to call async code from sync code.
- `_synth` builds `edge_tts.Communicate(text, voice=..., rate=..., pitch=...)` and concatenates the streamed audio chunks into mp3 bytes.
- Synthesised clips are cached in an `OrderedDict` (cap 64) keyed by a token; the server serves them from `/api/tts/<token>.mp3` (`_serve_tts` in `server.py`).

The whole module decides its path *once* at import: if `JANE_TTS != "browser"` and `import edge_tts` succeeds, `ENABLED = True`; otherwise it logs and falls back. No per-sentence branching mistakes possible.

## 6. Playing audio in order, without doubling (`voice.js`)

The browser side queues clip URLs and plays them through a single reused `<audio>` element:

```js
playAudio(url) {
    if (!url) return;
    this.audioQueue.push(url);
    this.drainAudio();
}

drainAudio() {
    if (this.audioPlaying || !this.audioQueue.length) return;
    const url = this.audioQueue.shift();
    if (!this.audioEl) this.audioEl = new Audio();
    const el = this.audioEl;
    this.audioPlaying = true;
    this.muted = true;                    // mic is Jane's while she plays
    this.onSpeaking(true);
    const done = () => {
        this.audioPlaying = false;
        if (this.audioQueue.length) { this.drainAudio(); return; }  // next clip
        this.onSpeaking(false);
        setTimeout(() => { if (!this.audioPlaying) this.muted = false; }, 450);
    };
    el.onended = done;
    el.onerror = done;                    // a bad clip must not freeze the queue
    el.src = url;
    const p = el.play();
    if (p && p.catch) p.catch(() => done());   // autoplay blocked → don't hang
}
```

One element + a queue = clips can never overlap (no doubling). `onerror` and the `play().catch` both route to `done()` so a single failed clip advances the queue instead of freezing Jane mid-reply.

## 7. Reducing latency and the hang

Three fixes address the user's "buffer takes a lot of time and sometimes hangs":
- **Sentence-level streaming** (Week 4) — Jane speaks sentence one while writing sentence two, so you hear her almost immediately instead of after the whole reply.
- **Shorter mute tail** — the mic re-arms 450 ms after audio ends (down from 800 ms), so the conversation turns around faster.
- **Chrome keepalive** — Chrome silently pauses long `speechSynthesis` utterances after ~15 s; an interval calls `speechSynthesis.resume()` while speaking, then clears on end:

```js
const keepAlive = setInterval(() => {
    if (this.speakingNow) speechSynthesis.resume();
}, 8000);
```

## 8. Barge-in

`hush()` cuts Jane off mid-sentence — it clears both queues, pauses the audio element, and cancels `speechSynthesis`. That's what lets you interrupt her, exactly like a real conversation.

## 9. Lab — a talking echo box

1. A page with a mic button that transcribes your speech (`SpeechRecognition`) into a `<div>`.
2. When a final result arrives, speak it back with `speechSynthesis`.
3. Add the mute-while-speaking guard and prove that without it, it hears itself.
4. **Stretch (Python):** install `edge-tts`, synthesise a sentence to an mp3 file, and play it in the browser. Compare it to the browser voice — that difference is exactly what §4 is about.

---

## Checkpoint

1. What are the two Web Speech APIs, and which browsers support recognition?
2. Describe both echo defences. Why keep two instead of one?
3. Why does neural TTS have to run server-side, and what happens if edge-tts isn't installed?
4. How does Jane call an async library from its thread-based server?
5. Explain, mechanically, how "there aren't two voices" is guaranteed — name both mechanisms.

→ [Week 7](week-07-acting-on-the-world.md)

