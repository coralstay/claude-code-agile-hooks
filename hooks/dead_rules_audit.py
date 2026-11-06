#!/usr/bin/env python3
# ---
# title: dead_rules_audit
# description: CLAUDE.md 규칙을 Claude가 지키는지 무시하는지 집계해 훅으로 승격할 규칙을 알리는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/dead-rules-audit.jsonl")  # ---- 1

RULE_LINE_RE = re.compile(r"^\s*[-*]?\s*(Do |Don't |Never |Always |Use )", re.IGNORECASE)  # ---- 2


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
    with open(LOG_PATH, "a") as f:  # ---- 3
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
                if record.get("session_id") != session_id:  # ---- 4
                    continue
                if record.get("event") == "edit":
                    edit_count += 1
                elif record.get("event") == "session_start":
                    rule_count = record.get("rule_count", 0)  # ---- 5

    append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "scorecard",
            "session_id": session_id,
            "rule_count": rule_count,
            "edit_count": edit_count,
        }
    )


HANDLERS = {  # ---- 6
    "SessionStart": handle_session_start,
    "PostToolUse": handle_post_tool_use,
    "SessionEnd": handle_session_end,
}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # ---- 7

    handler = HANDLERS.get(data.get("hook_event_name", ""))
    if handler:
        handler(data)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 로그는 홈의 hooks-logs
#   설명: 사용자 전역 위치에 쌓아 프로젝트 저장소에 섞여 들어가지 않는다.
# 2 규칙 줄은 명령형 접두사로 판별
#   설명: Do·Don't·Never·Always·Use로 시작하는 줄만 규칙으로 본다. 휴리스틱이라 정확한 준수 판정이 아니라 사람의 주의를 끌 대략적 성적표 용도다.
#   개념: 휴리스틱
# 3 추가 전용 JSONL
#   설명: 이벤트마다 한 줄씩 덧붙이기만 한다. 세션 종료 때 이 로그를 다시 읽어 집계하므로 기존 줄을 고치지 않는다.
#   개념: append-only
# 4 자기 세션의 기록만 집계
#   설명: 로그는 모든 세션이 공유한다. 다른 세션의 편집이 이 세션의 성적표에 섞이지 않게 session_id로 거른다.
# 5 규칙 수는 session_start 기록에서
#   설명: CLAUDE.md는 세션 시작 때 한 번 읽어 개수만 남긴다. 종료 시점에 다시 읽지 않아 중간 편집의 영향을 받지 않는다.
# 6 이벤트별 처리기 표
#   설명: SessionStart는 규칙 수 기록, PostToolUse는 편집 기록, SessionEnd는 둘을 합친 성적표를 쓴다.
# 7 입력이 깨지면 통과
#   설명: 감사 기록용 훅이라 입력을 못 읽어도 사용자 작업은 계속된다.
#   개념: fail-open
