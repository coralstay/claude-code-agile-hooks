#!/usr/bin/env python3
"""PermissionRequest
Auto-allow permission requests for read-only tools and commands, so Claude
Code doesn't stop to ask about calls that cannot change anything.

The scope is deliberately conservative:
- Read, Glob and Grep are always allowed.
- Bash is allowed only for a single plain command whose first word is one
  of ls, pwd, cat, echo, whoami, date, which, head, tail, wc, find, or for
  `git status|log|diff|show|branch|remote`. Any shell metacharacter
  (| ; & $ ` ( ) { } < >) or a newline disqualifies the command.
- Every other tool is left alone.
The hook never denies: it either allows or prints nothing, and the normal
permission prompt takes over.

This is this repository's own implementation.

Fully self-contained: no imports from any other file in this repo."""

import json
import sys

READ_ONLY_TOOLS = ("Read", "Glob", "Grep")
UNSAFE_CHARACTERS = frozenset("|;&$`(){}<>\n")
SAFE_COMMANDS = frozenset(
    {"ls", "pwd", "cat", "echo", "whoami", "date", "which", "head", "tail", "wc", "find"}
)
SAFE_GIT_SUBCOMMANDS = frozenset({"status", "log", "diff", "show", "branch", "remote"})
REASON = "permission_auto_allow: read-only tool/command"


def is_safe_bash_command(command):
    if any(char in UNSAFE_CHARACTERS for char in command):
        return False
    words = command.split()
    if not words:
        return False
    if words[0] in SAFE_COMMANDS:
        return True
    if words[0] == "git":
        return len(words) > 1 and words[1] in SAFE_GIT_SUBCOMMANDS
    return False


def should_auto_allow(tool_name, tool_input):
    if tool_name in READ_ONLY_TOOLS:
        return True
    if tool_name == "Bash":
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        return is_safe_bash_command(str(tool_input.get("command") or ""))
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    data = data if isinstance(data, dict) else {}

    if should_auto_allow(data.get("tool_name"), data.get("tool_input")):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PermissionRequest",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": REASON,
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
