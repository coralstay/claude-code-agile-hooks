#!/usr/bin/env python3
# ---
# title: config_watch
# description: 세션 중 설정 변경을 눈에 띄게 알리거나 차단하는 ConfigChange 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""ConfigChange (matcher: user_settings|project_settings|local_settings|policy_settings|skills)
Make every mid-session config change loudly visible (default) or block it
outright with CONFIG_WATCH_BLOCK=true. Catches out-of-band settings.json
writes made by something other than the agent itself (config_guard.py
covers the agent's own edits; this covers everything else - e.g. the
CHAINDROP npm worm's persistence trick of rewriting settings.json from a
malicious dependency's postinstall script). Ported from
karanb192/claude-code-hooks' config-watch plugin (MIT license).

The ConfigChange payload schema isn't fully documented upstream, so this
parses defensively: known fields are used if present, and the whole raw
event is always logged regardless.

policy_settings changes are never blocked (managed/enterprise settings are
outside what this session should be overriding) - only warned about.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/config-watch.jsonl")  # ---- 1


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    config_type = data.get("source") or data.get("config_type") or "unknown"
    file_path = data.get("file_path") or data.get("file") or "unknown"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_type": config_type,
        "file_path": file_path,
        "raw": data,
    }
    append_log(record)

    should_block = os.environ.get("CONFIG_WATCH_BLOCK") == "true" and config_type != "policy_settings"  # ---- 2

    if should_block:
        deny(f"[config-watch] 세션 중 설정 변경이 감지되어 차단되었습니다: {config_type} ({file_path})")

    print(f"[config-watch] 설정 변경 감지: {config_type} ({file_path})", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 원본 이벤트는 항상 기록
#   설명: ConfigChange 페이로드의 스키마가 업스트림에서도 다 문서화돼 있지 않아, 알려진 필드는 있으면 쓰고 이벤트 전체(raw)는 차단 여부와 무관하게 늘 로그에 남긴다.
# 2 policy_settings는 절대 차단하지 않는다
#   설명: 기본은 경고만, CONFIG_WATCH_BLOCK=true일 때만 차단한다. 관리형(엔터프라이즈) 정책 설정은 이 세션이 덮어쓸 대상이 아니므로 차단 모드에서도 경고만 한다.
#   관련: hooks/config_guard.py (에이전트 자신의 편집은 그쪽이, 그 밖의 변경은 이 훅이 맡는다)
