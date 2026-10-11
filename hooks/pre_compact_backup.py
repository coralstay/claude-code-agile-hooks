#!/usr/bin/env python3
"""PreCompact
Back up the full session transcript right before compaction discards
context, so whatever the summary leaves out can still be read later.

Each backup is a byte-for-byte copy written to
~/.claude/hooks-logs/transcript_backups/<session_id>-<UTC %Y%m%dT%H%M%SZ>.jsonl
A missing or unreadable transcript path is skipped silently; the hook always
exits 0 and never blocks compaction.

This is this repository's own implementation.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

BACKUP_DIR = os.path.expanduser("~/.claude/hooks-logs/transcript_backups")


def backup_transcript(transcript_path, session_id):
    if not isinstance(transcript_path, str) or not os.path.isfile(transcript_path):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = os.path.join(BACKUP_DIR, f"{session_id}-{stamp}.jsonl")
    shutil.copyfile(transcript_path, dest)
    return dest


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    data = data if isinstance(data, dict) else {}

    backup_transcript(data.get("transcript_path"), data.get("session_id") or "unknown")
    sys.exit(0)


if __name__ == "__main__":
    main()
