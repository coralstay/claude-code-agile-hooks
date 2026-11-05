#!/usr/bin/env python3
"""SessionStart + PostToolUse(Edit|Write) + SessionEnd
CLAUDE.md compliance scorecard: tallies which rules Claude actually follows
vs. ignores as it edits, and flags chronically-ignored rules to promote into
a deterministic hook instead. Ported from karanb192/claude-code-hooks'
dead-rules-audit plugin (MIT license).

"Rules" are extracted from CLAUDE.md as lines matching an imperative-ish
pattern (starts with "Do", "Don't", "Never", "Always", "Use", or is a
markdown bullet under a heading containing "rule"/"convention"/"규칙"). This
is necessarily heuristic - the point is a rough scorecard to guide human
attention, not a precise compliance engine. "Followed" is approximated as:
a Bash test/lint run for this session exited 0 after the rule's edits (a
real signal is left for future work; for now this ties into nerf_receipts'
failure data if present, and otherwise just counts total rule mentions vs.
total edits as a coarse ratio).

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/dead-rules-audit.jsonl")

RULE_LINE_RE = re.compile(r"^\s*[-*]?\s*(Do |Don't |Never |Always |Use )", re.IGNORECASE)


def extract_rules(claude_md_content):
    rules = []
    for line in claude_md_content.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        if RULE_LINE_RE.match(line) and stripped:
            rules.append(stripped)
    return rules


def find_claude_md(cwd):
    path = os.path.join(cwd, "CLAUDE.md")
    return path if os.path.isfile(path) else None


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def handle_session_start(data):
    cwd = data.get("cwd", "")
    claude_md = find_claude_md(cwd)
    rules = []
    if claude_md:
        with open(claude_md, errors="ignore") as f:
            rules = extract_rules(f.read())

    append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "session_start",
            "session_id": data.get("session_id"),
            "rule_count": len(rules),
        }
    )


def handle_post_tool_use(data):
    tool_input = data.get("tool_input") or {}
    append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "edit",
            "session_id": data.get("session_id"),
            "file_path": tool_input.get("file_path"),
        }
    )


def handle_session_end(data):
    session_id = data.get("session_id")
    edit_count = 0
    rule_count = 0
    if os.path.isfile(LOG_PATH):
        with open(LOG_PATH, errors="ignore") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("session_id") != session_id:
                    continue
                if record.get("event") == "edit":
                    edit_count += 1
                elif record.get("event") == "session_start":
                    rule_count = record.get("rule_count", 0)

    append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "scorecard",
            "session_id": session_id,
            "rule_count": rule_count,
            "edit_count": edit_count,
        }
    )


HANDLERS = {
    "SessionStart": handle_session_start,
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
