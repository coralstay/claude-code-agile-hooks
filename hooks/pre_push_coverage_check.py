#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
Optional coverage gate: if the project's .claude-rails.json configures a
`coverageCommand` (e.g. "python3 -m pytest --cov=. --cov-fail-under=100"),
run it before every push and show the real, measured report - every time,
pass or fail. Blocks the push only when the command itself fails (e.g.
coverage.py's own --cov-fail-under exits non-zero below the threshold).
Never fabricates a percentage; a project with no coverageCommand configured
gets no message at all. Every attempt (pass or fail) is also appended to
<cwd>/.claude-rails/coverage-log.jsonl so there's a permanent record beyond
the transcript, which scrolls away.

This script does its own subcommand detection so `git -C <path> push`
(flags before the subcommand) is still recognized as a push, not just
`git push`.

TASK-39: only a `git push` in *command position* counts, found the way
pre_push_check.py (TASK-34) finds it - heredoc bodies dropped, the line
split into shell segments, env assignments/wrappers skipped, git compared
by basename and its global flags skipped. `echo git push`, quoted text and
heredoc bodies no longer run the coverage command. If the line can't be
tokenized, any `push` substring counts as a push (conservative, like
TASK-34: an extra coverage run costs time, a skipped one lets an
under-covered push through).

TASK-46: registered without `if: Bash(git *)` (TASK-39 had kept it). The
filter matches the command text per subcommand (measured 2026-10-04), so
`/usr/bin/git push` or `FOO=1 git push` skipped this report - and when the
coverage command fails this hook denies the push, so it acts as a gate for
projects that opt in. Same registration as pre_push_check.py for
consistency; the cost is one short python process per Bash call, and a
line without a push exits right after parsing, before reading the config
or starting any subprocess. hooks/test_hook_registration_contract.py keeps
the registration and this detection in agreement.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")


# --- command parsing (strip_heredoc_bodies/tokenize/split_segments/
# command_head/git_subcommand_index/command_runs_git are registered in
# dedup_drift_guard.REGISTRY) ---


def strip_heredoc_bodies(command):
    """Drop the body lines of `<<EOF ... EOF` heredocs. The line holding
    the `<<` operator itself is kept (it is a real command)."""
    kept = []
    pending = []  # delimiters whose bodies are still open, in order
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(m.group(3) for m in HEREDOC_RE.finditer(line))
    return "\n".join(kept)


def tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def split_segments(tokens):
    segments = [[]]
    for tok in tokens:
        if tok and set(tok) <= SEPARATOR_CHARS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def command_head(segment):
    """Index of the executable in `segment`, skipping env assignments and
    simple wrappers (same rules as require_draft_first.py)."""
    i = 0
    while i < len(segment):
        tok = segment[i]
        if tok in ("{", "!") or ASSIGNMENT_RE.match(tok):
            i += 1
            continue
        if tok in WRAPPERS:
            i += 1
            while i < len(segment) and segment[i].startswith("-"):
                i += 1
            continue
        break
    return i


def git_subcommand_index(segment):
    """Index of the git subcommand in `segment` when the segment runs git
    in command position (basename compare, git's global flags skipped),
    else None."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) != "git":
        return None
    j = i + 1
    while j < len(segment):
        tok = segment[j]
        if tok in FLAGS_WITH_ARG:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        return j
    return None


def command_runs_git(command, subcommand):
    """True if some shell segment of `command` runs `git <subcommand>` in
    command position. Heredoc bodies and quoted/plain arguments of other
    commands don't count. Falls back to a substring check when the line
    can't be tokenized (conservative: these hooks are gates)."""
    if not command:
        return False
    # bash joins backslash-newline continuations before parsing words
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return subcommand in stripped
    for segment in split_segments(tokens):
        j = git_subcommand_index(segment)
        if j is not None and segment[j] == subcommand:
            return True
    return False


def configured_coverage_command(cwd):
    config_path = os.path.join(cwd, ".claude-rails.json")
    if not os.path.isfile(config_path):
        return None
    with open(config_path) as f:
        config = json.load(f)
    return config.get("coverageCommand") or None


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_id_from_branch(branch):
    """Extract "TASK-7" from "task/TASK-7", or None for branches that don't
    follow that convention (main, feature branches from other workflows,
    etc.)."""
    prefix = "task/"
    if branch.startswith(prefix):
        return branch[len(prefix) :]
    return None


def run_shell(cwd, command):
    result = subprocess.run(
        command, cwd=cwd, shell=True, capture_output=True, text=True
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def log_path(cwd):
    return os.path.join(cwd, ".claude-rails", "coverage-log.jsonl")


def append_log(cwd, record):
    path = log_path(cwd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    bash_command = (data.get("tool_input") or {}).get("command", "")

    if not command_runs_git(bash_command, "push"):
        sys.exit(0)

    command = configured_coverage_command(cwd)
    if not command:
        sys.exit(0)

    exit_code, output = run_shell(cwd, command)
    passed = exit_code == 0

    branch = current_branch(cwd)

    append_log(
        cwd,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": data.get("session_id"),
            "project": os.path.basename(os.path.normpath(cwd)) if cwd else None,
            "branch": branch or None,
            "task_id": task_id_from_branch(branch),
            "command": command,
            "exit_code": exit_code,
            "passed": passed,
            "output": output[-4000:],
        },
    )

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if passed else "deny",
            "permissionDecisionReason": (
                "커버리지 기준 통과"
                if passed
                else f"커버리지 기준 미달 (exit {exit_code})"
            ),
            "systemMessage": (
                f"[claude-rails] 커버리지 리포트 ('{command}', exit {exit_code}):\n"
                + output[-4000:]
            ),
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


if __name__ == "__main__":
    main()
