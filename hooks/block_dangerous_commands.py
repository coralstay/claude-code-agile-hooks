#!/usr/bin/env python3
# ---
# title: block_dangerous_commands
# description: 치명적이거나 위험도 높은 셸 명령을 실행 전에 막는 PreToolUse 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash)
Block catastrophic/high-risk shell commands before they run. Ported from
karanb192/claude-code-hooks' block-dangerous-commands plugin (MIT license),
scope narrowed: "force push to main" is owned exclusively by
pre_git_safety_check.py to avoid the duplicate rule that exists in the
upstream project itself (see plan's "겹침 정리" #1).

HOOK_SAFETY_LEVEL env var picks the ruleset: critical (default) | high | strict.
Unknown values fall back to critical.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys

_FLAG_TOKEN = r"(?:-[a-zA-Z]+|--[a-zA-Z-]+)"  # ---- 1
_RECURSIVE_FLAG = r"(?:-[a-zA-Z]*r[a-zA-Z]*|--recursive)\b"
_FORCE_FLAG = r"(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\b"

RM_RF_FLAGS = (  # ---- 2
    rf"(?=(?:{_FLAG_TOKEN}\s+)*{_RECURSIVE_FLAG})"
    rf"(?=(?:{_FLAG_TOKEN}\s+)*{_FORCE_FLAG})"
    rf"(?:{_FLAG_TOKEN}\s+)*{_FLAG_TOKEN}"
)

CRITICAL_PATTERNS = [
    (
        rf"rm\s+{RM_RF_FLAGS}\s+(/|~|\$HOME)\s*($|/\s*$)",
        "rm -rf on root or home",
    ),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bdd\s+.*of=/dev/(disk|sda|nvme|rdisk)", "dd writing directly to a disk device"),
    (r"\bmkfs(\.\w+)?\s+/dev/", "formatting a device"),
]

HIGH_PATTERNS = CRITICAL_PATTERNS + [
    (r"\bcurl\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b", "curl | sh"),
    (r"\bwget\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b", "wget | sh"),
    (r"git\s+reset\s+--hard\b", "git reset --hard"),
    (
        rf"rm\s+{RM_RF_FLAGS}[^;&|\n]*?(?:^|[\s/])\.\.(?=/|$|\s)",  # ---- 3
        "rm -rf escaping the current directory via ..",
    ),
    (
        rf"rm\s+{RM_RF_FLAGS}[^;&|\n]*?(?:^|\s)/(?!tmp\b|var/tmp\b|private/tmp\b|var/folders\b|dev/null\b|\s|$)\S+",  # ---- 4
        "rm -rf on an absolute path outside common safe/temp directories",
    ),
]

STRICT_PATTERNS = HIGH_PATTERNS + [
    (r"\bsudo\s+rm\b", "sudo rm"),
    (r"\bdocker\s+(system\s+)?prune\b", "docker prune"),
]

LEVELS = {
    "critical": CRITICAL_PATTERNS,
    "high": HIGH_PATTERNS,
    "strict": STRICT_PATTERNS,
}


def get_patterns():
    level = os.environ.get("HOOK_SAFETY_LEVEL", "critical")
    return LEVELS.get(level, CRITICAL_PATTERNS)  # ---- 5


def find_violation(command):
    for pattern, reason in get_patterns():
        if re.search(pattern, command, re.IGNORECASE):  # ---- 6
            return reason
    return None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    violation = find_violation(command)
    if violation:
        deny(
            f"[block-dangerous-commands] 위험한 명령이 차단되었습니다: {violation}\n명령: {command}"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 플래그 토큰 정규식
#   설명: 짧은 형태(-r, -rf, -Rf, -v ...)나 GNU 긴 형태(--recursive, --force, --verbose ...) 하나. `rm` 뒤의 플래그 묶음을 훑을 때와, 아래 두 lookahead 안에서 상관없는 플래그를 건너뛰며 재귀·강제 표시를 찾을 때 둘 다 쓴다.
# 2 rm -rf 플래그를 철자에 상관없이 잡는 정규식
#   설명: 재귀(-r)이면서 강제(-f)인 `rm` 플래그를 어떻게 쓰든 잡는다. 합친 짧은 토큰(-rf, -fr, -Rf, -RF), 따로 쓴 단어(-r -f, -f -r, -r -v -f), GNU 긴 플래그(--recursive --force)를 순서·대소문자 무관하게 받는다. 두 lookahead가 플래그 묶음을 앞으로 훑으며 재귀·강제 토큰이 둘 다 있는지 확인하고, 마지막 패턴이 묶음 전체를 소비해 호출부의 `\s+`와 맞물린다. 대소문자 무시는 find_violation의 re.IGNORECASE가 맡는다(-Rf, --RECURSIVE).
#   관련: hooks/pre_git_safety_check.py (git 쪽 파괴적 규칙은 그 훅이 전담)
#   개념: lookahead: 문자를 소비하지 않고 뒤따르는 패턴만 확인하는 정규식 구문
# 3 상위 디렉터리로 빠져나가는 rm -rf
#   설명: `rm -rf ../`, `../../foo`, `./dir/../../x`처럼 `..`으로 현재 디렉터리 밖을 겨냥한 삭제. 일부러 근사 판정이며, 무관한 `&&`·`;`·`|` 너머의 다른 명령까지 넘어가지 않도록 셸 한 구간(`[^;&|\n]`)으로 범위를 제한했다.
# 4 안전 목록 밖 절대 경로 rm -rf
#   설명: 흔한 임시 디렉터리(/tmp, /var/tmp, /private/tmp, /var/folders, /dev/null) 밖의 절대 경로를 겨냥한 삭제. 명령 문자열만으로는 실제 cwd를 알 수 없으므로 증명이 아니라 실용적 근사다.
# 5 알 수 없는 수준은 critical로
#   설명: HOOK_SAFETY_LEVEL(critical·high·strict)이 오타이거나 비어 있으면 가장 좁은 critical 규칙집합으로 되돌아간다.
#   관련: 위 LEVELS 표
# 6 대소문자 무시 매칭
#   설명: 모든 패턴을 re.IGNORECASE로 돌린다. 그래서 RM_RF_FLAGS는 -Rf·-RF·--RECURSIVE를 별도 처리하지 않고도 잡는다.
