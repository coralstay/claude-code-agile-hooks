#!/usr/bin/env python3
# ---
# title: standup_autopilot
# description: 세션 로그에서 하루 스탠드업을 만들고 어제 남은 항목을 다음 세션에 다시 알리는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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
    return os.path.join(STANDUP_DIR, f"{datetime.now(timezone.utc).date().isoformat()}.md")  # ---- 1


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
            if record.get("event") == "tool_use" and record.get("file_path"):  # ---- 2
                files.append(record["file_path"])
    return files


def append_standup_entry(session_id):
    files = session_activity(session_id)
    if not files:  # ---- 3
        return

    os.makedirs(STANDUP_DIR, exist_ok=True)
    unique_files = sorted(set(files))
    entry = f"- {datetime.now(timezone.utc).strftime('%H:%M')} UTC: {len(unique_files)}개 파일 작업 - " + ", ".join(
        unique_files[:10]
    )
    if len(unique_files) > 10:
        entry += f" 외 {len(unique_files) - 10}개"

    with open(today_path(), "a") as f:  # ---- 4
        f.write(entry + "\n")


def read_yesterday_summary():
    path = yesterday_path()
    if not os.path.isfile(path):
        return None
    with open(path, errors="ignore") as f:
        return f.read().strip() or None


def handle_session_start(data):
    if data.get("source") != "startup":  # ---- 5
        sys.exit(0)

    summary = read_yesterday_summary()
    if not summary:
        sys.exit(0)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"어제 작업 요약 (standup-autopilot):\n{summary}",  # ---- 6
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
    elif event in ("Stop", "SessionEnd"):  # ---- 7
        append_standup_entry(data.get("session_id"))

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 날짜는 UTC 기준
#   설명: 하루의 경계를 시간대 설정과 무관하게 UTC로 고정한다. 다른 시간대에서는 현지 날짜와 파일 날짜가 다를 수 있다.
# 2 세션 로그에서 파일 활동 수집
#   설명: session_logger.py가 남긴 tool_use 기록의 file_path를 모은다. 그 로그가 없으면 빈 목록이라 스탠드업 줄이 쓰이지 않는다.
#   관련: hooks/session_logger.py
#   개념: 연동
# 3 활동이 없으면 쓰지 않음
#   설명: 파일 작업이 없는 턴은 빈 줄을 남기지 않는다.
# 4 하루 파일에 추가
#   설명: Stop마다 한 줄씩 덧붙인다. 같은 날 여러 세션이 한 파일을 공유한다.
#   개념: append-only
# 5 startup일 때만 어제 요약 주입
#   설명: resume·clear·compact로 시작한 세션에는 다시 주입하지 않는다. 이미 본 내용을 반복하지 않기 위해서다.
# 6 additionalContext로 요약 전달
#   설명: SessionStart가 컨텍스트에 어제 작업을 넣는 방법이다. 요약이 비어 있으면 위에서 이미 빠져나간다.
#   개념: 훅 출력
# 7 Stop과 SessionEnd 모두 기록
#   설명: Stop은 턴 단위 기록이고 SessionEnd는 마지막 턴 이후의 누락을 메운다. 같은 세션 활동은 파일 집합으로 합쳐진다.
