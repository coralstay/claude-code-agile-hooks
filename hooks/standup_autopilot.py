#!/usr/bin/env python3
"""SessionStart(startup) + Stop + SessionEnd
Writes a daily standup from what the agent actually did across sessions:
captures files touched, bash commands run, and tasks worked on from
session_logger.py's log, and re-injects yesterday's open items at the next
SessionStart. Ported from karanb192/claude-code-hooks' standup-autopilot
plugin (MIT license).

Output: ~/.claude/hooks-logs/standup/<YYYY-MM-DD>.md, one entry appended per
Stop event, summarizing that turn's file/command activity for the day.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

STANDUP_DIR = os.path.expanduser("~/.claude/hooks-logs/standup")


def today_path():
    return os.path.join(STANDUP_DIR, f"{datetime.now(timezone.utc).date().isoformat()}.md")


def yesterday_path():
    from datetime import timedelta

    y = datetime.now(timezone.utc).date() - timedelta(days=1)
    return os.path.join(STANDUP_DIR, f"{y.isoformat()}.md")


def session_activity(session_id):
    """Summarize this session's file touches from session_logger.py's log,
    if present."""
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
    return files


def append_standup_entry(session_id):
    files = session_activity(session_id)
    if not files:
        return

    os.makedirs(STANDUP_DIR, exist_ok=True)
    unique_files = sorted(set(files))
    entry = f"- {datetime.now(timezone.utc).strftime('%H:%M')} UTC: {len(unique_files)}개 파일 작업 - " + ", ".join(
        unique_files[:10]
    )
    if len(unique_files) > 10:
        entry += f" 외 {len(unique_files) - 10}개"

    with open(today_path(), "a") as f:
        f.write(entry + "\n")


def read_yesterday_summary():
    path = yesterday_path()
    if not os.path.isfile(path):
        return None
    with open(path, errors="ignore") as f:
        return f.read().strip() or None


def handle_session_start(data):
    if data.get("source") != "startup":
        sys.exit(0)

    summary = read_yesterday_summary()
    if not summary:
        sys.exit(0)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"어제 작업 요약 (standup-autopilot):\n{summary}",
                }
            }
        )
    )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = data.get("hook_event_name", "")

    if event == "SessionStart":
        handle_session_start(data)
    elif event in ("Stop", "SessionEnd"):
        append_standup_entry(data.get("session_id"))

    sys.exit(0)


if __name__ == "__main__":
    main()
