#!/usr/bin/env python3
"""SessionStart + PostToolUse(Edit|Write)
Prices a repo's TODO/FIXME/HACK debt as aging XP bounties: a marker's value
grows the longer it sits unaddressed, and clearing one (removing the line
that contained it) pays out. Ported from karanb192/claude-code-hooks'
bounty-board plugin (MIT license).

XP formula: base 10 + 2 per day the marker has existed (capped at 100),
tracked by first-seen timestamp per (file, line content) pair so a marker
surviving across sessions keeps aging instead of resetting.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys
from datetime import datetime, timezone

BOARD_PATH = os.path.expanduser("~/.claude/hooks-logs/bounty-board.json")
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]?(.*)", re.IGNORECASE)
SKIP_MARKER_RE = re.compile(r"\bskip\b|@pytest\.mark\.skip", re.IGNORECASE)

BASE_XP = 10
XP_PER_DAY = 2
MAX_XP = 100


def load_board():
    if not os.path.isfile(BOARD_PATH):
        return {}
    try:
        with open(BOARD_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_board(board):
    os.makedirs(os.path.dirname(BOARD_PATH), exist_ok=True)
    with open(BOARD_PATH, "w") as f:
        json.dump(board, f, indent=2)


def bounty_key(file_path, line_text):
    return f"{file_path}::{line_text.strip()}"


def compute_xp(first_seen_iso):
    first_seen = datetime.fromisoformat(first_seen_iso)
    age_days = (datetime.now(timezone.utc) - first_seen).days
    return min(BASE_XP + XP_PER_DAY * age_days, MAX_XP)


def scan_markers(file_path):
    try:
        with open(file_path, errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return []
    markers = []
    for line in lines:
        if MARKER_RE.search(line):
            markers.append(line.rstrip("\n"))
    return markers


def sync_file_markers(board, file_path):
    """Add newly-seen markers to the board; return list of (key, xp) for
    markers that existed before this call but are gone now (cleared)."""
    current_markers = set(scan_markers(file_path))
    now = datetime.now(timezone.utc).isoformat()

    previously_tracked = {
        k: v for k, v in board.items() if k.startswith(f"{file_path}::")
    }
    cleared = []

    for key, record in previously_tracked.items():
        line_text = key.split("::", 1)[1]
        if line_text not in current_markers:
            cleared.append((key, compute_xp(record["first_seen"])))
            del board[key]

    for line_text in current_markers:
        key = bounty_key(file_path, line_text)
        if key not in board:
            board[key] = {"first_seen": now, "file": file_path}

    return cleared


def top_bounties(board, limit=3):
    scored = [(key, compute_xp(record["first_seen"])) for key, record in board.items()]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:limit]


def handle_session_start(data):
    board = load_board()
    top = top_bounties(board)
    if not top:
        sys.exit(0)
    lines = [f"- {key.split('::', 1)[1]} ({xp} XP)" for key, xp in top]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "미해결 부채 현상금 상위 항목 (bounty-board):\n" + "\n".join(lines),
                }
            }
        )
    )


def handle_post_tool_use(data):
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        sys.exit(0)

    board = load_board()
    cleared = sync_file_markers(board, file_path)
    save_board(board)

    for key, xp in cleared:
        print(f"[bounty-board] 현상금 클리어: {key.split('::', 1)[1]} (+{xp} XP)", file=sys.stderr)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    if event == "SessionStart":
        handle_session_start(data)
    elif event == "PostToolUse":
        handle_post_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()
