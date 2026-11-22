#!/usr/bin/env python3
# ---
# title: backlog_commit_scope
# description: draft 생성·승격 커밋이 각자 단독 커밋이 되도록 git commit을 검사하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-22'
# ---
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
3. TASK-59#1: draft-creation commits that add two or more new drafts - the
   history should show each draft (draft 1장 → 커밋) on its own.
4. TASK-59#2: status-transition commits that carry anything else. A staged
   file under backlog/tasks/ is a transition when the `status:` key of its
   YAML frontmatter (the block between the first two `---` lines) reads
   `In Progress` or `Done` in the staged blob (`git cat-file blob :<path>`)
   and something else - or nothing, for a file not in HEAD - in HEAD
   (`HEAD:<old path>`, so a title rename is followed). Such a commit must
   hold only that task file (its own rename included); other paths, or a
   second transitioning task file, are denied. The staged blob is read, not
   the worktree, and from the simulated index when simulation applies.
5. Work order commits that carry anything else (TASK-60): the index stages
   backlog/work-order.md AND anything other than task files under
   backlog/tasks/ (modified or renamed) whose `dependencies` frontmatter
   differs between HEAD and the index. Tidying `--dep` after a promotion and
   regenerating the work order land together as their own commit; a task
   file edited for any other reason, a new or deleted task, or code is
   denied. The staged content is read with `git show :<path>` from the same
   index the check looks at (the simulated one, see below), HEAD with
   `git show HEAD:<path>`.

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
pre-commit hook (decision recorded in TASK-29).

TASK-75: the index checked is the one of the repository the commit targets
- the session cwd moved by earlier `cd <dir>` on the line and the commit's
own `git -C <dir>` - judged at its git top-level. A target that isn't a
backlog project passes; one that can't be known statically (`cd "$X"`) is
denied. Preceding `git add`s are replayed only when that repository is the
session cwd's own (they ran there).

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")

DRAFTS = "backlog/drafts/"
TASKS = "backlog/tasks/"
WORK_ORDER = "backlog/work-order.md"
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
TRANSITION_STATUSES = {"In Progress", "Done"}
STATUS_RE = re.compile(r"^status:\s*(.*?)\s*$")
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
        return subcommand in stripped  # ---- 1
    for segment in split_segments(tokens):
        j = git_subcommand_index(segment)
        if j is not None and segment[j] == subcommand:
            return True
    return False


def project_root(path):
    """TASK-75 B1: the git top-level holding `path` (a directory or a file,
    existing or not) - the nearest of `path` and its parents with a `.git`
    entry, a directory or (linked worktree, submodule) a file. None outside
    any repository or for an empty path. Walks the logical path (no
    realpath) and runs no subprocess."""
    if not path:
        return None
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_backlog_project(cwd):
    """TASK-75 B1: True if `cwd` lies in a git repository (judged at its
    top-level, project_root) with backlog/config.yml - so a subdirectory
    or a linked worktree of a backlog project is that project too."""
    root = project_root(cwd)
    return root is not None and os.path.isfile(
        os.path.join(root, "backlog", "config.yml")
    )


# --- index inspection --------------------------------------------------------


def parse_name_status(raw):
    """Parses `git diff --name-status -z` output into
    [(status_letter, path, new_path_or_None), ...]."""
    fields = raw.split("\0")  # ---- 2
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
        return None  # ---- 3
    return parse_name_status(result.stdout)


