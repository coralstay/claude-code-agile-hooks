#!/usr/bin/env python3
"""PostToolUse (matcher: Read|Grep|Glob|Bash)
Per-file context-cost leaderboard: attributes each tool result's approximate
token cost to the file(s) it loaded, so you can see which files cost the
most context over a session. Ported from karanb192/claude-code-hooks'
context-hogs plugin (MIT license).

Token cost is approximated from the tool response's character count
(chars / 4, the common rough estimate for English/code text) rather than
requiring a real tokenizer dependency - this hook stays stdlib-only like
every other hook in this repo, at the cost of exact precision. Good enough
for a relative leaderboard, which is the whole point.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/context-hogs.jsonl")

CHARS_PER_TOKEN = 4


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def response_text(tool_response):
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        for key in ("content", "output", "stdout", "result"):
            value = tool_response.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(tool_response)
    return ""


def files_for_tool(tool_name, tool_input):
    if tool_name == "Read":
        path = tool_input.get("file_path")
        return [path] if path else []
    if tool_name == "Glob":
        return []  # a file listing, not file contents - no single file to attribute cost to
    if tool_name == "Grep":
        path = tool_input.get("path")
        return [path] if path else []
    if tool_name == "Bash":
        return []  # no single file; command output isn't attributable to one path
    return []


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def leaderboard():
    """Aggregate the log into {file_path: total_tokens}, most expensive first."""
    if not os.path.isfile(LOG_PATH):
        return []
    totals = {}
    with open(LOG_PATH, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") != "cost":
                continue
            path = record.get("file_path")
            tokens = record.get("tokens", 0)
            if path:
                totals[path] = totals.get(path, 0) + tokens
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def handle_post_tool_use(data):
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    tokens = estimate_tokens(response_text(data.get("tool_response")))
    if tokens == 0:
        return

    for path in files_for_tool(tool_name, tool_input):
        append_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "cost",
                "session_id": data.get("session_id"),
                "file_path": path,
                "tokens": tokens,
            }
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("hook_event_name") == "PostToolUse":
        handle_post_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()
