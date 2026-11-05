#!/usr/bin/env python3
"""PostToolUse + PostToolUseFailure + Stop
Personal flight recorder: records failure rate, edit churn, and tokens/task
by model version, flagging real shifts when the model changes. Ported from
karanb192/claude-code-hooks' nerf-receipts plugin (MIT license).

Token/model data comes from the same technique verified in this session's
own transcript: assistant messages carry message.model and
message.usage.iterations[].{input_tokens,output_tokens,
cache_read_input_tokens,cache_creation_input_tokens} - the actual API
response echoed back by the application, not a self-report.

Output: one JSONL record per PostToolUse/PostToolUseFailure/Stop event in
~/.claude/hooks-logs/nerf-receipts.jsonl.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/nerf-receipts.jsonl")


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def latest_assistant_usage(transcript_path):
    """Return (model, usage_dict) from the most recent assistant message in
    the transcript, or (None, None) if unavailable."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None, None

    try:
        with open(transcript_path, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None, None

    for line in reversed(lines[-200:]):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        model = message.get("model")
        usage = message.get("usage")
        if model and usage:
            return model, usage
    return None, None


def sum_tokens(usage):
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    for iteration in usage.get("iterations", []) or []:
        for key in totals:
            totals[key] += iteration.get(key, 0) or 0
    return totals


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    model, usage = latest_assistant_usage(data.get("transcript_path", ""))

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id"),
        "event": event,
        "model": model,
        "tokens": sum_tokens(usage) if usage else None,
    }

    if event == "PostToolUseFailure":
        record["tool_name"] = data.get("tool_name")
        record["failed"] = True
    elif event == "PostToolUse":
        record["tool_name"] = data.get("tool_name")
        if (data.get("tool_input") or {}).get("file_path"):
            record["file_path"] = data["tool_input"]["file_path"]

    append_log(record)
    sys.exit(0)


if __name__ == "__main__":
    main()
