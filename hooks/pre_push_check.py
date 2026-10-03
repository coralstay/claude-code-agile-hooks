#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, if: Bash(git *))
Phase 4.3: only push a task/<ID> branch once that task is Done and carries
a final summary.

The settings.json `if` filter only narrows to "any git command" - this
script does its own subcommand detection so `git -C <path> push` (flags
before the subcommand) is still recognized as a push, not just `git push`.

TASK-34: only a `git push` in *command position* counts - the start of a
shell segment (after `;`, `&&`, `||`, `|`, `&`, `(`, `{`, a newline, or the
start of the line), optionally behind env assignments (`FOO=1`) and simple
wrappers (`env`, `sudo`, `command`, `exec`, `time`, `nohup`, `npx`, `bunx`),
the same rules as require_draft_first.py / pipeline_trace.py. The executable
is compared by basename (`/usr/bin/git`, decision-1) and git's global flags
(`-C <path>`, `-c k=v`, `--git-dir=...`) are skipped. The words inside a
quoted argument (`git commit -m "... git push ..."`, backlog doc/notes text),
as plain arguments of another command (`echo git push`), or in a heredoc
body are not a push and pass without a task-status check.

Fallback: if the line can't be tokenized (an unbalanced quote outside any
heredoc), command position can't be told apart from text, so any `push`
substring in the heredoc-stripped line is treated as a push - the old
conservative behaviour. A spurious block is recoverable; a missed check on a
real push is not.

Timing caveat (inherent to PreToolUse): the hook runs once, before the whole
Bash line. In `backlog task edit <ID> -s Done ... && git push` the status
edit hasn't run yet when this is judged, so the push is still denied. Run
the status edit as its own command first.

Known gaps (decision-1): `bash -c "git push"`, `eval`, aliases, scripts, and
backtick substitution are not seen.

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
# command_head are registered in dedup_drift_guard.REGISTRY) ---


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


def segment_runs_git_push(segment):
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) != "git":
        return False
    j = i + 1
    while j < len(segment):
        tok = segment[j]
        if tok in FLAGS_WITH_ARG:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        break
    return j < len(segment) and segment[j] == "push"


def command_invokes_git_push(command):
    """True if some shell segment of `command` runs `git push` in command
    position. Heredoc bodies and quoted/plain arguments of other commands
    don't count. Falls back to a substring check when unparsable."""
    if not command:
        return False
    # bash joins backslash-newline continuations before parsing words
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return "push" in stripped
    return any(segment_runs_git_push(s) for s in split_segments(tokens))


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_view(cwd, task_id):
    result = subprocess.run(
        ["backlog", "task", "view", task_id, "--json"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


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

    if not command_invokes_git_push(command):
        sys.exit(0)
    if not has_command("backlog"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    branch = current_branch(cwd)
    if not branch.startswith("task/"):
        sys.exit(0)
    task_id = branch[len("task/") :]

    view = task_view(cwd, task_id)
    if view is None:
        sys.exit(0)

    task = view.get("task", {})
    status = task.get("status", "")
    summary = (task.get("finalSummary") or "").strip()

    if status != "Done":
        deny(
            f"[claude-rails] {task_id} 가 아직 Done 상태가 아닙니다 (현재: {status}). 완료 처리 후 push하세요."
        )
    if not summary:
        deny(
            f"[claude-rails] {task_id} 의 final summary가 비어있습니다. "
            f"'backlog task edit {task_id} --final-summary \"...\"' 로 작성 후 push하세요."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
