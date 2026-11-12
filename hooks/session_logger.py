#!/usr/bin/env python3
# ---
# title: session_logger
# description: 세션의 프롬프트·파일·bash 명령을 JSONL로 영구 기록하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""SessionStart + UserPromptSubmit + PostToolUse + SessionEnd
Writes a durable JSONL log of everything that happens in a session: cwd, git
branch, every prompt submitted, every file touched, every bash command run
(secrets best-effort redacted). Ported from karanb192/claude-code-hooks'
session-logger plugin (MIT license). UserPromptSubmit prompt logging is this
repository's own implementation, written into the same log as one more event type.

CC_SESSION_LOG_DIR overrides the log directory (e.g. point it at an Obsidian
vault); defaults to ~/.claude/hooks-logs/sessions/.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SECRET_VALUE_RE = re.compile(  # ---- 1
    r"(api[_-]?key|token|secret|password|passwd)(\s*[:=]\s*)(\S+)", re.IGNORECASE
)


def redact(command):
    return SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", command)


def log_dir():
    return os.environ.get("CC_SESSION_LOG_DIR") or os.path.expanduser("~/.claude/hooks-logs/sessions")  # ---- 2


def log_path(session_id):
    return os.path.join(log_dir(), f"{session_id or 'unknown'}.jsonl")  # ---- 3


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None  # ---- 4


def append_entry(session_id, entry):
    path = log_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with open(path, "a") as f:  # ---- 5
        f.write(json.dumps(entry) + "\n")


def handle_session_start(data):
    cwd = data.get("cwd", "")
    append_entry(
        data.get("session_id"),
        {"event": "session_start", "cwd": cwd, "branch": current_branch(cwd)},
    )


def handle_user_prompt_submit(data):
    append_entry(
        data.get("session_id"),
        {"event": "prompt", "prompt": data.get("prompt", "")},
    )


def handle_post_tool_use(data):
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    entry = {"event": "tool_use", "tool_name": tool_name}

    if tool_name in ("Edit", "Write"):
        entry["file_path"] = tool_input.get("file_path")
    elif tool_name == "Bash":
        entry["command"] = redact(tool_input.get("command", ""))  # ---- 6

    append_entry(data.get("session_id"), entry)


def handle_session_end(data):
    append_entry(
        data.get("session_id"),
        {"event": "session_end", "reason": data.get("reason")},
    )


HANDLERS = {
    "SessionStart": handle_session_start,
    "UserPromptSubmit": handle_user_prompt_submit,
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
# 1 시크릿 값 마스킹 패턴
#   설명: api key·token·secret·password 뒤의 `:`/`=` 다음 값을 가린다. 키워드 기반 최선 노력이라 패턴에 안 맞는 비밀은 그대로 로그에 남는다.
#   개념: best-effort 마스킹
# 2 로그 위치는 환경변수로 교체 가능
#   설명: CC_SESSION_LOG_DIR로 Obsidian 볼트 같은 곳에 쌓을 수 있다. 다른 훅(dead_end_registry, standup_autopilot, pr_provenance_stamp)은 기본 위치의 이 로그를 읽는다.
#   관련: hooks/dead_end_registry.py, hooks/standup_autopilot.py, hooks/pr_provenance_stamp.py
#   개념: 연동
# 3 세션 ID 없으면 unknown
#   설명: ID가 비어 있어도 어딘가에는 남긴다. 세션 ID 하나가 파일 하나이므로 세션끼리 기록이 섞이지 않는다.
# 4 git 실패는 None
#   설명: git 저장소가 아니거나 git이 없으면 빈 출력이라 None이 된다. 검사하지 않으므로 세션 시작을 막지 않는다.
#   개념: fail-open
# 5 추가 전용 JSONL
#   설명: 세션당 파일 하나에 이벤트를 덧붙인다. 다른 훅이 줄 단위로 읽으므로 기존 줄을 고치지 않는다.
#   개념: append-only
# 6 Bash 명령만 마스킹해 기록
#   설명: 명령은 redact를 거쳐 남긴다. 프롬프트는 가공 없이 그대로 기록되어, 마스킹은 명령에만 적용된다는 점을 알고 써야 한다.
#   개념: 프라이버시
# 7 입력이 깨지면 통과
#   설명: 로그 기록 훅이 세션을 방해하지 않도록 파싱 실패는 조용히 끝낸다.
#   개념: fail-open