def read_blob(cwd, spec, env=None):
    """Contents of `git cat-file blob <spec>` (e.g. `:path`, `HEAD:path`),
    or None when git can't resolve it."""
    result = subprocess.run(
        ["git", "cat-file", "blob", spec],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def frontmatter_status(text):
    """Value of the `status:` key in the leading `---` YAML frontmatter
    (quotes stripped), or None."""
    lines = (text or "").split("\n")
    if lines[0].strip() != "---":
        return None
    status = None
    for line in lines[1:]:
        if line.strip() == "---":
            return status
        m = STATUS_RE.match(line)
        if m and status is None:
            status = m.group(1).strip("'\"")
    return None  # unterminated: not frontmatter


def status_transitions(cwd, entries, env=None):
    """TASK-59#2: staged task files whose status becomes In Progress/Done
    relative to HEAD (paths as staged)."""
    found = []
    for letter, path, new_path in entries:
        staged = new_path or path
        if letter == "D" or not staged.startswith(TASKS):
            continue
        status = frontmatter_status(read_blob(cwd, ":" + staged, env))
        if status not in TRANSITION_STATUSES:
            continue
        if frontmatter_status(read_blob(cwd, "HEAD:" + path)) != status:  # ---- 4
            found.append(staged)
    return found


def inspect_index(cwd, env=None):
    """(staged entries, status transitions) of the index `env` points at,
    or None when the index can't be read."""
    entries = staged_entries(cwd, env=env)
    if entries is None:
        return None
    return entries, status_transitions(cwd, entries, env)


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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 5
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return None

    adds = []
    for segment in split_segments(tokens):
        head = command_head(segment)
        if head < len(segment) and segment[head] in ("cd", "pushd", "popd"):  # ---- 6
            return None
        j = git_subcommand_index(segment)
        if j is None:
            continue
        sub, args = segment[j], segment[j + 1 :]
        if sub not in ("add", "commit"):
            continue
        if j != head + 1 or any(t.startswith("GIT_") for t in segment[:head]):  # ---- 7
            # global flags (`git -C x ...`) or `GIT_*=` env may point at
            # another repo/index: only the commit itself is fine
            if sub == "commit":
                return adds, False
            return None
        if sub == "add":
            # shell expansions/redirections can't be replayed faithfully
            if any(ch in a for a in args for ch in "$`<>"):  # ---- 8
                return None
            adds.append(args)
        else:  # sub == "commit" (only add/commit get past the check above)
            return adds, commit_stages_all(args)
    return None


@contextmanager
def simulated_index(cwd, adds, commit_all):
    """Replays the staging steps on a temporary copy of the index and
    yields the env that points git at it (None if the index can't be
    located). Never touches the real index."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "index"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        yield None
        return
    real_index = os.path.join(cwd, result.stdout.strip())

    with tempfile.TemporaryDirectory() as tmp:
        temp_index = os.path.join(tmp, "index")
        if os.path.isfile(real_index):
            shutil.copy2(real_index, temp_index)  # ---- 9
        env = dict(os.environ, GIT_INDEX_FILE=temp_index)  # ---- 10
        steps = [["git", "add", *args] for args in adds]
        if commit_all:
            steps.append(["git", "add", "-u"])
        for step in steps:
            subprocess.run(step, cwd=cwd, capture_output=True, text=True, env=env)
        yield env


def simulated_entries(cwd, adds, commit_all):
    """The staged entries after replaying the staging steps (see
    simulated_index), or None."""
    with simulated_index(cwd, adds, commit_all) as env:
        return staged_entries(cwd, env=env) if env else None


# --- TASK-60: dependencies of staged task files ------------------------------
# (parse_frontmatter/parse_task are copied from ../scripts/work_order.py and
# registered in dedup_drift_guard.REGISTRY)


def parse_frontmatter(text):
    """The top-level keys of a `---` frontmatter block. Values are strings,
    or lists for block (`- x`) and inline (`[x, y]`) lists. Only what
    backlog.md writes is understood - this is not a YAML parser."""

    def unquote(value):
        if len(value) >= 2 and value[0] == value[-1] == "'":
            return value[1:-1].replace("''", "'")
        if len(value) >= 2 and value[0] == value[-1] == '"':
            return value[1:-1]
        return value

    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}
    fields = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = KEY_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                fields[key] = [unquote(v.strip()) for v in inner.split(",")] if inner else []
            elif value in (">-", ">", "|", "|-"):
                fields[key] = ""
            else:
                fields[key] = unquote(value)
            continue
        item = line.strip()
        if key is None or not item:
            continue
        if item == "-" or item.startswith("- "):
            if not isinstance(fields[key], list):
                fields[key] = []
            fields[key].append(unquote(item[2:].strip()))
        elif isinstance(fields[key], str):
            fields[key] = (fields[key] + " " + item).strip()
    return fields


def parse_task(text):
    """{id, title, status, deps} of a task file, or None without an id."""
    fm = parse_frontmatter(text)
    task_id = fm.get("id")
    if not isinstance(task_id, str) or not task_id:
        return None
    deps = fm.get("dependencies") or []
    if isinstance(deps, str):
        deps = [deps]
    return {
        "id": task_id.upper(),
        "title": fm.get("title") or "",
        "status": fm.get("status") or "",
        "deps": sorted({d.upper() for d in deps if d}),
    }


def dependencies_changed(cwd, path, new_path, env=None):
    """True if the staged task file `new_path` lists other dependencies
    than `path` at HEAD. A file missing on either side or without a task
    id is not a dependency change."""

    def deps_at(spec):
        result = subprocess.run(
            ["git", "show", spec],
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
        )
        task = parse_task(result.stdout) if result.returncode == 0 else None
        return task["deps"] if task else None

    before = deps_at(f"HEAD:{path}")
    after = deps_at(f":{new_path}")
    return before is not None and after is not None and before != after  # ---- 11


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


def check_scope(entries, transitions=(), deps_changed=None):
    """Returns a deny message, or None if the staged set is acceptable.
    `transitions` lists staged task paths whose status becomes In Progress
    or Done (status_transitions). `deps_changed(path, new_path)` tells
    whether a staged task file changed its dependencies (TASK-60); without
    it no task file qualifies."""
    new_drafts = [
        e for e in entries if e[0] in ("A", "C") and (e[2] or e[1]).startswith(DRAFTS)
    ]
    if len(new_drafts) >= 2:  # ---- 12
        return (
            "[claude-code-agile-hooks] 드래프트 생성 커밋에는 새 드래프트 한 장만 담는다 — "
            "스테이징에 새 드래프트가 여러 개 있습니다:\n"
            + format_offenders(new_drafts)
            + "\n한 장씩 커밋하세요. 나머지는 'git restore --staged <path>'로 내린 뒤 "
            "다음 커밋으로 나누세요."
        )
    if new_drafts:
        offenders = [
            e for e in entries if not all(p.startswith(DRAFTS) for p in entry_paths(e))
        ]
        if offenders:
            return (
                "[claude-code-agile-hooks] 드래프트 생성 커밋은 드래프트만 담는다 — 스테이징에 새 "
                "드래프트(backlog/drafts/)와 그 밖의 파일이 섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n드래프트만 먼저 커밋하고, 나머지는 'git restore --staged <path>'로 "
                "내린 뒤 별도 커밋으로 나누세요."
            )

    renames = [e for e in entries if is_promotion_rename(e)]
    deleted_drafts = [e for e in entries if e[0] == "D" and e[1].startswith(DRAFTS)]
    added_tasks = [e for e in entries if e[0] == "A" and e[1].startswith(TASKS)]
    if renames or (deleted_drafts and added_tasks):  # ---- 13
        offenders = [
            e
            for e in entries
            if not is_promotion_rename(e)
            and not (e[0] == "D" and e[1].startswith(DRAFTS))
            and not all(p.startswith(TASKS) for p in entry_paths(e))
        ]
        if offenders:
            return (
                "[claude-code-agile-hooks] 승격 커밋은 승격만 담는다 — 스테이징에 드래프트 승격"
                "(backlog/drafts/ → backlog/tasks/)과 그 밖의 파일이 섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n승격(과 승격된 태스크의 ref/doc 연결)만 먼저 커밋하고, 나머지는 "
                "'git restore --staged <path>'로 내린 뒤 별도 커밋으로 나누세요."
            )

    if transitions:
        offenders = [e for e in entries if (e[2] or e[1]) != transitions[0]]  # ---- 14
        if len(transitions) > 1 or offenders:
            listed = "\n".join(f"  - {p} (상태 전환)" for p in transitions)
            return (
                "[claude-code-agile-hooks] 상태 전환 커밋(→ In Progress, → Done)에는 그 "
                "태스크 파일만 담는다 — 스테이징에 상태 전환과 그 밖의 변경이 섞여 있습니다:\n"
                + listed
                + ("\n" + format_offenders(offenders) if offenders else "")
                + "\n태스크 파일 하나의 상태 전환만 먼저 커밋하고, 나머지는 "
                "'git restore --staged <path>'로 내린 뒤 별도 커밋으로 나누세요."
            )

    if any(WORK_ORDER in entry_paths(e) for e in entries):  # ---- 15
        offenders = [
            e
            for e in entries
            if WORK_ORDER not in entry_paths(e)
            and not (
                e[0] in ("M", "R")
                and all(p.startswith(TASKS) for p in entry_paths(e))
                and deps_changed is not None
                and deps_changed(e[1], e[2] or e[1])
            )
        ]
        if offenders:
            return (
                "[claude-code-agile-hooks] 작업 순서 커밋은 backlog/work-order.md와 의존"
                "(dependencies)을 고친 태스크 파일만 담는다 — 스테이징에 그 밖의 파일이 "
                "섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n작업 순서와 의존 변경만 먼저 커밋하고, 나머지는 "
                "'git restore --staged <path>'로 내린 뒤 별도 커밋으로 나누세요."
            )
    return None


def scope_message(cwd, env=None):
    """check_scope() on the index `env` points at (the real one if None);
    None when the index can't be read."""
    inspected = inspect_index(cwd, env=env)
    if inspected is None:
        return None
    entries, transitions = inspected
    return check_scope(
        entries,
        transitions,
        lambda path, new_path: dependencies_changed(cwd, path, new_path, env),
    )


def command_target_dir(command, cwd):
    """TASK-75 B2/B4/B6: [(segment, directory)] for every shell segment of
    `command` (the segments split_segments gives, after heredoc bodies are
    dropped and `\\`-newline continuations joined). `directory` is the one
    the segment acts on: the session `cwd`, moved by the earlier
    `cd`/`pushd <dir>` of the same line (relative to the directory before
    it), then for git its `-C <dir>` options in order, and for backlog a
    `BACKLOG_CWD=<dir>` in front of it (also behind `env`) or exported
    earlier on the line (relative to the segment's directory).

    A cd counts only where bash keeps it: not inside `( )` or `$( )` once
    they close, not in a pipeline (`cd x | ...`), not in a list sent to the
    background (`... &`).

    `directory` is None when it can't be known statically: a path with
    `$`, a backtick, a glob or `{` (`cd "$X"`, `cd $(...)`), `cd -`,
    `popd`, `pushd` without a directory, a cd with more than one argument,
    a relative cd while CDPATH is set, a directory that doesn't exist, a cd
    that may not have run (after `||` or a shell keyword such as `then`; a
    cd behind `&&` once its `&&` chain ends; any cd once an `||` other than
    `|| exit` / `|| return` follows it), a bare `BACKLOG_CWD=...` assignment
    (exported or not is unknown), and git with `--git-dir`, `--work-tree`,
    `GIT_DIR=` or `GIT_WORK_TREE=`. A line that can't be tokenized gives
    [(None, cwd)], or [(None, None)] when its text mentions a directory
    changer."""

    def resolve(base, path):
        if path is None:
            return None
        if path.startswith("~"):
            path = os.path.expanduser(path)
        if not path or path.startswith("~") or any(c in path for c in "$`*?[{"):
            return None
        if not os.path.isabs(path):
            if not base:
                return None
            path = os.path.join(base, path)
        path = os.path.normpath(path)
        return path if os.path.isdir(path) else None

    def operands(args):
        words = []
        i = 0
        while i < len(args):
            tok = args[i]
            if tok and set(tok) <= set("<>&"):
                if words and words[-1].isdigit():
                    words.pop()
                i += 2
                continue
            words.append(tok)
            i += 1
        return words

    def cd_target(name, args, base):
        words = operands(args)
        while words and words[0].startswith("-") and words[0] != "-":
            if words.pop(0) == "--":
                break
        if name == "popd" or len(words) > 1:
            return None
        if not words:
            return None if name == "pushd" else resolve(None, os.path.expanduser("~"))
        word = words[0]
        if word == "-" or (name == "pushd" and word[:1] in ("+", "-")):
            return None
        word = os.path.expanduser(word)
        if os.environ.get("CDPATH") and word.split("/")[0] not in ("", ".", ".."):
            return None
        return resolve(base, word)

    stripped = strip_heredoc_bodies(command or "").replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        changer = re.search(
            r"\b(?:cd|pushd|popd)\b|(?:^|\s)-C\b|--git-dir|--work-tree"
            r"|GIT_DIR|GIT_WORK_TREE|BACKLOG_CWD",
            stripped,
        )
        return [(None, None if changer else cwd)]

    def operator(run):
        if "||" in run:
            return ("op", "or")
        if "&&" in run:
            return ("op", "and")
        if "|" in run:
            return ("op", "pipe")
        if "&" in run:
            return ("op", "bg")
        return ("op", "seq")

    # a separator token can hold several operators and parens (`)&&(`)
    events = []
    current = []
    for tok in tokens:
        if not (tok and set(tok) <= set(";&|()\n")):
            current.append(tok)
            continue
        if current:
            events.append(("segment", current))
            current = []
        for part in re.findall(r"[()]|[^()]+", tok):
            events.append(("paren", part) if part in "()" else operator(part))
    if current:
        events.append(("segment", current))

    keywords = {"if", "then", "else", "elif", "do", "while", "until"}
    directory, backlog_cwd, git_env = cwd, "", False
    snapshot = (directory, backlog_cwd, git_env)
    fragile = None
    previous = "seq"
    stack = []
    pairs = []
    for index, (kind, value) in enumerate(events):
        following = events[index + 1] if index + 1 < len(events) else ("op", "seq")
        if kind == "paren":
            if value == "(":
                stack.append((directory, backlog_cwd, git_env, snapshot, fragile))
                snapshot = (directory, backlog_cwd, git_env)
                fragile = None
                previous = "seq"
            elif stack:
                directory, backlog_cwd, git_env, snapshot, fragile = stack.pop()
            continue
        if kind == "op":
            if value == "or" and fragile is not None:
                nxt = following[1] if following[0] == "segment" else []
                head = command_head(nxt)
                if head >= len(nxt) or nxt[head] not in ("exit", "return"):
                    directory = None
            elif value == "seq":
                if fragile == "end":
                    directory = None
                fragile = None
                snapshot = (directory, backlog_cwd, git_env)
            elif value == "bg":
                directory, backlog_cwd, git_env = snapshot
                fragile = None
            previous = value
            continue

        segment = value
        start = 0
        while start < len(segment) and segment[start] in keywords:
            start += 1
        head = start + command_head(segment[start:])
        name = segment[head] if head < len(segment) else ""
        target = directory
        if os.path.basename(name) == "git":
            if git_env or any(
                t.startswith(("GIT_DIR=", "GIT_WORK_TREE=")) for t in segment[:head]
            ):
                target = None
            j = head + 1
            while target is not None and j < len(segment):
                tok = segment[j]
                if tok == "-C":
                    target = resolve(target, segment[j + 1] if j + 1 < len(segment) else None)
                    j += 2
                elif tok in ("--git-dir", "--work-tree") or tok.startswith(
                    ("--git-dir=", "--work-tree=")
                ):
                    target = None
                elif tok in ("-c", "--namespace"):
                    j += 2
                elif tok.startswith("-"):
                    j += 1
                else:
                    break
        elif os.path.basename(name) in ("backlog", "backlog.md"):
            env_value = backlog_cwd
            for tok in segment[:head]:
                if tok.startswith("BACKLOG_CWD="):
                    env_value = tok[len("BACKLOG_CWD=") :]
            if env_value is None:
                target = None
            elif env_value:
                target = resolve(target, env_value)
        pairs.append((segment, target))

        if previous == "pipe" or following == ("op", "pipe"):
            continue
        conditional = start > 0 or previous in ("and", "or")
        if name in ("cd", "pushd", "popd"):
            if start > 0 or previous == "or":
                directory = None
            else:
                directory = cd_target(name, segment[head + 1 :], directory)
                fragile = "end" if previous == "and" else "or"
        elif name in ("export", "unset") or head == len(segment):
            for tok in segment[start:]:
                key, eq, val = tok.partition("=")
                if key == "BACKLOG_CWD":
                    if name == "unset":
                        backlog_cwd = ""
                    elif conditional or name != "export" or not eq:
                        backlog_cwd = None
                    else:
                        backlog_cwd = val
                elif key in ("GIT_DIR", "GIT_WORK_TREE") and name != "unset":
                    git_env = True
    return pairs


def target_roots(command, cwd, match, fallback):
    """TASK-75: [(root, [results])] - the gated segments of `command`
    (`match(segment)` is not None) grouped by the git top-level of the
    directory each one targets (command_target_dir), in first-seen order.
    A target that isn't a backlog project is dropped, whatever the session
    cwd is (B7). A gated segment whose directory can't be known statically
    is denied (B6). An untokenizable line counts the hook's own text-match
    results (`fallback`) against its single pseudo-segment."""
    groups = []
    for segment, directory in command_target_dir(command, cwd):
        if segment is None:
            found = list(fallback)
        else:
            value = match(segment)
            found = [] if value is None else [value]
        if not found:
            continue
        if directory is None:
            deny(
                "[claude-code-agile-hooks] 이 명령이 어느 저장소를 겨누는지 정적으로 알 수 "
                '없어 거부합니다(cd "$X" · cd $(...) · cd - · git -C "$D" · '
                "BACKLOG_CWD=$Y · 없는 디렉터리 · || 뒤나 조건부 cd 등). 대상 디렉터리를 "
                "리터럴 경로로 적거나(cd /path/to/repo && ...), 그 저장소에서 명령을 "
                "따로 실행하세요."
            )
        root = project_root(directory) or directory
        if not is_backlog_project(root):
            continue
        for known, values in groups:
            if known == root:
                values.extend(found)
                break
        else:
            groups.append((root, found))
    return groups


def segment_commits(segment):
    """TASK-75: True for a `git commit` segment in command position, else
    None (the match function target_roots takes)."""
    j = git_subcommand_index(segment)
    return True if j is not None and segment[j] == "commit" else None


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

    if not command_runs_git(command, "commit"):  # ---- 16
        sys.exit(0)
    if not has_command("git"):
        sys.exit(0)
    for root, _ in target_roots(command, cwd, segment_commits, [True]):  # ---- 17
        check_repo(root, command, cwd)
    sys.exit(0)


def merge_in_progress(root):
    """TASK-77: True only when git confirms a merge is in progress in `root`
    (MERGE_HEAD resolves). Any failure - not a repository, git missing, a
    timeout - is False, so the caller keeps checking (B3)."""
    try:
        result = subprocess.run(
            ["git", "-C", root, "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def check_repo(root, command, cwd):
    if merge_in_progress(root):  # ---- 19
        return
    # the replayed `git add`s ran in the session cwd: only replay them onto
    # the index of the repository that cwd belongs to
    plan = staging_plan(command) if (project_root(cwd) or cwd) == root else None
    if plan and (plan[0] or plan[1]):  # ---- 18
        with simulated_index(cwd, plan[0], plan[1]) as env:
            message = scope_message(root, env) if env else None
    else:
        message = scope_message(root)
    if message:
        deny(message)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 토큰화 실패 시 fail-closed
#   설명: 따옴표 불균형으로 토큰화가 안 되면 명령 위치를 구분할 수 없다. 부분 문자열이 있으면 커밋으로 보고 실제 인덱스를 검사한다. 인덱스를 한 번 더 읽는 것은 무해하고, 건너뛴 범위 검사는 복구할 수 없다.
#   관련: hooks/pre_commit_check.py, hooks/dedup_drift_guard.py
#   개념: fail-closed
# 2 git -z 출력을 NUL로 파싱
#   설명: --name-status -z 는 경로를 NUL로 구분해 공백·한글·개행이 든 경로도 인용 없이 안전하게 받는다. R/C 상태는 경로가 둘이라 필드 개수가 다르다는 점이 파서의 핵심이다.
#   개념: NUL 구분, rename detection
# 3 인덱스를 못 읽으면 검사 포기
#   설명: git diff --cached 가 실패하면 None을 돌려 main이 deny하지 않고 통과시킨다. 읽을 수 없는 인덱스로 추측해 막는 것보다 훅이 길을 막지 않는 쪽을 택한 fail-open 결정이다.
#   개념: fail-open
# 4 상태 전환은 HEAD와 비교
#   설명: 스테이징된 blob의 status 가 In Progress/Done 이어도 HEAD에서도 같으면 전환이 아니다. 제목이 바뀌어 경로가 달라질 수 있으므로 HEAD 쪽은 옛 경로(path)로 읽어 이름 변경을 따라간다. 새 파일은 HEAD에 없으므로 None과 비교돼 전환으로 잡힌다.
#   관련: TASK-59#2
# 5 검출과 같은 세그먼트로 재생
#   설명: TASK-39: command_runs_git() 이 판단하는 것과 같은 세그먼트를 쓴다. 히어독 본문을 버리고 줄 이음을 합치고 명령 위치의 git만 찾는다. 그래야 검출과 시뮬레이션이 어긋나 echo git add 같은 텍스트가 재생되는 일이 없다.
#   관련: TASK-39, TASK-34
# 6 cd/pushd 가 있으면 시뮬레이션 포기
#   설명: 작업 디렉터리가 바뀌면 이후 git add 가 다른 저장소를 가리킨다. 안전하게 재생할 수 없으므로 None을 돌려 실제 인덱스를 그대로 검사하게 한다.
# 7 전역 플래그·GIT_ 환경은 재생 불가
#   설명: git -C x add 나 GIT_DIR= 같은 지정은 다른 저장소·인덱스를 가리킬 수 있다. add 라면 시뮬레이션을 포기하고, commit 이라면 앞선 add 만 재생하고 -a 는 무시한다.
#   관련: hooks/pre_commit_check.py (git -C 는 cwd 인덱스를 본다는 알려진 한계)
# 8 셸 확장은 충실히 재생할 수 없다
#   설명: $VAR, 백틱, 리디렉션이 든 인자는 훅 시점에 값을 알 수 없다. 틀린 파일을 스테이징한 것으로 시뮬레이션하면 오탐·미탐이 생기므로 시뮬레이션 자체를 포기한다.
# 9 인덱스 복사본의 mtime 보존
#   설명: git은 인덱스 파일보다 오래되지 않은 항목(racy)만 내용을 비교한다. 복사본의 mtime이 새로 찍히면 같은 초 안에 한 같은 크기의 편집이 가려진다. copy2로 mtime을 유지해 이를 막는다.
#   개념: racy git, GIT_INDEX_FILE
# 10 실제 인덱스는 건드리지 않는다
#   설명: PreToolUse 는 Bash 명령보다 먼저 돌아 인덱스가 명령 실행 전 상태다. 같은 줄의 git add / commit -a 를 임시 복사본 인덱스에 재생해 일반적인 경우를 닫는다. 실제 인덱스를 바꾸면 훅 부작용이 되기 때문에 반드시 복사본만 쓴다.
#   개념: GIT_INDEX_FILE
# 11 의존 변경 판정은 양쪽 모두 있을 때만
#   설명: 한쪽 파일이 없거나 task id 가 없으면 의존 변경이 아니다. 신규·삭제 태스크가 작업 순서 커밋에 섞여 들어오는 것을 막기 위한 규칙(TASK-60)과 맞물린다.
#   관련: TASK-60, scripts/work_order.py
# 12 드래프트는 한 커밋에 한 장
#   설명: TASK-59#1: 히스토리에서 각 드래프트(드래프트 1장 → 커밋)가 자기 지점을 갖게 한다.
#   관련: TASK-59
# 13 승격 커밋 판정: 이름 변경 또는 삭제+추가
#   설명: git의 rename 감지가 놓치는 경우를 위해, 드래프트 삭제와 태스크 추가가 함께 있으면 승격으로 본다. 승격 직후의 --add-ref, --doc 편집과 다른 태스크 파일 수정은 허용하고 코드·문서·설정은 거부한다.
#   관련: TASK-29
# 14 상태 전환 커밋은 그 태스크 파일만
#   설명: 전환 태스크 파일(이름 변경 포함) 외의 경로가 있거나 전환 파일이 둘 이상이면 거부한다. 읽는 것은 워크트리가 아니라 스테이징된 blob이다.
#   관련: TASK-59#2
# 15 작업 순서 커밋은 의존 변경과만 함께
#   설명: 의존을 정리하고 작업 순서를 다시 만드는 일이 한 묶음의 커밋이 되게 한다. dependencies 프런트매터가 HEAD와 달라진 태스크 파일만 허용한다.
#   관련: TASK-60, backlog/work-order.md
# 16 커밋이 아니면 바로 통과
#   설명: if 필터 없이 모든 Bash 호출에 등록돼 있다(절대경로·환경변수 접두 커밋을 놓치지 않기 위해). 따라서 커밋이 아닌 줄은 파싱 직후 빠져나가 비용을 한 번의 짧은 파싱으로 제한한다.
#   관련: TASK-39
# 17 세션 cwd가 아니라 커밋 대상 저장소의 인덱스를 검사
#   설명: 같은 줄의 앞선 cd와 git -C로 커밋이 겨누는 디렉터리를 정하고, 그 git top-level이 backlog 프로젝트일 때 그 저장소의 인덱스를 검사한다. 대상이 backlog 프로젝트가 아니면 통과하고, 대상을 정적으로 알 수 없으면 target_roots가 거부한다. 앞선 git add 재생은 세션 cwd 저장소가 곧 대상일 때만 한다(add가 세션 cwd에서 돌았으므로).
#   관련: TASK-75 (B2 · B3 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
# 18 시뮬레이션이 필요한 경우만 임시 인덱스 사용
#   설명: 같은 줄에 앞선 add 나 commit -a 가 없으면 재생할 단계가 없으므로 실제 인덱스를 바로 검사한다. 이 훅은 PreToolUse 이지 git pre-commit 이 아니라서 터미널·GUI 커밋은 보지 못하는 점은 알려진 한계다(TASK-29).
#   관련: TASK-29
# 19 충돌 병합을 마무리하는 커밋은 검사하지 않음
#   설명: 대상 저장소에 MERGE_HEAD 가 있으면 이 커밋은 충돌을 푼 병합의 마무리다. 그 스테이징에는 병합되는 브랜치의 변경(상태 전환 · archive · 코드)이 한꺼번에 들어오지만 각 커밋은 원래 브랜치에서 이미 규칙 1~5를 통과했다. 충돌 없는 병합은 git 이 직접 커밋해 훅이 보지 않으므로, 충돌 여부라는 우연으로 막히던 것을 없앤다. MERGE_HEAD 확인이 실패하면 병합으로 보지 않고 검사한다.
#   관련: TASK-77, source-header TASK-42 · upkeep TASK-8(정리 브랜치 병합)
#   개념: fail-closed
