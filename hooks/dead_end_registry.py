#!/usr/bin/env python3
# ---
# title: dead_end_registry
# description: 시도했다 되돌린 접근과 이유를 기억해 같은 막다른 길로 다시 들어가기 전에 경고하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""UserPromptSubmit + PreToolUse(Edit|Write)
Remembers approaches that were tried and reverted (with a reason), and warns
before retrying the same dead end. Ported from karanb192/claude-code-hooks'
dead-end-registry plugin (MIT license).

Registration is manual by design (upstream is the same): the user tells the
agent "that didn't work because X" in a prompt matching a "revert" pattern
(mentions undo/revert/rollback/dead end), which UserPromptSubmit records
against the current file(s) recently edited this session. On the next
Edit/Write to a file with a registered dead end, PreToolUse warns (doesn't
block - this is advisory) via additionalContext... but PreToolUse doesn't
support additionalContext for blocking events, so the warning goes to
stderr on allow (visible in the debug log) plus is always recorded so
`/dead-end-registry:dead-ends`-style tooling (not built here) could render it.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys
from datetime import datetime, timezone

REGISTRY_PATH = os.path.expanduser("~/.claude/hooks-logs/dead-end-registry.jsonl")

REVERT_MENTION_RE = re.compile(
    # \b works for space-delimited English words but not for Korean, where a
    # verb stem (e.g. 되돌-) fuses directly with its conjugation ending with
    # no boundary in between - so the Korean alternatives skip \b entirely.
    r"(?:\b(?:revert|undo|rollback)\b|되돌|취소|롤백).{0,120}(?:\b(?:because|since)\b|이유|때문에)",  # ---- 1
    re.IGNORECASE,
)


def append_registry(record):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "a") as f:  # ---- 2
        f.write(json.dumps(record) + "\n")


def recent_files_for_session(session_id, limit=5):
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
            if record.get("event") == "tool_use" and record.get("file_path"):
                files.append(record["file_path"])
    return files[-limit:]


def dead_ends_for_file(file_path):
    if not os.path.isfile(REGISTRY_PATH):
        return []
    entries = []
    with open(REGISTRY_PATH, errors="ignore") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("file_path") == file_path:
                entries.append(record)
    return entries


def handle_user_prompt_submit(data):
    prompt = data.get("prompt", "")
    if not REVERT_MENTION_RE.search(prompt):  # ---- 3
        sys.exit(0)

    files = recent_files_for_session(data.get("session_id"))  # ---- 4
    for file_path in files:
        append_registry(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": file_path,
                "reason": prompt,
            }
        )
    sys.exit(0)


def handle_pre_tool_use(data):
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    dead_ends = dead_ends_for_file(file_path)
    if dead_ends:
        latest = dead_ends[-1]
        print(  # ---- 5
            f"[dead-end-registry] '{file_path}'에 이전에 되돌린 접근이 있습니다: {latest['reason']}",
            file=sys.stderr,
        )
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:  # ---- 6
        sys.exit(0)

    event = data.get("hook_event_name", "")
    if event == "UserPromptSubmit":
        handle_user_prompt_submit(data)
    elif event == "PreToolUse":
        handle_pre_tool_use(data)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 되돌림 + 이유 문장만 등록
#   설명: '되돌/취소/롤백/revert/undo/rollback' 뒤에 '때문에/이유/because/since'가 이어지는 프롬프트만 막다른 길로 기록한다. 한글 쪽 대안은 어간에 어미가 붙어 \b 경계가 없어 \b를 쓰지 않는다. 등록은 사용자가 이유를 말할 때만 일어나는 수동 방식이다.
#   개념: 의도적 수동 등록
# 2 추가 전용 레지스트리
#   설명: 타임스탬프·파일·이유를 한 줄씩 덧붙이기만 한다. 같은 파일에 여러 건이 쌓이고 조회는 마지막 건을 쓴다.
#   개념: append-only
# 3 되돌림 언급이 아니면 통과
#   설명: 대부분의 프롬프트는 여기서 끝난다. 파일 기록을 읽지 않는다.
# 4 최근 편집 파일에 귀속
#   설명: 프롬프트가 어느 파일의 실패인지 말하지 않으므로 세션 로그에서 최근 5개 파일에 같은 이유를 붙인다. 정확하지 않은 추정이며 session_logger의 로그가 없으면 기록이 비어 있다.
#   관련: hooks/session_logger.py
#   개념: 휴리스틱
# 5 경고만 하고 막지 않는다
#   설명: PreToolUse는 막는 이벤트라 additionalContext를 지원하지 않는다. 그래서 허용(exit 0)하면서 stderr로만 알린다. 자문 성격의 기능이다.
#   개념: advisory
# 6 입력이 깨지면 통과
#   설명: 경고 기능이 편집을 막는 일이 없도록 파싱 실패는 조용히 끝낸다.
#   개념: fail-open
