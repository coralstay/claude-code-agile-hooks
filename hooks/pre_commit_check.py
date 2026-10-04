#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
Phase 3-1 + 3-4: commits must happen on a task/<ID> branch, and (if the
project opted in via .claude-rails.json) tests must pass first.

TASK-39: registered without `if: Bash(git *)` - that filter matches the
command text, so `/usr/bin/git commit` or `FOO=1 git commit` never reached
this gate (same finding as TASK-37). The cost is one short python process
per Bash call; every non-commit line exits right after parsing.

Only a `git commit` in *command position* counts, found the way
pre_push_check.py (TASK-34) finds a push: heredoc bodies dropped,
backslash-newline continuations joined, the line tokenized and split into
shell segments (`;`, `&&`, `||`, `|`, `&`, `(`, newline), env assignments
and simple wrappers (`env`, `sudo`, ...) skipped (`command_head`), git
compared by basename (decision-1) and its global flags (`-C <path>`,
`-c k=v`, `--git-dir=...`) skipped. `echo git commit`, quoted text
(`--notes "... git commit ..."`) and heredoc bodies are not a commit.

Parse failure (unbalanced quote): command position can't be told apart
from text, so any `commit` substring counts as a commit - this is a gate,
and an unneeded branch/test check is recoverable while a skipped one is not.

Known gaps (decision-1): `bash -c "git commit"`, `eval`, aliases, scripts,
backtick substitution, and runners such as `xargs git commit` are not seen.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")


def has_command(name):
    return shutil.which(name) is not None


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


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def configured_test_command(cwd):
    config_path = os.path.join(cwd, ".claude-rails.json")
    if not os.path.isfile(config_path):
        return None
    with open(config_path) as f:
        config = json.load(f)
    return config.get("testCommand") or None


def run_shell(cwd, command):
    result = subprocess.run(
        command, cwd=cwd, shell=True, capture_output=True, text=True
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    command = (data.get("tool_input") or {}).get("command", "")

    if not command_runs_git(command, "commit"):
        sys.exit(0)
    if not has_command("backlog"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    if has_active_task(cwd):
        branch = current_branch(cwd)
        if not branch.startswith("task/"):
            deny(
                f"[claude-rails] 커밋하기 전에 태스크 브랜치(task/TASK-ID)로 전환하세요. 현재 브랜치: {branch}"
            )

    test_command = configured_test_command(cwd)
    if test_command:
        exit_code, output = run_shell(cwd, test_command)
        if exit_code != 0:
            deny(
                f"[claude-rails] 커밋 전 테스트 실패 ('{test_command}', exit {exit_code}):\n"
                + output[-800:]
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
