#!/usr/bin/env python3
"""SessionStart + PreCompact + Stop
TASK-31 "context flags": hooks can't add fields to Claude Code's own hook
payload, so this hook keeps a tiny per-session flag file that other hooks
(or a human debugging a session) can read to learn session state the
payload of *their* event doesn't carry.

File: $CC_HOOK_FLAGS_DIR/<session_id>.json
      (default ~/.claude/hooks-logs/flags/<session_id>.json)

Schema (every key optional for readers - treat missing as "unknown"):
  session_id            str
  updated_at            ISO-8601 UTC, last write by any event
  last_start_source     SessionStart `source`: startup|resume|clear|compact
  post_compact          bool - context was compacted (SessionStart
                        source=compact); reset to false by startup/clear,
                        kept as-is by resume
  compacted_at          ISO-8601 UTC of the latest compaction
  compact_count         int, compactions seen in this session
  compact_trigger       PreCompact `trigger`: auto|manual
  pre_compact_at        ISO-8601 UTC of the latest PreCompact
  parallel_session      bool - Stop payload's `background_tasks` non-empty
  background_task_count int
  parallel_checked_at   ISO-8601 UTC of the latest Stop

Writes are atomic (temp file + os.replace) so concurrent writers never
leave a half-written file. Fail-open: any exception exits 0 - a flag
writer must never be the hook that paralyses a session.

Fully self-contained: no imports from any other file in this repo."""

import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone


def flags_dir():
    return os.environ.get("CC_HOOK_FLAGS_DIR") or os.path.expanduser(
        "~/.claude/hooks-logs/flags"
    )


def flags_path(session_id):
    name = os.path.basename(str(session_id or "")) or "unknown"
    return os.path.join(flags_dir(), f"{name}.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def read_flags(session_id):
    try:
        with open(flags_path(session_id)) as f:
            flags = json.load(f)
    except (OSError, ValueError):
        return {}
    return flags if isinstance(flags, dict) else {}


def write_flags(session_id, flags):
    path = flags_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(flags, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def background_tasks_running(data):
    """True if the Stop payload says background work is still running.
    The field's shape isn't documented, so any non-empty list/dict counts."""
    tasks = data.get("background_tasks")
    return isinstance(tasks, (list, dict)) and len(tasks) > 0


def apply_session_start(flags, data):
    source = data.get("source")
    flags["last_start_source"] = source
    flags.setdefault("compact_count", 0)
    if source == "compact":
        flags["post_compact"] = True
        flags["compacted_at"] = now()
        flags["compact_count"] += 1
    elif source in ("startup", "clear") or "post_compact" not in flags:
        flags["post_compact"] = False


def apply_pre_compact(flags, data):
    flags["compact_trigger"] = data.get("trigger")
    flags["pre_compact_at"] = now()


def apply_stop(flags, data):
    running = background_tasks_running(data)
    flags["parallel_session"] = running
    flags["background_task_count"] = len(data.get("background_tasks")) if running else 0
    flags["parallel_checked_at"] = now()


HANDLERS = {
    "SessionStart": apply_session_start,
    "PreCompact": apply_pre_compact,
    "Stop": apply_stop,
}


def update(data):
    handler = HANDLERS.get(data.get("hook_event_name", ""))
    if not handler:
        return
    session_id = data.get("session_id")
    flags = read_flags(session_id)
    handler(flags, data)
    flags["session_id"] = session_id or "unknown"
    flags["updated_at"] = now()
    write_flags(session_id, flags)


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            update(data)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
