#!/usr/bin/env python3
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
ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")
TAG_CHAR_RE = re.compile("[\U000e0000-\U000e007f]")
VARIATION_SELECTOR_RUN_RE = re.compile("[︀-️\U000e0100-\U000e01ef]{3,}")
BIDI_OVERRIDE_RE = re.compile("[‪-‮⁦-⁩]")

SECRET_EXFIL_RE = re.compile(
    r"\b(cat|read|print|export|upload|send)\b.{0,40}(\.env\b|secrets?\b|credentials?\b|api[_-]?key\b)",
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

LEVELS = {"critical": CRITICAL_CHECKS, "high": HIGH_CHECKS, "strict": STRICT_CHECKS}


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
    return os.path.join(os.path.expanduser("~/.claude/hooks-logs"), f"instructions-audit-lock-{safe_id}.json")


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
    except (json.JSONDecodeError, OSError):
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
    if os.environ.get("HOOK_AUDIT_WARN_ONLY") == "true":
        print(message, file=sys.stderr)
        sys.exit(0)

    write_lock(session_id, reason, line, file_path)
    print(message, file=sys.stderr)
    sys.exit(0)  # InstructionsLoaded's exit code/continue is ignored upstream


def handle_enforcement(data):
    session_id = data.get("session_id", "")
    lock = read_lock(session_id)
    if lock:
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
        sys.exit(0)

    event = data.get("hook_event_name", "")

    if event == "InstructionsLoaded":
        handle_instructions_loaded(data)
    else:
        handle_enforcement(data)


if __name__ == "__main__":
    main()
