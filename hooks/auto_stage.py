#!/usr/bin/env python3
# ---
# title: auto_stage
# description: Claude가 수정한 파일을 PostToolUse에서 자동으로 git add 하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PostToolUse (matcher: Edit|Write)
Automatically `git add` files Claude modifies, so `git status` always shows
exactly what Claude touched. Ported from karanb192/claude-code-hooks'
auto-stage plugin (MIT license).

Silently does nothing outside a git repo, or for a file that isn't inside
one (e.g. editing something under /tmp).

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import subprocess
import sys


def git_toplevel(path):
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    result = subprocess.run(
        ["git", "-C", directory, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def stage_file(path):
    toplevel = git_toplevel(path)
    if not toplevel:
        return False
    result = subprocess.run(["git", "-C", toplevel, "add", "--", path], capture_output=True, text=True)  # ---- 1
    return result.returncode == 0


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") not in ("Edit", "Write"):
        sys.exit(0)

    path = (data.get("tool_input") or {}).get("file_path", "")
    if path and os.path.isfile(path):
        stage_file(path)

    sys.exit(0)  # ---- 2


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 파일 하나만 stage
#   설명: `git add -A`가 아니라 `--` 뒤에 Edit/Write가 건드린 경로 하나만 넘긴다. 그래서 `git status`에는 Claude가 만진 파일만 나타난다.
#   개념: `--`는 뒤따르는 인자를 옵션이 아닌 경로로 고정한다
# 2 훅은 절대 실패하지 않는다
#   설명: JSON이 깨졌거나 도구가 Edit/Write가 아니거나 stage에 실패해도 항상 exit 0이다. PostToolUse 훅이라 작업을 막을 수단이 아니며, stage 실패가 세션을 방해해선 안 된다.
