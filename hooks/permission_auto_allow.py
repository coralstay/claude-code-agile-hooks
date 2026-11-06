#!/usr/bin/env python3
# ---
# title: permission_auto_allow
# description: 읽기 전용 도구·명령의 권한 요청을 자동 허용하는 PermissionRequest 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PermissionRequest
Auto-allow permission requests for read-only tools and commands, so Claude
Code doesn't stop to ask about calls that cannot change anything.

The scope is deliberately conservative:
- Read, Glob and Grep are always allowed.
- Bash is allowed only for a single plain command whose first word is one
  of ls, pwd, cat, echo, whoami, date, which, head, tail, wc, find, or for
  `git status|log|diff|show|branch|remote`. Any shell metacharacter
  (| ; & $ ` ( ) { } < >) or a newline disqualifies the command.
- Every other tool is left alone.
The hook never denies: it either allows or prints nothing, and the normal
permission prompt takes over.

This is this repository's own implementation.

Fully self-contained: no imports from any other file in this repo."""

import json
import sys

READ_ONLY_TOOLS = ("Read", "Glob", "Grep")
UNSAFE_CHARACTERS = frozenset("|;&$`(){}<>\n")  # ---- 1
SAFE_COMMANDS = frozenset(
    {"ls", "pwd", "cat", "echo", "whoami", "date", "which", "head", "tail", "wc", "find"}
)
SAFE_GIT_SUBCOMMANDS = frozenset({"status", "log", "diff", "show", "branch", "remote"})
REASON = "permission_auto_allow: read-only tool/command"


def is_safe_bash_command(command):
    if any(char in UNSAFE_CHARACTERS for char in command):
        return False
    words = command.split()
    if not words:
        return False
    if words[0] in SAFE_COMMANDS:
        return True
    if words[0] == "git":  # ---- 2
        return len(words) > 1 and words[1] in SAFE_GIT_SUBCOMMANDS
    return False


def should_auto_allow(tool_name, tool_input):
    if tool_name in READ_ONLY_TOOLS:
        return True
    if tool_name == "Bash":
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        return is_safe_bash_command(str(tool_input.get("command") or ""))
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    data = data if isinstance(data, dict) else {}

    if should_auto_allow(data.get("tool_name"), data.get("tool_input")):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PermissionRequest",
                        "permissionDecision": "allow",  # ---- 3
                        "permissionDecisionReason": REASON,
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 셸 메타문자는 모두 불합격
#   설명: 파이프·`;`·`&`·`$`·백틱·괄호·중괄호·리다이렉션·개행이 하나라도 있으면 읽기 전용이라 단정할 수 없어 자동 허용하지 않는다. 복합 명령에 쓰기 명령이 숨어 들어오는 길을 문자 수준에서 막는 보수적 선택이다.
#   관련: decision-1 (문자열 매칭의 한계)
# 2 git은 읽기 전용 하위 명령만
#   설명: git은 status·log·diff·show·branch·remote일 때만 허용한다. 첫 단어만 보므로 `git -C x ...`처럼 옵션이 먼저 오면 허용하지 않고 평소 권한 프롬프트로 넘어간다.
#   관련: backlog/drafts/draft-8 (자동 허용을 읽기 전용으로 좁히기)
# 3 허용만 하고 거부는 하지 않는다
#   설명: 이 훅은 allow를 출력하거나 아무것도 출력하지 않는다. 판단하지 못한 요청은 일반 권한 프롬프트가 이어받으므로 이 훅이 실수해도 사용자가 마지막 관문으로 남는다.
