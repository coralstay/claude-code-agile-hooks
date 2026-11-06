#!/usr/bin/env python3
# ---
# title: block_stop_if_dirty
# description: 태스크 진행 중 커밋하지 않은 변경이 있으면 턴 종료(Stop)를 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""Stop
Phase 3-4b: don't let Claude end its turn with uncommitted changes while a
task is In Progress - forces the small-commit loop to actually finish.

TASK-31 context flags (read straight from the Stop payload, not from the
flag file - Stop hooks run in parallel, so context_flags.py's write for
this same Stop isn't guaranteed to land first):
- background_tasks non-empty (parallel_session): pass. The uncommitted
  changes may belong to a still-running background subagent editing the
  same tree; blocking only makes the main agent busy-wait. The Stop that
  follows once the background work finishes is still checked.
- stop_hook_active is deliberately NOT a pass condition: committing is
  always within Claude's power, so repeated blocking is the enforcement,
  not a loop bug. The loop seen in practice came from background work
  owning the dirty tree, which the rule above covers.

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


def has_active_task(cwd):
    result = subprocess.run(
        ["backlog", "task", "list", "--status", "In Progress", "--plain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return "No tasks found." not in (result.stdout or "")  # ---- 1


def is_dirty(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "status", "--porcelain"], capture_output=True, text=True
    )
    return bool((result.stdout or "").strip())


def background_tasks_running(data):
    """True if the Stop payload says background work is still running.
    The field's shape isn't documented, so any non-empty list/dict counts."""
    tasks = data.get("background_tasks")
    return isinstance(tasks, (list, dict)) and len(tasks) > 0  # ---- 2


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)  # ---- 3


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")

    if background_tasks_running(data):
        sys.exit(0)

    if not has_command("backlog"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)
    if not has_active_task(cwd):
        sys.exit(0)

    if is_dirty(cwd):
        deny(
            "[claude-code-agile-hooks] 커밋하지 않은 변경사항이 있습니다. 작은 단위로 커밋을 마무리한 뒤 턴을 종료하세요."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 In Progress 태스크가 있을 때만 적용
#   설명: backlog CLI 출력 문구에 기대는 판정이다. 활성 태스크가 없으면 커밋을 강제할 이유가 없어 통과한다.
#   관련: hooks/dedup_drift_guard.py (이 함수는 훅마다 복사돼 REGISTRY로 일치를 검증한다)
# 2 백그라운드 작업이 있으면 통과
#   설명: background_tasks 필드의 모양이 문서화돼 있지 않아 비어 있지 않은 list/dict면 모두 실행 중으로 본다. 더러운 작업 트리가 아직 도는 서브에이전트의 것일 수 있어, 막으면 메인 에이전트가 기다리기만 한다.
#   관련: hooks/context_flags.py, TASK-31
# 3 exit 2로 턴 종료를 막는다
#   설명: Stop 훅이 stderr 메시지와 함께 exit 2를 내면 Claude가 멈추지 못하고 커밋부터 마무리한다. stop_hook_active는 일부러 통과 조건에서 뺐다. 커밋은 늘 Claude가 할 수 있으므로 반복 차단이 곧 강제다.
