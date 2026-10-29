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
        if frontmatter_status(read_blob(cwd, "HEAD:" + path)) != status:
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
    return before is not None and after is not None and before != after


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
    if len(new_drafts) >= 2:
        # TASK-59#1: one draft per commit, so each draft has its own point
        # in history (draft 1장 → 커밋)
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
                "[claude-code-agile-hooks] 승격 커밋은 승격만 담는다 — 스테이징에 드래프트 승격"
                "(backlog/drafts/ → backlog/tasks/)과 그 밖의 파일이 섞여 있습니다:\n"
                + format_offenders(offenders)
                + "\n승격(과 승격된 태스크의 ref/doc 연결)만 먼저 커밋하고, 나머지는 "
                "'git restore --staged <path>'로 내린 뒤 별도 커밋으로 나누세요."
            )

    if transitions:
        offenders = [e for e in entries if (e[2] or e[1]) != transitions[0]]
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

    if any(WORK_ORDER in entry_paths(e) for e in entries):
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
        with simulated_index(cwd, plan[0], plan[1]) as env:
            message = scope_message(cwd, env) if env else None
    else:
        message = scope_message(cwd)
    if message:
        deny(message)
    sys.exit(0)


if __name__ == "__main__":
    main()
