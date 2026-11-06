#!/usr/bin/env python3
# ---
# title: instructions_audit
# description: CLAUDE.md·규칙 파일의 숨은 유니코드와 적대적 지시를 로드 시점에 검사하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""InstructionsLoaded (matcher: any) + UserPromptSubmit + PreToolUse
Audit CLAUDE.md / .claude/rules/*.md content as it loads and lock the
session on hidden or hostile directives: invisible-Unicode smuggling
(zero-width characters, tag characters, variation-selector runs - the
TrapDoor supply-chain signature), bidi overrides, directives to read/exfil
secrets, curl|sh, decode-and-execute, or hook/settings tampering. Ported
from karanb192/claude-code-hooks' instructions-audit plugin (MIT license).

InstructionsLoaded itself has no decision control (its exit code and even
`continue: false` are ignored by current Claude Code builds), so detection
and enforcement are split, matching upstream's design:
- On InstructionsLoaded: scan the file, and if it's hostile, write a lock
  file recording which rule fired and at what line.
- On UserPromptSubmit and PreToolUse: if a lock file exists for this
  session, block every prompt/tool call until a human deletes it.

HOOK_AUDIT_LEVEL: critical|high|strict (default: high).
HOOK_AUDIT_WARN_ONLY=true: warn (print, don't lock) instead of locking.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys

# Explicit \u/\U escapes throughout - these characters are invisible or
# render inconsistently, so spelling them out avoids silent corruption of
# this file across editors/encodings.
ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")  # ---- 1
TAG_CHAR_RE = re.compile("[\U000e0000-\U000e007f]")
VARIATION_SELECTOR_RUN_RE = re.compile("[︀-️\U000e0100-\U000e01ef]{3,}")  # ---- 2
BIDI_OVERRIDE_RE = re.compile("[‪-‮⁦-⁩]")

SECRET_EXFIL_RE = re.compile(
    r"\b(cat|read|print|export|upload|send)\b.{0,40}(\.env\b|secrets?\b|credentials?\b|api[_-]?key\b)",  # ---- 3
    re.IGNORECASE,
)
CURL_PIPE_RE = re.compile(r"curl\b[^\n]{0,80}\|\s*(sudo\s+)?(sh|bash)\b")
DECODE_EXEC_RE = re.compile(r"base64\s+-d.{0,40}\|\s*(sh|bash)\b")
_HOOK_TAMPER_NOUN = r"(settings\.json|\.claude/hooks|hooks\.json)"
_HOOK_TAMPER_VERB = r"(modify|edit|delete|overwrite|change)"
HOOK_TAMPER_RE = re.compile(
    rf"\b{_HOOK_TAMPER_VERB}\b.{{0,40}}\b{_HOOK_TAMPER_NOUN}|"
    rf"\b{_HOOK_TAMPER_NOUN}\b.{{0,40}}\b{_HOOK_TAMPER_VERB}\b",
    re.IGNORECASE,
)

CRITICAL_CHECKS = [
    (ZERO_WIDTH_RE, "제로폭 유니코드 문자 은닉"),
    (TAG_CHAR_RE, "유니코드 태그 문자 은닉 (TrapDoor 시그니처)"),
    (VARIATION_SELECTOR_RUN_RE, "variation selector 연속 사용 (은닉 채널)"),
    (BIDI_OVERRIDE_RE, "bidi 방향 override 문자"),
]

HIGH_CHECKS = CRITICAL_CHECKS + [
    (SECRET_EXFIL_RE, "시크릿 파일 읽기/유출 지시"),
    (CURL_PIPE_RE, "curl | sh 계열 지시"),
]

STRICT_CHECKS = HIGH_CHECKS + [
    (DECODE_EXEC_RE, "base64 디코드 후 실행 지시"),
    (HOOK_TAMPER_RE, "훅/설정 변조 지시"),
]

LEVELS = {"critical": CRITICAL_CHECKS, "high": HIGH_CHECKS, "strict": STRICT_CHECKS}  # ---- 4


def get_checks():
    return LEVELS.get(os.environ.get("HOOK_AUDIT_LEVEL", "high"), HIGH_CHECKS)


def find_violation(content):
    for pattern, reason in get_checks():
        match = pattern.search(content)
        if match:
            line = content.count("\n", 0, match.start()) + 1
            return reason, line
    return None, None


def lock_path(session_id):
    safe_id = session_id or "unknown"
    return os.path.join(os.path.expanduser("~/.claude/hooks-logs"), f"instructions-audit-lock-{safe_id}.json")  # ---- 5


def write_lock(session_id, reason, line, file_path):
    path = lock_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"reason": reason, "line": line, "file": file_path}, f)


def read_lock(session_id):
    path = lock_path(session_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):  # ---- 6
        return None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def handle_instructions_loaded(data):
    content = data.get("content", "")
    file_path = data.get("file_path", "")
    session_id = data.get("session_id", "")

    reason, line = find_violation(content)
    if reason is None:
        sys.exit(0)

    message = f"[instructions-audit] {file_path}:{line} 에서 위험 신호 감지: {reason}"
    if os.environ.get("HOOK_AUDIT_WARN_ONLY") == "true":  # ---- 7
        print(message, file=sys.stderr)
        sys.exit(0)

    write_lock(session_id, reason, line, file_path)  # ---- 8
    print(message, file=sys.stderr)
    sys.exit(0)  # InstructionsLoaded's exit code/continue is ignored upstream


def handle_enforcement(data):
    session_id = data.get("session_id", "")
    lock = read_lock(session_id)
    if lock:  # ---- 9
        deny(
            f"[instructions-audit] 이 세션은 잠겨 있습니다 — {lock.get('file')}:{lock.get('line')}에서 "
            f"'{lock.get('reason')}' 발견. 사람이 파일을 고치거나 잠금 파일을 지울 때까지 모든 "
            f"프롬프트/툴 호출이 차단됩니다."
        )
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # ---- 10

    event = data.get("hook_event_name", "")

    if event == "InstructionsLoaded":
        handle_instructions_loaded(data)
    else:
        handle_enforcement(data)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 제로폭 문자 은닉 탐지
#   설명: 눈에 안 보이는 문자로 지시를 숨기는 공급망 공격을 잡는다. 문자를 이스케이프가 아닌 원문으로 적어 둔 줄이라 에디터가 조용히 바꾸지 않게 주의해야 한다.
#   개념: 유니코드 은닉
# 2 variation selector 연속 3개 이상
#   설명: 정상 이모지는 보통 하나만 붙는다. 3개 이상 이어지면 데이터를 실어 나르는 은닉 채널로 본다.
#   개념: TrapDoor 시그니처
# 3 시크릿 읽기·유출 지시
#   설명: 읽기·출력·전송 동사와 .env·secrets·credentials·api key가 가까이 있는 문장을 잡는다. 40자 거리 제한으로 오탐을 줄인다.
# 4 수준 선택 표
#   설명: critical은 은닉 문자만, high는 여기에 유출·curl|sh, strict는 디코드 실행과 훅 변조까지 본다. 수준이 높을수록 오탐 위험이 커진다.
#   개념: HOOK_AUDIT_LEVEL
# 5 세션별 잠금 파일 경로
#   설명: 세션 ID마다 잠금 파일이 따로여서 한 세션의 잠금이 다른 세션을 막지 않는다. ID가 없으면 unknown으로 모은다.
# 6 잠금 읽기 실패는 잠금 없음
#   설명: 깨진 잠금 파일로 세션이 영구히 막히지 않게 None을 돌려준다.
#   개념: fail-open
# 7 경고 전용 모드
#   설명: HOOK_AUDIT_WARN_ONLY=true면 메시지만 출력하고 잠그지 않는다. 도입 초기에 오탐을 관찰하는 용도다.
# 8 탐지와 집행의 분리
#   설명: InstructionsLoaded는 종료 코드와 continue 값이 무시되어 직접 막을 수 없다. 대신 잠금 파일을 남기고 뒤따르는 UserPromptSubmit·PreToolUse가 집행한다.
#   개념: 결정 제어 없는 이벤트
# 9 잠금이 있으면 모든 프롬프트·툴 호출 거부
#   설명: 사람이 파일을 고치거나 잠금 파일을 지울 때까지 풀리지 않는다. 자동으로 풀리면 공격이 한 번 지나가는 것만으로 우회된다.
#   개념: fail-closed
# 10 입력 JSON이 깨지면 통과
#   설명: 이 훅은 감사 용도라 입력을 못 읽으면 판정할 수 없다. 사용자 작업을 막지 않는다.
#   개념: fail-open
