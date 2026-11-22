#!/usr/bin/env python3
# ---
# title: session_start
# description: 세션 시작 때마다 워크플로 안내문을 주고, backlog 프로젝트면 공식 안내와 무결성 문제를 이어 알려 주는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-21'
# ---
"""SessionStart: brief Claude with the workflow guide on every session and,
if cwd is a backlog.md project, with the official workflow overview and
any integrity issues. Cannot block (SessionStart doesn't support it) - this
is context injection only.
TASK-76: the guide (workflow_guide.md, installed next to this hook) is
printed wherever the session starts, so it can't drift from the installed
hooks the way a block pasted once into ~/.claude/CLAUDE.md did. No guide
or an unreadable one is skipped silently.
TASK-75: cwd is judged at its git top-level, so a subdirectory or linked
worktree of a backlog project counts.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import shutil
import subprocess
import sys

GUIDE_NAME = "workflow_guide.md"


def has_command(name):
    return shutil.which(name) is not None


def project_root(path):
    """TASK-75 B1: the git top-level holding `path` (a directory or a file,
    existing or not) - the nearest of `path` and its parents with a `.git`
    entry, a directory or (linked worktree, submodule) a file. None outside
    any repository or for an empty path. Walks the logical path (no
    realpath) and runs no subprocess."""
    if not path:
        return None
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_backlog_project(cwd):
    """TASK-75 B1: True if `cwd` lies in a git repository (judged at its
    top-level, project_root) with backlog/config.yml - so a subdirectory
    or a linked worktree of a backlog project is that project too."""
    root = project_root(cwd)
    return root is not None and os.path.isfile(
        os.path.join(root, "backlog", "config.yml")
    )


def run(cwd, cmd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout or ""


def strip_frontmatter(text):
    """TASK-76: the guide without its YAML source header (`---` ... `---`
    at the top), trimmed. An unterminated header is kept as text."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 3)
        if end != -1:
            text = text[end + len("\n---\n"):]
    return text.strip()


def read_guide():
    """TASK-76 B2: the workflow guide next to this hook file, or "" when it
    is missing or unreadable (never an error - the session must start)."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), GUIDE_NAME)  # ---- 1
    try:
        with open(path, encoding="utf-8") as f:
            return strip_frontmatter(f.read())
    except (OSError, ValueError):  # ---- 2
        return ""


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")

    context = [read_guide()]  # ---- 3
    output = {"hookEventName": "SessionStart"}
    if has_command("backlog") and is_backlog_project(cwd):
        context.append(run(cwd, ["backlog", "instructions", "overview"]))  # ---- 4
        output["systemMessage"] = "backlog doctor:\n" + run(cwd, ["backlog", "doctor"])  # ---- 5
    output["additionalContext"] = "\n\n".join(part for part in context if part)

    if output["additionalContext"] or "systemMessage" in output:
        print(json.dumps({"hookSpecificOutput": output}))
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 안내문은 훅 파일 옆에서 찾는다
#   설명: install.sh가 훅과 같은 디렉터리에 workflow_guide.md를 복사한다. 심볼릭 링크로 불려도 실제 훅 파일 위치를 기준으로 찾도록 realpath를 쓴다. 훅과 안내문이 함께 설치·갱신되므로 둘이 어긋나지 않는다.
#   관련: install.sh, TASK-76
# 2 안내문 실패는 조용히 건너뛴다
#   설명: 파일이 없거나(OSError), 디렉터리이거나, UTF-8이 아니어도(ValueError) 빈 문자열로 넘긴다. SessionStart는 막을 수 없고, 안내문 때문에 세션 시작이 깨지면 안 된다.
#   관련: TASK-76 B2
# 3 안내문을 세션 위치와 무관하게 먼저
#   설명: backlog 프로젝트 여부와 backlog CLI 유무를 보기 전에 안내문을 넣는다. 그래서 프로젝트 밖에서 연 세션도 다른 저장소를 다룰 때의 규칙을 안다.
#   관련: TASK-76 B2
# 4 공식 워크플로 안내를 안내문 뒤에 이어 붙임
#   설명: backlog 프로젝트 안이면 `backlog instructions overview` 출력을 안내문 다음에 빈 줄 하나를 두고 붙여 additionalContext로 넣는다. 빈 조각은 빼고 잇는다.
# 5 무결성 점검 결과를 시스템 메시지로
#   설명: backlog doctor 출력을 systemMessage로 보여 무결성 문제를 세션 시작에서 바로 드러낸다. 안내문·overview가 모두 비어도 프로젝트 안이면 출력한다.
