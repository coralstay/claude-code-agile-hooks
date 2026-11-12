#!/usr/bin/env python3
# ---
# title: context_flags
# description: 세션 상태를 세션별 플래그 파일에 기록해 다른 훅이 읽게 하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""SessionStart + PreCompact + Stop
TASK-31 "context flags": hooks can't add fields to Claude Code's own hook
payload, so this hook keeps a tiny per-session flag file that other hooks
(or a human debugging a session) can read to learn session state the
payload of *their* event doesn't carry.

File: $CC_HOOK_FLAGS_DIR/<session_id>.json
      (default ~/.claude/hooks-logs/flags/<session_id>.json)

Schema (every key optional for readers - treat missing as "unknown"):
  session_id            str
  updated_at            ISO-8601 UTC, last write by any event
  last_start_source     SessionStart `source`: startup|resume|clear|compact
  post_compact          bool - context was compacted (SessionStart
                        source=compact); reset to false by startup/clear,
                        kept as-is by resume
  compacted_at          ISO-8601 UTC of the latest compaction
  compact_count         int, compactions seen in this session
  compact_trigger       PreCompact `trigger`: auto|manual
  pre_compact_at        ISO-8601 UTC of the latest PreCompact
  parallel_session      bool - Stop payload's `background_tasks` non-empty
  background_task_count int
  parallel_checked_at   ISO-8601 UTC of the latest Stop

Writes are atomic (temp file + os.replace) so concurrent writers never
leave a half-written file. Fail-open: any exception exits 0 - a flag
writer must never be the hook that paralyses a session.

Fully self-contained: no imports from any other file in this repo."""

import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone


def flags_dir():
    return os.environ.get("CC_HOOK_FLAGS_DIR") or os.path.expanduser(
        "~/.claude/hooks-logs/flags"
    )


def flags_path(session_id):
    name = os.path.basename(str(session_id or "")) or "unknown"  # ---- 1
    return os.path.join(flags_dir(), f"{name}.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def read_flags(session_id):
    try:
        with open(flags_path(session_id)) as f:
            flags = json.load(f)
    except (OSError, ValueError):  # ---- 2
        return {}
    return flags if isinstance(flags, dict) else {}


def write_flags(session_id, flags):
    path = flags_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(flags, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # ---- 3
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def background_tasks_running(data):
    """True if the Stop payload says background work is still running.
    The field's shape isn't documented, so any non-empty list/dict counts."""
    tasks = data.get("background_tasks")
    return isinstance(tasks, (list, dict)) and len(tasks) > 0  # ---- 4


def apply_session_start(flags, data):
    source = data.get("source")
    flags["last_start_source"] = source
    flags.setdefault("compact_count", 0)
    if source == "compact":
        flags["post_compact"] = True
        flags["compacted_at"] = now()
        flags["compact_count"] += 1
    elif source in ("startup", "clear") or "post_compact" not in flags:  # ---- 5
        flags["post_compact"] = False


def apply_pre_compact(flags, data):
    flags["compact_trigger"] = data.get("trigger")
    flags["pre_compact_at"] = now()


def apply_stop(flags, data):
    running = background_tasks_running(data)
    flags["parallel_session"] = running
    flags["background_task_count"] = len(data.get("background_tasks")) if running else 0
    flags["parallel_checked_at"] = now()


HANDLERS = {
    "SessionStart": apply_session_start,
    "PreCompact": apply_pre_compact,
    "Stop": apply_stop,
}


def update(data):
    handler = HANDLERS.get(data.get("hook_event_name", ""))  # ---- 6
    if not handler:
        return
    session_id = data.get("session_id")
    flags = read_flags(session_id)
    handler(flags, data)
    flags["session_id"] = session_id or "unknown"
    flags["updated_at"] = now()
    write_flags(session_id, flags)


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            update(data)
    except Exception:  # ---- 7
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 세션 ID를 basename으로 제한
#   설명: session_id가 `../` 같은 경로를 담아도 플래그 디렉터리 밖으로 나갈 수 없다. 비어 있으면 unknown 파일을 쓴다.
#   개념: 경로 순회 방어
# 2 읽기 실패는 빈 플래그
#   설명: 파일이 없거나 깨졌으면 {}로 시작해 이번 이벤트가 새로 채운다. 스키마의 모든 키는 읽는 쪽에서 선택 사항이다.
#   개념: fail-open
# 3 임시 파일에서 원자적 교체
#   설명: 플래그 파일은 다른 훅이나 사람이 언제든 읽는다. 쓰는 도중의 반쯤 쓴 파일이 보이지 않게 한다.
#   개념: 원자적 쓰기
# 4 background_tasks 형식은 문서화되지 않음
#   설명: 어떤 모양이든 비어 있지 않은 list/dict면 병렬 작업 중으로 본다. 형식이 바뀌어도 오탐 쪽으로 안전하게 기운다.
#   개념: 방어적 파싱
# 5 resume은 post_compact 유지
#   설명: startup·clear면 false로 되돌리고, resume이면 이전 값을 그대로 둔다. 압축 직후 이어 열린 세션이 압축 사실을 잃지 않는다.
#   개념: 상태 전이
# 6 처리 대상 이벤트만 갱신
#   설명: SessionStart, PreCompact, Stop이 아니면 파일을 건드리지 않는다.
# 7 모든 예외를 삼키고 exit 0
#   설명: 플래그를 쓰는 훅이 세션을 마비시키는 훅이 되면 안 된다.
#   개념: fail-open
