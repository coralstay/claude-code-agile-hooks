#!/usr/bin/env python3
# ---
# title: nerf_receipts
# description: 모델 버전별 실패율·수정 반복·토큰을 기록해 모델 교체 뒤의 변화를 알리는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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
    except OSError:  # ---- 1
        return None, None

    for line in reversed(lines[-200:]):  # ---- 2
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":  # ---- 3
            continue
        message = entry.get("message", {})
        model = message.get("model")
        usage = message.get("usage")
        if model and usage:
            return model, usage
    return None, None


def sum_tokens(usage):
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    for iteration in usage.get("iterations", []) or []:  # ---- 4
        for key in totals:
            totals[key] += iteration.get(key, 0) or 0
    return totals


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    model, usage = latest_assistant_usage(data.get("transcript_path", ""))  # ---- 5

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id"),
        "event": event,
        "model": model,
        "tokens": sum_tokens(usage) if usage else None,
    }

    if event == "PostToolUseFailure":  # ---- 6
        record["tool_name"] = data.get("tool_name")
        record["failed"] = True
    elif event == "PostToolUse":
        record["tool_name"] = data.get("tool_name")
        if (data.get("tool_input") or {}).get("file_path"):
            record["file_path"] = data["tool_input"]["file_path"]

    append_log(record)  # ---- 7
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 트랜스크립트를 못 읽으면 (None, None)
#   설명: 모델·토큰 없이도 이벤트 기록은 계속된다. 로그 훅이 읽기 오류로 실패하지 않는다.
#   개념: fail-open
# 2 끝의 200줄만 역순으로
#   설명: 최신 assistant 메시지를 찾는 데 전체를 파싱할 필요가 없다. 큰 트랜스크립트에서도 호출당 비용이 일정하다.
#   개념: 성능
# 3 assistant 메시지에서만 모델·사용량
#   설명: 모델과 usage는 API 응답이 그대로 되돌려진 것이라 자기 보고가 아니다. 다른 종류의 줄은 건너뛴다.
# 4 iterations 합산
#   설명: usage.iterations 배열의 입력·출력·캐시 토큰을 더한다. 값이 None이어도 0으로 취급해 합산이 깨지지 않는다.
# 5 훅 시점의 마지막 사용량
#   설명: 이벤트 시각에 트랜스크립트에서 가장 최근의 모델과 usage를 붙인다. 도구 호출 단위의 정확한 토큰이 아니라 그 시점의 최근 턴 값이다.
#   개념: 근사치
# 6 실패 이벤트 구분
#   설명: PostToolUseFailure는 failed=true로 남겨 사후에 실패율을 모델 버전별로 셀 수 있게 한다.
#   개념: 실패율
# 7 항상 한 줄 기록 후 exit 0
#   설명: 기록 훅이므로 결정을 내리지 않는다. 추가 전용 JSONL에 이벤트마다 한 줄을 남긴다.
#   개념: append-only
