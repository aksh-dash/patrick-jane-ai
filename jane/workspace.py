"""Jane's hands on the filesystem — confined to one folder tree.

Every path the model gives is resolved and checked to sit inside config.WORKSPACE
before anything is read or written. There is no way to reach outside it, and no
free-form shell here (that lives behind its own flag in tools.py). Files are the
point of a desktop assistant; this module keeps that power on a short leash.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config
from .logbus import bus

_MAX_READ = 200_000        # bytes — enough for source files, not whole binaries
_MAX_WRITE = 500_000       # bytes the model may hand us in one write
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea"}


class WorkspaceError(Exception):
    """A path outside the sandbox, or an operation that isn't allowed."""


def _root() -> Path:
    return config.WORKSPACE


def _read_root() -> Path:
    return config.READ_ROOT


def _resolve(rel: str) -> Path:
    """Resolve a user-supplied path against the workspace, refusing escapes."""
    if not config.ALLOW_FILES:
        raise WorkspaceError("File access is disabled. Set JANE_ALLOW_FILES=1 in .env.")
    root = _root()
    raw = (rel or "").strip().strip('"').strip("'")
    # An absolute path is only allowed if it already lives inside the workspace.
    candidate = Path(raw)
    target = candidate if candidate.is_absolute() else root / candidate
    try:
        target = target.resolve()
    except OSError as exc:
        raise WorkspaceError(f"Bad path: {exc}") from exc
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            f"'{raw}' is outside the workspace ({root}). I can only touch files under there."
        ) from exc
    return target


def _resolve_read(rel: str) -> Path:
    """Resolve a path for READING/SEARCHING, bounded by the wider READ_ROOT.

    This is the "look anywhere" leash: it permits any path under READ_ROOT (the
    home folder by default, the whole drive if the user widens it) but grants no
    power to write or run — those still answer to _resolve and the sandbox.
    """
    if not config.ALLOW_FILES:
        raise WorkspaceError("File access is disabled. Set JANE_ALLOW_FILES=1 in .env.")
    root = _read_root()
    raw = (rel or "").strip().strip('"').strip("'")
    candidate = Path(raw)
    target = candidate if candidate.is_absolute() else root / candidate
    try:
        target = target.resolve()
    except OSError as exc:
        raise WorkspaceError(f"Bad path: {exc}") from exc
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            f"'{raw}' is outside where I'm allowed to look ({root})."
        ) from exc
    return target


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(_root()))
    except ValueError:
        return str(p)


# --- operations ---------------------------------------------------------
def list_dir(rel: str = ".") -> str:
    target = _resolve_read(rel)
    if not target.exists():
        return f"Nothing at '{rel}'."
    if target.is_file():
        return f"{_rel(target)} is a file ({target.stat().st_size} bytes)."
    entries = []
    for child in sorted(target.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
        if child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        if child.is_dir():
            entries.append(f"{child.name}/")
        else:
            entries.append(f"{child.name} ({child.stat().st_size} B)")
    if not entries:
        return f"{_rel(target)}/ is empty."
    listing = "\n".join(entries)
    bus.log(f"Listed {_rel(target)}/", "tool")
    return f"{_rel(target)}/ contains:\n{listing}"


def read_file(rel: str) -> str:
    target = _resolve_read(rel)
    if not target.is_file():
        return f"No file at '{rel}'."
    if target.stat().st_size > _MAX_READ:
        return f"'{rel}' is too large to read ({target.stat().st_size} bytes; limit {_MAX_READ})."
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"'{rel}' isn't a text file I can read."
    bus.log(f"Read {_rel(target)}", "tool")
    return f"--- {_rel(target)} ---\n{text}"


def write_file(rel: str, content: str) -> str:
    target = _resolve(rel)
    content = content or ""
    if len(content.encode("utf-8")) > _MAX_WRITE:
        return f"That's too much to write at once (limit {_MAX_WRITE} bytes)."
    existed = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    bus.log(f"{'Rewrote' if existed else 'Created'} {_rel(target)}", "ok")
    verb = "Rewrote" if existed else "Created"
    return f"{verb} {_rel(target)} ({len(content)} chars)."


def append_file(rel: str, content: str) -> str:
    target = _resolve(rel)
    content = content or ""
    if len(content.encode("utf-8")) > _MAX_WRITE:
        return f"That's too much to append at once (limit {_MAX_WRITE} bytes)."
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep a clean line boundary when adding to an existing non-empty file.
    prefix = ""
    if target.is_file() and target.stat().st_size:
        tail = target.read_bytes()[-1:]
        if tail not in (b"\n", b""):
            prefix = "\n"
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(prefix + content)
    bus.log(f"Appended to {_rel(target)}", "ok")
    return f"Appended {len(content)} chars to {_rel(target)}."


def find(query: str, root: str = ".", limit: int = 40) -> str:
    """Search names recursively under READ_ROOT for files/folders matching `query`.

    Read-only reconnaissance — "find the folder on my C drive with those files."
    Breadth-first from `root` so shallow, near-the-top matches (what people
    usually mean) surface before the walk disappears into some giant deep tree.
    Case-insensitive substring match on names, pruning noise dirs and capping
    both hits and directories scanned so a whole-drive search still returns.
    """
    import os
    from collections import deque

    q = (query or "").strip().lower()
    if not q:
        return "Give me something to search for."
    base = _resolve_read(root)
    if not base.exists():
        return f"Nothing at '{root}' to search under."
    if base.is_file():
        base = base.parent

    limit = max(1, min(int(limit), 200))
    hits: list[str] = []
    scanned = 0
    truncated = False
    _SCAN_CAP = 120_000         # directories — a sane ceiling for a live drive walk
    queue: "deque[Path]" = deque([base])
    while queue and len(hits) < limit:
        current = queue.popleft()
        scanned += 1
        if scanned > _SCAN_CAP:
            truncated = True
            break
        try:
            with os.scandir(current) as it:
                for entry in it:
                    name = entry.name
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir and (name in _SKIP_DIRS or name.startswith(".")):
                        continue
                    if q in name.lower():
                        hits.append(entry.path + ("\\" if is_dir else ""))
                        if len(hits) >= limit:
                            break
                    if is_dir:
                        queue.append(Path(entry.path))
        except (PermissionError, OSError):
            continue        # locked system folders are simply skipped

    if not hits:
        return f"No files or folders matching '{query}' under {base}."
    bus.log(f"Searched for '{query}' under {base} — {len(hits)} hit(s)", "tool")
    tail = ""
    if len(hits) >= limit:
        tail = "\n… (more matches exist; refine the search)"
    elif truncated:
        tail = "\n… (stopped early — search space too large; give me a narrower root)"
    return f"Matches for '{query}' under {base}:\n" + "\n".join(hits) + tail


def run_command(command: str) -> str:
    """Run a shell command in the workspace. Off unless JANE_ALLOW_SHELL=1."""
    if not config.ALLOW_SHELL:
        return ("Shell execution is off. Set JANE_ALLOW_SHELL=1 in .env if you want me "
                "to run commands — and know what that means before you do.")
    command = (command or "").strip()
    if not command:
        return "No command given."
    bus.log(f"Shell: {command}", "warn")
    try:
        proc = subprocess.run(
            command, shell=True, cwd=str(_root()),
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "That command took longer than a minute, so I stopped it."
    out = (proc.stdout or "") + (proc.stderr or "")
    out = out.strip() or "(no output)"
    if len(out) > 4000:
        out = out[:4000] + "\n… (truncated)"
    return f"Exit {proc.returncode}:\n{out}"
