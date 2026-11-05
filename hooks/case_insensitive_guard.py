#!/usr/bin/env python3
"""PreToolUse (matcher: Bash)
Stop `rm -rf content` from destroying `Content` on a case-insensitive
filesystem (APFS default on macOS, exFAT, NTFS). Ported from
karanb192/claude-code-hooks' case-insensitive-guard plugin (MIT license).

The real hazard: a command deletes path X, but a differently-cased path Y
also exists on disk and the filesystem treats them as the same entry. Since
this hook can't rely on the actual filesystem case-sensitivity setting
(sandboxed here, and we don't want to shell out per invocation for a rare
case), it flags any `rm -rf`-style deletion of a target whose current working
directory contains a sibling entry differing only by case - a cheap, real
check using os.listdir(), not a guess.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

RM_RE = re.compile(r"\brm\b")


def find_case_collision(target, cwd):
    """If `target` (relative to cwd) has a sibling in the same directory that
    matches case-insensitively but not case-sensitively, return that sibling
    name. Otherwise None."""
    if not target or target.startswith("-"):
        return None

    directory, _, name = target.rpartition("/")
    search_dir = os.path.join(cwd, directory) if directory else cwd

    try:
        entries = os.listdir(search_dir)
    except OSError:
        return None

    for entry in entries:
        if entry != name and entry.lower() == name.lower():
            return entry
    return None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    command = (data.get("tool_input") or {}).get("command", "")
    cwd = data.get("cwd", ".")

    if not command or not RM_RE.search(command):
        sys.exit(0)

    try:
        tokens = shlex.split(command)
    except ValueError:
        sys.exit(0)

    basenames = [os.path.basename(t) for t in tokens]
    if "rm" not in basenames:
        sys.exit(0)

    rm_index = basenames.index("rm")
    targets = [t for t in tokens[rm_index + 1 :] if not t.startswith("-")]
    for target in targets:
        collision = find_case_collision(target, cwd)
        if collision:
            deny(
                f"[case-insensitive-guard] '{target}'와(과) 대소문자만 다른 '{collision}'이(가) "
                f"같은 디렉토리에 있습니다. 대소문자 구분 안 하는 파일시스템(APFS/exFAT/NTFS)에서는 "
                f"'{target}' 삭제가 '{collision}'도 함께 지울 수 있습니다: {command}"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
