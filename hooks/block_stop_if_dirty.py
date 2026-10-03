#!/usr/bin/env python3
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
    return "No tasks found." not in (result.stdout or "")


def is_dirty(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "status", "--porcelain"], capture_output=True, text=True
    )
    return bool((result.stdout or "").strip())


def background_tasks_running(data):
    """True if the Stop payload says background work is still running.
    The field's shape isn't documented, so any non-empty list/dict counts."""
    tasks = data.get("background_tasks")
    return isinstance(tasks, (list, dict)) and len(tasks) > 0


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


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
            "[claude-rails] 커밋하지 않은 변경사항이 있습니다. 작은 단위로 커밋을 마무리한 뒤 턴을 종료하세요."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
