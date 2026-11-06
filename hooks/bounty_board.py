#!/usr/bin/env python3
# ---
# title: bounty_board
# description: TODO/FIXME/HACK 부채를 나이에 따라 커지는 XP 현상금으로 매기는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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
    except (json.JSONDecodeError, OSError):  # ---- 1
        return {}


def save_board(board):
    os.makedirs(os.path.dirname(BOARD_PATH), exist_ok=True)
    with open(BOARD_PATH, "w") as f:
        json.dump(board, f, indent=2)


def bounty_key(file_path, line_text):
    return f"{file_path}::{line_text.strip()}"  # ---- 2


def compute_xp(first_seen_iso):
    first_seen = datetime.fromisoformat(first_seen_iso)
    age_days = (datetime.now(timezone.utc) - first_seen).days
    return min(BASE_XP + XP_PER_DAY * age_days, MAX_XP)  # ---- 3


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
        if line_text not in current_markers:  # ---- 4
            cleared.append((key, compute_xp(record["first_seen"])))
            del board[key]

    for line_text in current_markers:
        key = bounty_key(file_path, line_text)
        if key not in board:  # ---- 5
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
    if not file_path or not os.path.isfile(file_path):  # ---- 6
        sys.exit(0)

    board = load_board()
    cleared = sync_file_markers(board, file_path)
    save_board(board)  # ---- 7

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
    elif event == "PostToolUse":  # ---- 8
        handle_post_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 깨진 현상금 파일은 빈 보드로
#   설명: 읽기 실패나 JSON 오류면 빈 dict로 시작한다. 부가 기능이 세션을 막지 않는다. 다음 저장 때 새 파일로 덮인다.
#   개념: fail-open
# 2 (파일, 줄 내용) 쌍이 현상금의 정체
#   설명: 줄 번호가 아니라 줄 내용으로 식별해서 위쪽에 줄이 추가돼 번호가 밀려도 같은 마커가 계속 나이를 먹는다. 줄 내용이 바뀌면 새 마커로 취급된다.
#   개념: 식별자
# 3 하루 2 XP씩, 상한 100
#   설명: 기본 10에 경과일 x 2를 더하고 MAX_XP에서 자른다. 오래 방치한 부채일수록 값이 커지되 무한히 커지지 않는다.
# 4 사라진 마커는 클리어
#   설명: 이전에 추적하던 줄이 현재 파일에 없으면 해결된 것으로 보고 현상금을 지급한 뒤 보드에서 뺀다. 줄을 고쳐 쓴 경우도 이전 마커의 클리어로 계산된다.
# 5 이미 있는 키는 first_seen을 유지
#   설명: 세션이 바뀌어도 나이가 초기화되지 않는다. 새 마커만 지금 시각으로 기록한다.
#   개념: 나이 보존
# 6 파일이 없으면 통과
#   설명: 삭제·이름 변경된 편집 대상이나 경로 없는 도구 입력은 스캔할 수 없다.
#   개념: fail-open
# 7 스캔 뒤 즉시 저장
#   설명: 편집마다 보드를 디스크에 반영한다. 세션이 갑자기 끝나도 지급과 새 마커 기록이 남는다.
# 8 PostToolUse는 클리어 판정 경로
#   설명: SessionStart는 상위 현상금을 컨텍스트로 알려 주고, 편집 직후에는 해당 파일의 마커만 동기화한다.
