#!/usr/bin/env python3
# ---
# title: context_hogs
# description: 도구 결과의 대략적인 토큰 비용을 파일별로 집계해 컨텍스트 소모 순위를 만드는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PostToolUse (matcher: Read|Grep|Glob|Bash)
Per-file context-cost leaderboard: attributes each tool result's approximate
token cost to the file(s) it loaded, so you can see which files cost the
most context over a session. Ported from karanb192/claude-code-hooks'
context-hogs plugin (MIT license).

Token cost is approximated from the tool response's character count
(chars / 4, the common rough estimate for English/code text) rather than
requiring a real tokenizer dependency - this hook stays stdlib-only like
every other hook in this repo, at the cost of exact precision. Good enough
for a relative leaderboard, which is the whole point.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/context-hogs.jsonl")

CHARS_PER_TOKEN = 4


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)  # ---- 1


def response_text(tool_response):
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        for key in ("content", "output", "stdout", "result"):
            value = tool_response.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(tool_response)  # ---- 2
    return ""


def files_for_tool(tool_name, tool_input):
    if tool_name == "Read":
        path = tool_input.get("file_path")
        return [path] if path else []
    if tool_name == "Glob":  # ---- 3
        return []  # a file listing, not file contents - no single file to attribute cost to
    if tool_name == "Grep":
        path = tool_input.get("path")
        return [path] if path else []
    if tool_name == "Bash":
        return []  # no single file; command output isn't attributable to one path
    return []


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def leaderboard():
    """Aggregate the log into {file_path: total_tokens}, most expensive first."""
    if not os.path.isfile(LOG_PATH):
        return []
    totals = {}
    with open(LOG_PATH, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") != "cost":
                continue
            path = record.get("file_path")
            tokens = record.get("tokens", 0)
            if path:
                totals[path] = totals.get(path, 0) + tokens
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)  # ---- 4


def handle_post_tool_use(data):
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    tokens = estimate_tokens(response_text(data.get("tool_response")))
    if tokens == 0:  # ---- 5
        return

    for path in files_for_tool(tool_name, tool_input):
        append_log(  # ---- 6
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "cost",
                "session_id": data.get("session_id"),
                "file_path": path,
                "tokens": tokens,
            }
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("hook_event_name") == "PostToolUse":
        handle_post_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 글자 수 / 4로 토큰 근사
#   설명: 토크나이저 의존성 없이 stdlib만 쓰기 위해 영어·코드의 일반적 어림값을 쓴다. 파일 간 상대 순위가 목적이라 정확도는 포기한다. 최소 1을 돌려 빈 응답과 구분한다.
#   개념: 근사치
# 2 알 수 없는 dict 응답은 통째로 직렬화
#   설명: content·output·stdout·result 키가 하나도 없으면 JSON 문자열의 길이로 비용을 센다. 응답 형태가 도구마다 달라서다.
#   개념: 방어적 파싱
# 3 Glob은 귀속 파일 없음
#   설명: 목록은 파일 내용이 아니라서 한 파일에 비용을 지울 수 없다. Bash도 같은 이유로 비워 둔다. 그래서 순위표에는 Read와 Grep 대상만 오른다.
# 4 비싼 파일 순 정렬
#   설명: 로그를 읽을 때마다 파일별 토큰 합을 내림차순으로 집계한다. 로그는 이벤트만 쌓고 합계는 저장하지 않는다.
# 5 비용 0이면 기록 안 함
#   설명: 빈 응답으로 로그를 늘리지 않는다.
# 6 파일마다 비용 한 줄
#   설명: 한 호출이 여러 파일을 가리켜도 같은 토큰 수가 각각에 붙는다. 이벤트는 추가 전용 JSONL이다.
#   개념: append-only
