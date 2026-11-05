#!/usr/bin/env python3
"""PreToolUse (matcher: Bash)
Block catastrophic/high-risk shell commands before they run. Ported from
karanb192/claude-code-hooks' block-dangerous-commands plugin (MIT license),
scope narrowed: "force push to main" is owned exclusively by
pre_git_safety_check.py to avoid the duplicate rule that exists in the
upstream project itself (see plan's "겹침 정리" #1).

HOOK_SAFETY_LEVEL env var picks the ruleset: critical (default) | high | strict.
Unknown values fall back to critical.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys

# A single "flag token": short form (-r, -rf, -Rf, -v, ...) or GNU long form
# (--recursive, --force, --verbose, ...). Used both to walk over a cluster of
# flags after `rm` and, inside the two lookaheads below, to skip past
# unrelated flags while searching for a recursive/force indicator.
_FLAG_TOKEN = r"(?:-[a-zA-Z]+|--[a-zA-Z-]+)"
_RECURSIVE_FLAG = r"(?:-[a-zA-Z]*r[a-zA-Z]*|--recursive)\b"
_FORCE_FLAG = r"(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\b"

# Matches the flags portion of an `rm` invocation that is recursive AND
# forced, however that's spelled: a single combined short token in either
# order and either case (-rf, -fr, -Rf, -RF, ...), flags split into separate
# words in any order (-r -f, -f -r, -r -v -f, ...), or GNU long flags in any
# order (--recursive --force, --force --recursive). The two lookaheads each
# scan forward across the flag cluster (skipping unrelated flags) to confirm
# a recursive-ish and a force-ish token are both present; the trailing
# pattern then actually consumes the whole cluster so the caller's `\s+`
# separator before the target path still lines up. Matching is case
# insensitive (see find_violation), which is what makes -Rf/-RF/--RECURSIVE
# work.
RM_RF_FLAGS = (
    rf"(?=(?:{_FLAG_TOKEN}\s+)*{_RECURSIVE_FLAG})"
    rf"(?=(?:{_FLAG_TOKEN}\s+)*{_FORCE_FLAG})"
    rf"(?:{_FLAG_TOKEN}\s+)*{_FLAG_TOKEN}"
)

CRITICAL_PATTERNS = [
    (
        rf"rm\s+{RM_RF_FLAGS}\s+(/|~|\$HOME)\s*($|/\s*$)",
        "rm -rf on root or home",
    ),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bdd\s+.*of=/dev/(disk|sda|nvme|rdisk)", "dd writing directly to a disk device"),
    (r"\bmkfs(\.\w+)?\s+/dev/", "formatting a device"),
]

HIGH_PATTERNS = CRITICAL_PATTERNS + [
    (r"\bcurl\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b", "curl | sh"),
    (r"\bwget\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b", "wget | sh"),
    (r"git\s+reset\s+--hard\b", "git reset --hard"),
    # rm -rf targeting a path that walks up out of the current directory via
    # ".." (rm -rf ../, rm -rf ../../foo, rm -rf ./some-dir/../../important).
    # Approximate on purpose: scoped to a single shell "segment" ([^;&|\n])
    # so it doesn't reach across an unrelated && / ; / | into another command.
    (
        rf"rm\s+{RM_RF_FLAGS}[^;&|\n]*?(?:^|[\s/])\.\.(?=/|$|\s)",
        "rm -rf escaping the current directory via ..",
    ),
    # rm -rf targeting an absolute path that isn't one of a small set of
    # common safe/temp directories. This can't know the real cwd from the
    # command string alone, so it's a practical approximation, not a proof.
    (
        rf"rm\s+{RM_RF_FLAGS}[^;&|\n]*?(?:^|\s)/(?!tmp\b|var/tmp\b|private/tmp\b|var/folders\b|dev/null\b|\s|$)\S+",
        "rm -rf on an absolute path outside common safe/temp directories",
    ),
]

STRICT_PATTERNS = HIGH_PATTERNS + [
    (r"\bsudo\s+rm\b", "sudo rm"),
    (r"\bdocker\s+(system\s+)?prune\b", "docker prune"),
]

LEVELS = {
    "critical": CRITICAL_PATTERNS,
    "high": HIGH_PATTERNS,
    "strict": STRICT_PATTERNS,
}


def get_patterns():
    level = os.environ.get("HOOK_SAFETY_LEVEL", "critical")
    return LEVELS.get(level, CRITICAL_PATTERNS)


def find_violation(command):
    for pattern, reason in get_patterns():
        if re.search(pattern, command, re.IGNORECASE):
            return reason
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
    if not command:
        sys.exit(0)

    violation = find_violation(command)
    if violation:
        deny(
            f"[block-dangerous-commands] 위험한 명령이 차단되었습니다: {violation}\n명령: {command}"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
