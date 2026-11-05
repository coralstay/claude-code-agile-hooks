#!/usr/bin/env python3
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
    result = subprocess.run(["git", "-C", toplevel, "add", "--", path], capture_output=True, text=True)
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

    sys.exit(0)


if __name__ == "__main__":
    main()
