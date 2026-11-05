#!/usr/bin/env python3
"""UserPromptSubmit + PreToolUse(Edit|Write)
Remembers approaches that were tried and reverted (with a reason), and warns
before retrying the same dead end. Ported from karanb192/claude-code-hooks'
dead-end-registry plugin (MIT license).

Registration is manual by design (upstream is the same): the user tells the
agent "that didn't work because X" in a prompt matching a "revert" pattern
(mentions undo/revert/rollback/dead end), which UserPromptSubmit records
against the current file(s) recently edited this session. On the next
Edit/Write to a file with a registered dead end, PreToolUse warns (doesn't
block - this is advisory) via additionalContext... but PreToolUse doesn't
support additionalContext for blocking events, so the warning goes to
stderr on allow (visible in the debug log) plus is always recorded so
`/dead-end-registry:dead-ends`-style tooling (not built here) could render it.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys
from datetime import datetime, timezone

REGISTRY_PATH = os.path.expanduser("~/.claude/hooks-logs/dead-end-registry.jsonl")

REVERT_MENTION_RE = re.compile(
    # \b works for space-delimited English words but not for Korean, where a
    # verb stem (e.g. 되돌-) fuses directly with its conjugation ending with
    # no boundary in between - so the Korean alternatives skip \b entirely.
    r"(?:\b(?:revert|undo|rollback)\b|되돌|취소|롤백).{0,120}(?:\b(?:because|since)\b|이유|때문에)",
    re.IGNORECASE,
)


def append_registry(record):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def recent_files_for_session(session_id, limit=5):
    path = os.path.expanduser(f"~/.claude/hooks-logs/sessions/{session_id}.jsonl")
    if not os.path.isfile(path):
        return []
    files = []
    with open(path, errors="ignore") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") == "tool_use" and record.get("file_path"):
                files.append(record["file_path"])
    return files[-limit:]


def dead_ends_for_file(file_path):
    if not os.path.isfile(REGISTRY_PATH):
        return []
    entries = []
    with open(REGISTRY_PATH, errors="ignore") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("file_path") == file_path:
                entries.append(record)
    return entries


def handle_user_prompt_submit(data):
    prompt = data.get("prompt", "")
    if not REVERT_MENTION_RE.search(prompt):
        sys.exit(0)

    files = recent_files_for_session(data.get("session_id"))
    for file_path in files:
        append_registry(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": file_path,
                "reason": prompt,
            }
        )
    sys.exit(0)


def handle_pre_tool_use(data):
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    dead_ends = dead_ends_for_file(file_path)
    if dead_ends:
        latest = dead_ends[-1]
        print(
            f"[dead-end-registry] '{file_path}'에 이전에 되돌린 접근이 있습니다: {latest['reason']}",
            file=sys.stderr,
        )
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    if event == "UserPromptSubmit":
        handle_user_prompt_submit(data)
    elif event == "PreToolUse":
        handle_pre_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()
