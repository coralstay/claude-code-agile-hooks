#!/usr/bin/env python3
# ---
# title: session_start
# description: backlog 프로젝트에서 세션 시작 시 워크플로 안내와 무결성 문제를 알려 주는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""SessionStart: if cwd is a backlog.md project, brief Claude with the
official workflow guide and surface any integrity issues. Cannot block
(SessionStart doesn't support it) - this is context injection only.

Fully self-contained: no imports from any other file in this repo."""

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


def run(cwd, cmd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout or ""


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")

    if not has_command("backlog"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    overview = run(cwd, ["backlog", "instructions", "overview"])
    doctor_out = run(cwd, ["backlog", "doctor"])  # ---- 1

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": overview,  # ---- 2
                    "systemMessage": "backlog doctor:\n" + doctor_out,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 무결성 점검 결과를 시스템 메시지로
#   설명: backlog doctor 출력을 systemMessage로 보여 무결성 문제를 세션 시작에서 바로 드러낸다.
# 2 공식 워크플로 안내를 컨텍스트로 주입
#   설명: `backlog instructions overview` 출력을 additionalContext로 넣는다. SessionStart는 차단할 수 없어 컨텍스트 주입만 한다.
