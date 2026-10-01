# Week 4 — The Brain: the Anthropic Messages API

> Goal: give Jane a mind. Understand large language models enough to use one well, then read `jane/brain.py` and `jane/persona.py` line by line — streaming, prompt caching, extended thinking, and the multi-round tool loop that lets Jane act.

---

## Objectives

- Understand what an LLM is and what the Messages API expects.
- Send a conversation and stream the reply token by token.
- Split a system prompt into a cached prefix and a volatile suffix (and know why).
- Use extended **thinking** and read its summaries.
- Understand the **tool-use loop** at a high level (Week 5 builds the tools).
- Handle every error the network and API can throw.

---

## 1. What an LLM actually is

A large language model is a function: give it a sequence of text, it predicts the most likely next chunk of text, over and over. That's it. Everything clever — answering, reasoning, calling tools — emerges from that one behaviour plus good instructions.

For Jane this means three things you control:
- **The system prompt** — standing instructions that shape *who* the model is (Jane's persona).
- **The messages** — the running conversation (user turn, assistant turn, user turn…).
- **The tools** — a menu of actions the model may ask you to perform.

You send all three; the model returns text and/or requests to use tools. You never "program" its personality directly — you *describe* it and it complies.

## 2. The client

Jane uses the official `anthropic` Python SDK. The whole setup is in `Brain.__init__`:

```python
client_kwargs = {"api_key": config.API_KEY, "max_retries": 3}
if config.BASE_URL:
    client_kwargs["base_url"] = config.BASE_URL     # a compatible gateway
self.client = anthropic.Anthropic(**client_kwargs)
```

- **`api_key`** authenticates you. It comes from `.env` via `config.py` — never hard-coded, never committed.
- **`max_retries=3`** — the SDK automatically retries transient failures with backoff. Free resilience.
- **`base_url`** — optional. Jane can point at an Anthropic-compatible gateway instead of `api.anthropic.com`. (In this project the gateway's token happens to allow the `claude-opus-4-8` model.)

If there's no valid key, `self.client` is `None` and Jane degrades gracefully: she can still *hear* (Week 6) but tells you she can't *think*. Notice the pattern again — missing capability, sensible fallback, not a crash.

## 3. The persona, and why it's split in two

`jane/persona.py` builds the system prompt as a **list of two blocks**:

```python
def system_blocks():
    return [
        {"type": "text", "text": PERSONA, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": situation_report()},
    ]
```

- `PERSONA` is a long, fixed description of who Jane is — how she thinks, how she speaks, what she won't do. It **never changes during a run**.
- `situation_report()` is volatile: the clock, the weather, the ledger, live system stats. It changes every single turn.

Why split them? **Prompt caching.** The `cache_control` marker tells the API: "you've seen this exact prefix before — reuse your cached processing of it instead of re-reading it." Caching only works on an unchanging prefix, so the fixed persona goes first (cached) and the volatile report goes after (never cached). This makes every turn faster and cheaper. If you put the changing clock *inside* the cached block, the cache would miss every time and the optimisation would be worthless. **Order matters.**

Open `persona.py` and read `PERSONA` itself — it's a masterclass in prompt writing: concrete voice rules ("one to three sentences," "numbers get rounded when spoken"), hard prohibitions ("never invent a fact"), and — crucially for Week 7 — the confirmation boundary for outward actions.

## 4. Streaming a reply

Jane doesn't wait for the whole answer — she streams it so speech can begin on the first sentence. `_request` builds the call:

```python
kwargs = dict(
    model=config.MODEL,
    max_tokens=16000,
    system=persona.system_blocks(),
    messages=messages,
    tools=tools.SCHEMAS,                       # the menu of actions — Week 5
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": config.EFFORT},
)
return self._stream(self.client.messages.stream(**kwargs))
```

`.stream(...)` yields a series of **events** as the model writes. `_stream` consumes them:

```python
for event in stream:
    if event.type == "content_block_delta":
        delta = event.delta
        if delta.type == "text_delta":
            pending += delta.text
            bus.publish("transcript_delta", {"text": delta.text})   # UI updates live
            # ...break pending into whole sentences and speak each one...
        elif delta.type == "thinking_delta":
            thought += delta.thinking
```

Two streams of content arrive interleaved: **text** (what Jane says) and **thinking** (her private reasoning). Text deltas are pushed to the browser instantly *and* accumulated in `pending`. When `pending` contains a complete sentence (detected by the `_SENTENCE_END` regex — a period/question mark/ellipsis followed by space, or a newline), Jane slices it off and calls `speech.say(sentence)`. That's why she starts talking before she's finished thinking: **sentence-level streaming**.

The thinking deltas are collected and, at each block's end, one line is logged as a "Deduction" — the little Mentalist touch of showing her reasoning without dumping all of it.

## 5. Extended thinking

`thinking={"type": "adaptive", "display": "summarized"}` turns on the model's ability to reason before answering. *Adaptive* means it thinks more on hard questions and less on trivial ones. *Summarized* means you receive a condensed version of that reasoning (the raw chain can be long). `output_config={"effort": ...}` is a second dial — higher effort spends more compute for better answers. Jane reads `EFFORT` from config so you can tune the speed/quality trade-off without touching code.

## 6. The tool loop (the part that makes Jane *act*)

This is the most important structure in the file. A model can't run code — it can only *ask* you to. So a turn is a loop:

```
you send: messages + tools
model replies with stop_reason:
  "end_turn"  → it's done talking. finish.
  "tool_use"  → it wants a tool run. YOU run it, append the result, loop again.
  "pause_turn"→ a server-side tool (web search) needs another round. loop.
  "refusal"   → it declined on safety grounds. stop cleanly.
```

Jane's `_turn` runs that loop up to `_MAX_TOOL_ROUNDS = 6` times:

```python
for _ in range(_MAX_TOOL_ROUNDS):
    message = self._request(messages)
    ...
    messages.append({"role": "assistant", "content": message.content})
    if message.stop_reason != "tool_use":
        break
    results = []
    for block in message.content:
        if block.type != "tool_use":
            continue
        output = tools.run(block.name, dict(block.input))   # ← run the tool
        results.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": output})
    messages.append({"role": "user", "content": results})   # feed results back
```

Read that carefully. The model says "call `get_weather` with `{city: 'Pune'}`." Jane runs it, gets "31°C, clear," wraps it as a `tool_result` tagged with the same `tool_use_id`, and sends it back. The model now *knows* the weather and writes its actual reply. The cap of 6 rounds stops runaway loops. Every tool call is wrapped in try/except so a broken tool returns an error result the model can react to, instead of crashing the turn.

## 7. Memory of the conversation

After the turn, Jane appends the user text and her reply to `self.history`, trimmed to the last `_MAX_HISTORY = 16` turns, and forced to start on a user turn:

```python
self.history = (self.history + [
    {"role": "user", "content": text},
    {"role": "assistant", "content": reply},
])[-_MAX_HISTORY:]
while self.history and self.history[0]["role"] != "user":
    self.history.pop(0)
```

The API is **stateless** — it remembers nothing between calls. *You* carry the conversation by resending the recent history each time. Trimming keeps the context (and cost) bounded; the "must start on a user turn" rule respects an API constraint about message ordering.

## 8. Errors

`ask()` wraps the turn in a try/except covering the whole family: `AuthenticationError`, `RateLimitError`, `APIConnectionError`, `APIStatusError`. Each maps to a calm, in-character message via `_fail`, which also **closes the open transcript** so the UI settles instead of hanging on a half-written line. Good error handling isn't just "don't crash" — it's "leave the interface in a sane state and tell the human what happened."

## 9. Lab — a minimal brain

Write a script that:
1. Creates an `anthropic.Anthropic` client from a key in `.env`.
2. Sends a system prompt ("You are terse and witty") and a user message.
3. **Streams** the reply, printing text deltas as they arrive.
4. Keeps a `history` list and holds a 3-turn back-and-forth in a loop.
5. Split your system prompt into a cached block + a volatile block containing the current time, exactly like `persona.py`.

Then add one trivial tool (`get_time`) and implement the tool loop until you see the model call it and use the result. This is Jane's brain in miniature — Week 5 makes the tools real.

---

## Checkpoint

1. Why is the persona split into a cached prefix and a volatile suffix? What breaks if you put the clock in the cached part?
2. What are the four `stop_reason` values Jane handles, and what does she do for each?
3. Why does Jane speak sentence-by-sentence instead of waiting for the full reply?
4. The Messages API is stateless. How does Jane have a memory of the conversation?
5. Why is every `tools.run(...)` wrapped in try/except, and what gets sent back on failure?

→ [Week 5](week-05-tools-and-agency.md)

