#!/usr/bin/env python3
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
    doctor_out = run(cwd, ["backlog", "doctor"])

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": overview,
                    "systemMessage": "backlog doctor:\n" + doctor_out,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
