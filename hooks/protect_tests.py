#!/usr/bin/env python3
# ---
# title: protect_tests
# description: 테스트 파일 삭제·이름 변경·skip/xfail 비활성화로 가짜 통과를 만드는 것을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash|Edit|Write)
Stop "fake green": block deleting a test file, renaming a test file away
from a test-looking name, or disabling tests via skip/xfail decorators
instead of fixing the underlying code. Ported from karanb192/claude-code-hooks'
protect-tests plugin (MIT license).

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

TEST_FILE_RE = re.compile(  # ---- 1
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.py|[^/]+\.test\.[jt]sx?|[^/]+\.spec\.[jt]sx?)$"
)

SKIP_DECORATOR_RE = re.compile(  # ---- 2
    r"@pytest\.mark\.skip|@pytest\.mark\.xfail|\bpytest\.skip\(|test\.skip\(|it\.skip\(|describe\.skip\("
)


def is_test_file(path):
    if not path:
        return False
    return bool(TEST_FILE_RE.search(path.replace("\\", "/")))


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def check_bash(command):
    if not command:
        return
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    basenames = [os.path.basename(t) for t in tokens]
    is_delete = any(b in ("rm", "unlink") for b in basenames)  # ---- 3
    is_rename = "mv" in basenames

    if not (is_delete or is_rename):
        return

    paths = [
        t
        for t, b in zip(tokens, basenames)
        if not t.startswith("-") and b not in ("rm", "unlink", "mv")
    ]
    for path in paths:
        if is_test_file(path):
            action = "삭제" if is_delete else "이름 변경"
            deny(f"[protect-tests] 테스트 파일 {action}은 금지됩니다: {command}")


def check_write_or_edit(tool_name, tool_input):
    path = tool_input.get("file_path", "")
    if not is_test_file(path):
        return

    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:  # Edit
        content = tool_input.get("new_string", "")  # ---- 4

    if SKIP_DECORATOR_RE.search(content):
        deny(
            f"[protect-tests] 테스트를 고치는 대신 skip/xfail로 비활성화하는 것은 금지됩니다: {path}"
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}

    if tool_name == "Bash":
        check_bash(tool_input.get("command", ""))
    elif tool_name in ("Write", "Edit"):
        check_write_or_edit(tool_name, tool_input)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 테스트 파일 이름 규칙
#   설명: test_*.py, *_test.py, *.test.js/ts(x), *.spec.js/ts(x)를 테스트 파일로 본다. 이름을 바꿔 테스트가 아닌 척하는 우회(mv)는 check_bash가 대상 경로가 테스트 이름일 때 막는다.
#   개념: 가짜 통과(fake green): 코드를 고치지 않고 테스트를 지우거나 끄는 것
# 2 비활성화 표식
#   설명: pytest의 skip·xfail, JS의 test.skip·it.skip·describe.skip이 새로 써넣는 내용에 들어 있으면 테스트를 고치는 대신 끄는 것으로 본다.
# 3 삭제·이름 변경 명령 판정
#   설명: basename 비교라 `/bin/rm` 같은 절대 경로 호출도 잡는다. 삭제는 rm·unlink, 이름 변경은 mv다.
# 4 Edit은 바뀌는 조각만 검사
#   설명: Write는 전체 content를, Edit은 새로 들어가는 new_string만 검사한다. 기존에 있던 skip 데코레이터는 문제 삼지 않는다.
