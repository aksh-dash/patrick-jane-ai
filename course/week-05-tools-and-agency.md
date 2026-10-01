# Week 5 — Tools & Agency

> Goal: turn a talker into a doer. Learn how tool schemas work, build a dispatch table, and study the safety patterns that let Jane touch the filesystem, remember facts, and search the web without being dangerous. Files: `jane/tools.py`, `jane/workspace.py`, `jane/ledger.py`, `jane/memory.py`.

---

## Objectives

- Write a JSON tool schema the model understands.
- Build a dispatch table mapping tool names to Python functions.
- Design tools that are safe by construction (sandboxing, limits, allow-lists).
- Understand the difference between local tools and server-side tools (web search).
- See how persistence (ledger, memory) is just JSON on disk.

---

## 1. What "agency" means here

Last week the model could *ask* to run a tool. This week we define the tools it can ask for. A tool is two things:

1. A **schema** — a JSON description of the tool's name, what it does, and what arguments it takes. This goes to the model so it knows the menu.
2. An **implementation** — the Python function that actually runs when the model calls it.

Jane keeps all schemas in `tools.SCHEMAS` (a list) and all implementations behind one `tools.run(name, args)` function. Clean separation: the model reads the menu, `run` does the cooking.

## 2. Anatomy of a schema

Here's the weather tool's schema (`tools.py`):

```python
{
    "name": "get_weather",
    "description": "Current weather conditions for a city. Omit the city for the "
                   "user's own location.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name."}},
    },
}
```

- **`name`** — how the model refers to it, and the key `run` dispatches on.
- **`description`** — the single most important field. This is how the model decides *when* to use the tool. Vague descriptions cause misuse; Jane's are specific and even hint at behaviour ("Omit the city for the user's own location").
- **`input_schema`** — a JSON Schema of the arguments. `properties` lists each argument with its type; a `required` list (see below) marks the mandatory ones.

The `ledger_add` tool shows a required argument:

```python
"input_schema": {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
},
```

Writing schemas *is* prompt engineering. The model behaves exactly as well as your descriptions let it.

> **Caching note (ties back to Week 4):** `SCHEMAS` order is fixed and must be byte-identical between requests, because the tool list is part of the cached prefix. Reordering it silently would blow the cache. Small detail, real cost.

## 3. The dispatch table

`tools.run` is a long `if`/`elif` ladder — a **dispatch table** in its plainest form:

```python
def run(name, args):
    bus.log(f"Tool: {name}", "tool")
    if name == "get_weather":
        ...
        return weather.summary(args.get("city"))
    if name == "ledger_add":
        entry = ledger.add(args["text"])
        _ledger_changed()
        return f"Added to the ledger: {entry['text']}"
    ...
    return f"Unknown tool: {name}"
```

Every branch does the work and **returns a plain string** — that string becomes the `tool_result` the brain feeds back to the model (Week 4, §6). Note two habits:
- Every tool call is logged to the bus, so the UI shows Jane reaching for a tool in real time.
- Required args use `args["text"]` (fail loud if missing); optional args use `args.get("city")` (default to `None`). The schema and the code agree on which is which.

The final `return f"Unknown tool"` is a safety net — if the model ever invents a tool name, Jane says so instead of throwing.

## 4. Safety pattern A — the sandbox

The file tools are the sharpest edge. `jane/workspace.py` confines *every* path to one folder tree (`config.WORKSPACE`). The gatekeeper is `_resolve`:

```python
def _resolve(rel):
    if not config.ALLOW_FILES:
        raise WorkspaceError("File access is disabled. Set JANE_ALLOW_FILES=1 in .env.")
    root = _root()
    candidate = Path((rel or "").strip().strip('"').strip("'"))
    target = candidate if candidate.is_absolute() else root / candidate
    target = target.resolve()                 # collapse any ../ tricks
    target.relative_to(root)                  # raises ValueError if outside root
    return target
```

This is the **same path-traversal defence you learned in Week 2**, reused for a different surface. `resolve()` + `relative_to()` = "you cannot escape this folder." Every read/write/list/append goes through `_resolve` first, so there is no code path that touches a file outside the sandbox. Plus:

- **Size limits** — `_MAX_READ` (200 KB) and `_MAX_WRITE` (500 KB) stop Jane from slurping a huge binary or being handed a monstrous write.
- **Encoding guards** — reading a non-text file returns a friendly message, not a `UnicodeDecodeError`.
- **`ALLOW_FILES` flag** — the whole capability is off unless you opt in.

## 5. Safety pattern B — allow-lists

The app launcher (`_launch_app` in `tools.py`) does **not** run arbitrary commands. It maps a fixed set of names to fixed commands:

```python
_APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "spotify": ["cmd", "/c", "start", "spotify:"],
    ...
}
```

The model can only open things on this list; anything else returns "not on the allow-list" with the available options. This is the opposite philosophy to free-form shell — **enumerate what's permitted rather than trying to block what's forbidden.** (Users extend it via `data/apps.json`, merged on top.)

## 6. Safety pattern C — the loaded gun stays holstered

`run_command` (real shell execution) exists but is **off by default** behind `JANE_ALLOW_SHELL`:

```python
def run_command(command):
    if not config.ALLOW_SHELL:
        return ("Shell execution is off. Set JANE_ALLOW_SHELL=1 in .env if you want me "
                "to run commands — and know what that means before you do.")
    ...
    proc = subprocess.run(command, shell=True, cwd=str(_root()),
                          capture_output=True, text=True, timeout=60)
```

Note the 60-second timeout and the 4000-char output cap. Even the dangerous tool has guardrails. The lesson: **the most powerful capability should be the hardest to turn on, and still bounded when it is.**

## 7. Local vs. server-side tools

Most tools run on *your* machine. But look at the last entry in `SCHEMAS`:

```python
{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}
```

This is a **server-side tool** — it runs on Anthropic's side, not yours. You don't implement it; you just declare it, and the model performs the search during its own turn (that's the `pause_turn` stop reason from Week 4). `max_uses` caps it. The takeaway: some tools you build, some you just switch on.

## 8. Persistence is just JSON

The ledger (`ledger.py`) and memory (`memory.py`) are not databases — they're JSON files read and written on disk. `ledger.add` appends an item, saves the list, and the tool layer publishes the new state to the bus so the UI updates live. This is entirely enough for a single-user assistant. Don't reach for a database until a flat file genuinely hurts.

## 9. Lab — add a tool end to end

Add a `roll_dice` tool:
1. Write its schema (name, description, an optional `sides` integer defaulting to 6) and place it in `SCHEMAS`.
2. Add a branch in `run` that returns `"You rolled a 4 (d6)."`.
3. Run Jane, say "roll a d20," and watch the tool loop fire in the logs.

Then, harder: add a `word_count` tool that uses the **workspace** to read a file and count its words — forcing you to go through `_resolve`. Try to make it read a file outside the workspace and confirm it refuses.

---

## Checkpoint

1. What are the two halves of a tool, and where does each live in Jane?
2. Why is the tool `description` field the most important part of a schema?
3. Explain the sandbox's `resolve()` + `relative_to()` defence. Where else in Jane have you seen it?
4. Contrast the allow-list philosophy (`_APPS`) with free-form shell. When is each appropriate?
5. What's different about the `web_search` tool compared to `get_weather`?

→ [Week 6](week-06-voice.md)

