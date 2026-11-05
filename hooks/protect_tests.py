#!/usr/bin/env python3
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

TEST_FILE_RE = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.py|[^/]+\.test\.[jt]sx?|[^/]+\.spec\.[jt]sx?)$"
)

SKIP_DECORATOR_RE = re.compile(
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
    is_delete = any(b in ("rm", "unlink") for b in basenames)
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
        content = tool_input.get("new_string", "")

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
