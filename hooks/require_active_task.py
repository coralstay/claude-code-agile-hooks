#!/usr/bin/env python3
# ---
# title: require_active_task
# description: backlog 프로젝트에서 In Progress 태스크를 읽기 전에는 Edit/Write를 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Edit|Write)
Phase 1.8 + Phase 3-0: don't let Claude edit files in a backlog.md project
unless a task is In Progress and its content has actually been read this
session (`backlog task view`), so references/documentation load naturally.

Fully self-contained: no imports from any other file in this repo, so a bug
in another hook can never break this one."""

import json
import os
import shutil
import subprocess
import sys


def has_command(name):
    return shutil.which(name) is not None


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


def has_active_task(cwd):
    result = subprocess.run(
        ["backlog", "task", "list", "--status", "In Progress", "--plain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return "No tasks found." not in (result.stdout or "")


def is_outside_project(path, cwd):
    """True if `path` (relative paths resolve against `cwd`) lands outside the
    project root after realpath on both sides, so `..` and symlinks pointing
    back into the project still count as inside. Empty path -> False."""
    if not path or not cwd:
        return False
    root = os.path.realpath(cwd)
    target = os.path.realpath(os.path.join(cwd, path))
    return os.path.commonpath([root, target]) != root  # ---- 1


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    transcript = data.get("transcript_path", "") or ""

    if not has_command("backlog"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    # TASK-27: 프로젝트 밖 파일(plan, memory, scratchpad 등)은 게이트하지 않는다.
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if isinstance(path, str) and is_outside_project(path, cwd):  # ---- 2
            sys.exit(0)

    if not has_active_task(cwd):  # ---- 3
        deny(
            "[claude-code-agile-hooks] In Progress 상태인 backlog 태스크가 없습니다. "
            "먼저 'backlog task edit <ID> -s \"In Progress\"'로 태스크를 활성화하세요."
        )

    if transcript and os.path.isfile(transcript):
        with open(transcript, errors="ignore") as f:
            content = f.read()
        if "task view" not in content:  # ---- 4
            deny(
                "[claude-code-agile-hooks] 이 세션에서 'backlog task view <ID> --plain'으로 태스크를 먼저 읽지 않았습니다."
            )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 프로젝트 밖 판정은 realpath 양쪽
#   설명: 프로젝트 루트와 대상 경로를 둘 다 realpath로 푼 뒤 비교한다. `..`나 프로젝트 안으로 되돌아오는 심볼릭 링크도 안쪽으로 센다.
#   관련: TASK-27
#   개념: realpath: 심볼릭 링크와 `..`를 모두 푼 절대 경로
# 2 프로젝트 밖 파일은 게이트하지 않는다
#   설명: plan·memory·scratchpad처럼 저장소 밖 파일은 태스크와 무관하므로 편집을 막지 않는다. notebook_path도 같이 본다.
#   관련: TASK-27
# 3 In Progress 태스크가 없으면 거부
#   설명: backlog 프로젝트에서 Edit/Write는 In Progress 태스크가 있어야만 허용된다. 거부는 exit 2와 안내 메시지다.
# 4 태스크를 읽었는지 트랜스크립트로 확인
#   설명: 세션 트랜스크립트에 `task view`가 한 번이라도 나왔는지 문자열로 본다. 읽지 않고 편집하면 참조·문서가 컨텍스트에 오르지 않으므로 막는다. 문자열 매칭이라 정밀한 증명은 아니다.
