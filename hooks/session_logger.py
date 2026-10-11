#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit + PostToolUse + SessionEnd
Writes a durable JSONL log of everything that happens in a session: cwd, git
branch, every prompt submitted, every file touched, every bash command run
(secrets best-effort redacted). Ported from karanb192/claude-code-hooks'
session-logger plugin (MIT license). UserPromptSubmit prompt logging is this
repository's own implementation, written into the same log as one more event type.

CC_SESSION_LOG_DIR overrides the log directory (e.g. point it at an Obsidian
vault); defaults to ~/.claude/hooks-logs/sessions/.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SECRET_VALUE_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd)(\s*[:=]\s*)(\S+)", re.IGNORECASE
)


def redact(command):
    return SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", command)


def log_dir():
    return os.environ.get("CC_SESSION_LOG_DIR") or os.path.expanduser("~/.claude/hooks-logs/sessions")


def log_path(session_id):
    return os.path.join(log_dir(), f"{session_id or 'unknown'}.jsonl")


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def append_entry(session_id, entry):
    path = log_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def handle_session_start(data):
    cwd = data.get("cwd", "")
    append_entry(
        data.get("session_id"),
        {"event": "session_start", "cwd": cwd, "branch": current_branch(cwd)},
    )


def handle_user_prompt_submit(data):
    append_entry(
        data.get("session_id"),
        {"event": "prompt", "prompt": data.get("prompt", "")},
    )


def handle_post_tool_use(data):
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    entry = {"event": "tool_use", "tool_name": tool_name}

    if tool_name in ("Edit", "Write"):
        entry["file_path"] = tool_input.get("file_path")
    elif tool_name == "Bash":
        entry["command"] = redact(tool_input.get("command", ""))

    append_entry(data.get("session_id"), entry)


def handle_session_end(data):
    append_entry(
        data.get("session_id"),
        {"event": "session_end", "reason": data.get("reason")},
    )


HANDLERS = {
    "SessionStart": handle_session_start,
    "UserPromptSubmit": handle_user_prompt_submit,
    "PostToolUse": handle_post_tool_use,
    "SessionEnd": handle_session_end,
}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    handler = HANDLERS.get(data.get("hook_event_name", ""))
    if handler:
        handler(data)

    sys.exit(0)


if __name__ == "__main__":
    main()
