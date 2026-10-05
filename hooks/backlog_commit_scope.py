#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-29 (B): in a backlog.md project, "draft created" and "draft promoted"
must each land as their own commit, so history shows when something became
a task. On `git commit` (including `git -C <path> commit`) this hook reads
the staged index with `git diff --cached --name-status -M -z` and denies:

1. Draft-creation commits that carry anything else: the index adds a new
   file under backlog/drafts/ AND stages any path outside backlog/drafts/.
2. Promotion commits that carry anything else: the index renames
   backlog/drafts/* -> backlog/tasks/* (or, if git's rename detection
   misses it, deletes a draft and adds a task) AND stages anything other
   than those renames/deletes and files under backlog/tasks/. Editing the
   promoted task file right after promotion (`task edit --add-ref`, `--doc`)
   and touching other task files is allowed; code/docs/config is not.

Timing caveat: PreToolUse runs *before* the Bash command, so the index it
sees is the pre-command one. To close the common cases this hook simulates,
on a throwaway copy of the index (GIT_INDEX_FILE, the real index is never
touched), the parts of the same command line that stage files before the
commit:
  - plain `git add <args>` segments that precede the commit, and
  - `git commit -a` / `--all` / short clusters such as `-am`.
Simulation is skipped (the real index is checked as-is) when the command
`cd`s/`pushd`s first, when a preceding `git add` uses global flags
(`git -C x add`), a `GIT_*=` assignment, or shell expansions (`$VAR`,
backticks), or when the line can't be tokenized.

TASK-39: commits and the `git add`s to replay are found the way
pre_push_check.py (TASK-34) finds a push - heredoc bodies dropped,
backslash-newline continuations joined, the line split into shell segments,
env assignments and simple wrappers skipped (`command_head`), git compared
by basename (decision-1) and its global flags skipped. Detection
(`command_runs_git`) and replay (`staging_plan`) read the same segments, so
`echo git commit`, quoted text and heredoc bodies neither trigger the check
nor get replayed, while `sudo git add x && FOO=1 /usr/bin/git commit` is
both detected and simulated. If the line can't be tokenized, any `commit`
substring counts as a commit and the real index is checked (conservative:
an extra index read is harmless, a skipped scope check is not). Registered
without `if: Bash(git *)` for the same reason as pre_commit_check.py: the
filter matches command text, so absolute-path or env-prefixed commits never
reached this hook.

Still uncovered: `git rm`/`git mv`/`git stage`/`git update-index` in the
same command, `git commit <pathspec>`/`--only`/`--include` (checked against
the full index, which can over- or under-report), commits run inside
`bash -c`/scripts/aliases, and commits made outside Claude Code (plain
terminal, git GUIs) - this is a Claude Code PreToolUse hook, not a git
pre-commit hook (decision recorded in TASK-29). `git -C <path> commit` is
recognized as a commit, but the index checked is still the one of `cwd`,
same as pre_commit_check.py.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")

DRAFTS = "backlog/drafts/"
TASKS = "backlog/tasks/"
COMMIT_SHORT_WITH_ARG = set("mFcCt")
COMMIT_LONG_WITH_ARG = {
    "--message",
    "--file",
    "--author",
    "--date",
    "--template",
    "--reuse-message",
    "--reedit-message",
    "--fixup",
    "--squash",
    "--cleanup",
    "--trailer",
    "--pathspec-from-file",
}
MAX_LISTED = 10


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


# --- index inspection --------------------------------------------------------


def parse_name_status(raw):
    """Parses `git diff --name-status -z` output into
    [(status_letter, path, new_path_or_None), ...]."""
    fields = raw.split("\0")
    entries = []
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        letter = status[0]
        if letter in ("R", "C") and i + 2 < len(fields):
            entries.append((letter, fields[i + 1], fields[i + 2]))
            i += 3
        elif i + 1 < len(fields):
            entries.append((letter, fields[i + 1], None))
            i += 2
        else:
            break
    return entries


def staged_entries(cwd, env=None):
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status", "-M", "-z"],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return None
    return parse_name_status(result.stdout)


# --- same-command staging simulation ----------------------------------------


def commit_stages_all(args):
    """True if `git commit <args>` would stage tracked changes (-a/--all)."""
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            break
        if arg.startswith("--"):
            if arg == "--all":
                return True
            if "=" not in arg and arg in COMMIT_LONG_WITH_ARG:
                i += 1
            continue
        if arg.startswith("-") and len(arg) > 1:
            cluster = arg[1:]
            for pos, ch in enumerate(cluster):
                if ch == "a":
                    return True
                if ch in COMMIT_SHORT_WITH_ARG:
                    if pos == len(cluster) - 1:
                        i += 1
                    break
    return False


def staging_plan(command):
    """Returns (list_of_git_add_arg_lists, commit_all) describing what the
    command stages before its commit, or None when it can't be simulated
    safely (fall back to checking the real index)."""
    # TASK-39: the same segments command_runs_git() judges - heredoc bodies
    # dropped, continuations joined, git found in command position
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return None

    adds = []
    for segment in split_segments(tokens):
        head = command_head(segment)
        if head < len(segment) and segment[head] in ("cd", "pushd", "popd"):
            return None
        j = git_subcommand_index(segment)
        if j is None:
            continue
        sub, args = segment[j], segment[j + 1 :]
        if sub not in ("add", "commit"):
            continue
        if j != head + 1 or any(t.startswith("GIT_") for t in segment[:head]):
            # global flags (`git -C x ...`) or `GIT_*=` env may point at
            # another repo/index: only the commit itself is fine
            if sub == "commit":
                return adds, False
            return None
        if sub == "add":
            # shell expansions/redirections can't be replayed faithfully
            if any(ch in a for a in args for ch in "$`<>"):
                return None
            adds.append(args)
        else:  # sub == "commit" (only add/commit get past the check above)
            return adds, commit_stages_all(args)
    return None


def simulated_entries(cwd, adds, commit_all):
    """Replays the staging steps on a temporary copy of the index and
    returns the resulting staged entries. Never touches the real index."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "index"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    real_index = os.path.join(cwd, result.stdout.strip())

    with tempfile.TemporaryDirectory() as tmp:
        temp_index = os.path.join(tmp, "index")
        if os.path.isfile(real_index):
            # copy2 keeps the mtime: git compares content only for entries
            # not older than the index file ("racy"), and a fresh mtime on
            # the copy would hide a same-size edit made in that second
            shutil.copy2(real_index, temp_index)
        env = dict(os.environ, GIT_INDEX_FILE=temp_index)
        steps = [["git", "add", *args] for args in adds]
        if commit_all:
            steps.append(["git", "add", "-u"])
        for step in steps:
            subprocess.run(step, cwd=cwd, capture_output=True, text=True, env=env)
        return staged_entries(cwd, env=env)


# --- policy -----------------------------------------------------------------


def entry_paths(entry):
    _, path, new_path = entry
    return [path, new_path] if new_path else [path]


def is_promotion_rename(entry):
    letter, path, new_path = entry
    return (
        letter == "R"
        and path.startswith(DRAFTS)
        and bool(new_path)
        and new_path.startswith(TASKS)
    )


def format_offenders(entries):
    paths = []
    for entry in entries:
        for p in entry_paths(entry):
            if p not in paths:
                paths.append(p)
    listed = "\n".join(f"  - {p}" for p in paths[:MAX_LISTED])
    if len(paths) > MAX_LISTED:
        listed += f"\n  ... 외 {len(paths) - MAX_LISTED}개"
    return listed


def check_scope(entries):
    """Returns a deny message, or None if the staged set is acceptable."""
    new_drafts = [
        e for e in entries if e[0] in ("A", "C") and (e[2] or e[1]).startswith(DRAFTS)
    ]
    if new_drafts:
        offenders = [
            e for e in entries if not all(p.startswith(DRAFTS) for p in entry_paths(e))
        ]
        if offenders:
            return (
                "[interlock] 드래프트 생성 커밋은 드래프트만 담는다 — 스테이징에 새 "
                "드래프트(backlog/drafts/)와 그 밖의 파일이 섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n드래프트만 먼저 커밋하고, 나머지는 'git restore --staged <path>'로 "
                "내린 뒤 별도 커밋으로 나누세요."
            )

    renames = [e for e in entries if is_promotion_rename(e)]
    deleted_drafts = [e for e in entries if e[0] == "D" and e[1].startswith(DRAFTS)]
    added_tasks = [e for e in entries if e[0] == "A" and e[1].startswith(TASKS)]
    if renames or (deleted_drafts and added_tasks):
        offenders = [
            e
            for e in entries
            if not is_promotion_rename(e)
            and not (e[0] == "D" and e[1].startswith(DRAFTS))
            and not all(p.startswith(TASKS) for p in entry_paths(e))
        ]
        if offenders:
            return (
                "[interlock] 승격 커밋은 승격만 담는다 — 스테이징에 드래프트 승격"
                "(backlog/drafts/ → backlog/tasks/)과 그 밖의 파일이 섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n승격(과 승격된 태스크의 ref/doc 연결)만 먼저 커밋하고, 나머지는 "
                "'git restore --staged <path>'로 내린 뒤 별도 커밋으로 나누세요."
            )
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

    if not command_runs_git(command, "commit"):
        sys.exit(0)
    if not has_command("git"):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    plan = staging_plan(command)
    if plan and (plan[0] or plan[1]):
        entries = simulated_entries(cwd, plan[0], plan[1])
    else:
        entries = staged_entries(cwd)
    if entries is None:
        sys.exit(0)

    message = check_scope(entries)
    if message:
        deny(message)
    sys.exit(0)


if __name__ == "__main__":
    main()
