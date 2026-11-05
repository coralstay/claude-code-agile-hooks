#!/usr/bin/env python3
"""PreToolUse (matcher: Bash)
TASK-59#3: in a backlog.md project every card lifecycle stage lands as its
own commit - draft 1장 → 커밋 → 승격 → 커밋 → In Progress → 커밋 → 작업 →
Done → 커밋. This hook denies the *next* stage command while the previous
stage is still uncommitted, i.e. while `git status --porcelain -- backlog/`
reports anything (modified, staged, untracked, deleted, renamed).

Stage commands, judged in command position only:
  - `backlog draft create ...`
  - `backlog draft promote ...`
  - `backlog task edit <ID> ... -s/--status "In Progress"` (case-insensitive)
  - `backlog task edit <ID> ... -s/--status Done`

Command position works as in require_draft_first.py: after `;`, `&&`,
`||`, `|`, `(`, a newline or at the start, behind env assignments and simple
wrappers, the executable compared by basename (decision-1). Quoted
arguments of other commands and heredoc bodies don't count. If the line
can't be tokenized (unbalanced quotes), a text match stands in (this is a
gate: a false deny costs one commit, a missed one costs the history).

Only backlog/ is checked - unrelated work in progress elsewhere never blocks
a stage. The changes a stage command makes itself happen *after* this
PreToolUse check, so `backlog task edit X --check-ac 1 --final-summary ...
-s Done` in one command passes on a clean tree. Separate earlier edits
(`task edit X --add-ref ...` left uncommitted, then `-s "In Progress"`) are
denied on purpose: commit them first.

Known gaps (decision-1): `bash -c`, `eval`, aliases/variables, the backlog
MCP server and browser UI are not seen. backlog_commit_scope.py checks the
commit side (one new draft per commit, transition commits hold only their
task file).

Fully self-contained (decision-3): no imports from any other file in this
repo. The copied helpers are registered in dedup_drift_guard.REGISTRY."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
STAGE_STATUSES = {"in progress", "done"}
FALLBACK_RE = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?backlog(?:\.md)?\s+(?:"
    r"drafts?\s+(?:create|promote)\b"
    r"|tasks?\s+edit\b[^;&|\n]*?(?:-s|--status)(?:=|\s+)['\"]?(?:in progress|done)\b"
    r")",
    re.MULTILINE | re.IGNORECASE,
)
MAX_LISTED = 10


def has_command(name):
    return shutil.which(name) is not None


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


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


def edit_status(args):
    """The value of the last -s/--status option in `task edit` args."""
    status = None
    for j, tok in enumerate(args):
        if tok in ("-s", "--status") and j + 1 < len(args):
            status = args[j + 1]
        elif tok.startswith("--status="):
            status = tok[len("--status=") :]
    return status


def segment_runs_stage(segment):
    """True if `segment` runs a lifecycle stage command in command position."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
        return False
    rest = segment[i + 1 :]
    if len(rest) < 2:
        return False
    noun, verb = rest[0], rest[1]
    if noun in ("draft", "drafts"):
        return verb in ("create", "promote")
    if noun in ("task", "tasks") and verb == "edit":
        status = edit_status(rest[2:])
        return status is not None and status.lower() in STAGE_STATUSES
    return False


def command_runs_stage(command):
    if not command:
        return False
    # bash joins backslash-newline continuations before parsing words
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return bool(FALLBACK_RE.search(stripped))
    return any(segment_runs_stage(s) for s in split_segments(tokens))


# --- working tree -----------------------------------------------------------


def uncommitted_backlog_paths(cwd):
    """Paths under backlog/ that differ from HEAD (staged, unstaged or
    untracked), or None when git status fails."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all", "--", "backlog/"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    paths = []
    fields = result.stdout.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in ("R", "C") and i < len(fields):
            paths.append(fields[i])  # -z puts the rename source next
            i += 1
    return paths


def format_paths(paths):
    listed = "\n".join(f"  - {p}" for p in paths[:MAX_LISTED])
    if len(paths) > MAX_LISTED:
        listed += f"\n  ... 외 {len(paths) - MAX_LISTED}개"
    return listed


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

    if not command_runs_stage(command):
        sys.exit(0)
    if not has_command("git") or not is_backlog_project(cwd):
        sys.exit(0)

    paths = uncommitted_backlog_paths(cwd)
    if not paths:
        sys.exit(0)

    deny(
        "[claude-code-agile-hooks] 다음 단계(draft create · draft promote · "
        '-s "In Progress" · -s Done)로 넘어가기 전에 이전 단계를 먼저 커밋하세요 — '
        "커밋되지 않은 backlog/ 변경이 있습니다:\n"
        + format_paths(paths)
        + "\n단계마다 커밋한다: draft 1장 → 커밋 → 승격 → 커밋 → In Progress → 커밋 → "
        "작업 → Done → 커밋."
    )


if __name__ == "__main__":
    main()
