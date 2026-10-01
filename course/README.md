# Building J.A.N.E. — A Course

*From an empty folder to a talking, thinking, acting AI assistant — using the real code you already have.*

---

## What this is

This is a complete, self-paced course that teaches you **everything** that went into building J.A.N.E.: a JARVIS-style voice assistant themed on Patrick Jane from *The Mentalist*. By the end you will understand — and be able to rebuild from scratch — every technology, library, protocol, and design decision in the project.

We don't hand-wave. Every concept is taught from first principles, then shown in Jane's actual source. You finish each week having built a working piece of the real system.

## Who it's for

You can already write basic code (variables, functions, loops, a little Python and a little JavaScript). You do **not** need to know web servers, APIs, async programming, LLMs, or audio. We build all of that here.

## What you'll be able to do at the end

- Write an HTTP server and a real-time streaming API using **only the Python standard library** — no Flask, no Django, no Node.
- Talk to a large language model (the **Anthropic Messages API**) with streaming, tool use, prompt caching, and extended thinking.
- Give an AI **agency**: a safe tool system that lets it read files, run searches, send email, and control desktop apps — with a hard human-confirmation boundary.
- Build a **voice interface**: speech recognition, speech synthesis, neural TTS, and the tricky problem of stopping an assistant from hearing itself.
- Build a **cinematic single-page frontend** in vanilla JavaScript with a clean state architecture and accessible, responsive CSS.

## The technology map (everything Jane uses)

| Area | Technology | Where it lives | Taught in |
|------|-----------|----------------|-----------|
| Web server | `http.server`, `ThreadingHTTPServer` | `jane/server.py` | Week 2 |
| Real-time | Server-Sent Events (SSE), `EventSource` | `server.py`, `web/js/bus.js` | Week 3 |
| Concurrency | `threading`, `queue.Queue` | `jane/logbus.py` | Week 3 |
| The LLM | Anthropic Messages API, `anthropic` SDK | `jane/brain.py` | Week 4 |
| Prompt design | System prompts, prompt caching, thinking | `jane/persona.py` | Week 4 |
| Agency | Tool use / function calling, dispatch tables | `jane/tools.py` | Week 5 |
| Persistence | JSON files, sandboxed workspace | `workspace.py`, `ledger.py`, `memory.py` | Week 5 |
| Ears | Web Speech API — `SpeechRecognition` | `web/js/voice.js` | Week 6 |
| Mouth | `speechSynthesis` + neural **edge-tts** | `web/js/voice.js`, `jane/speech.py` | Week 6 |
| Async I/O | `asyncio` (driving edge-tts) | `jane/speech.py` | Week 6 |
| Email | `smtplib`, `email.message` | `jane/mailer.py` | Week 7 |
| Desktop control | Launch protocols, `os.startfile`, `subprocess` | `jane/desktop.py` | Week 7 |
| Frontend | ES modules, state store, data-attribute CSS | `web/js/*`, `web/css/*` | Week 8 |
| System metrics | `psutil` | `jane/metrics.py` | Week 3 |
| Config | `.env` parsing, `os.environ` | `jane/config.py` | Week 1 |

## Course structure

Eight weeks. Each week is one file in this folder. Each contains:

- **Objectives** — what you'll know by the end.
- **Concepts** — the technology taught from scratch, before any Jane code.
- **In Jane's code** — a guided read of the real source.
- **Lab** — you build a working piece yourself.
- **Checkpoint** — questions to confirm you got it.

| Week | Title | You'll build |
|------|-------|--------------|
| 1 | [Foundations & Architecture](week-01-foundations.md) | Your environment + a one-file HTTP server |
| 2 | [The Web Server from Scratch](week-02-web-server.md) | Jane's static server + JSON API |
| 3 | [Real-Time: SSE & Pub/Sub](week-03-realtime-sse.md) | A live telemetry stream to the browser |
| 4 | [The Brain: the Anthropic API](week-04-the-brain.md) | A streaming, thinking conversation loop |
| 5 | [Tools & Agency](week-05-tools-and-agency.md) | The tool system + a sandboxed file tool |
| 6 | [Voice: Ears & Mouth](week-06-voice.md) | The full speech pipeline |
| 7 | [Acting on the World](week-07-acting-on-the-world.md) | Email + desktop control, safely |
| 8 | [The Frontend & Capstone](week-08-frontend-and-capstone.md) | The UI + your own new feature |

## How to use it

Read a week, run every snippet, do the lab. Keep Jane's source open beside you — the point is to connect the general idea to the specific line. Don't move on until the checkpoint feels easy.

Let's begin. → [Week 1](week-01-foundations.md)
