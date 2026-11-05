#!/usr/bin/env python3
"""PreToolUse (matcher: Bash)
TASK-60: in a backlog.md project, every promotion is followed by tidying
dependencies (`backlog task edit <ID> --dep ...`) and regenerating the work
order (backlog/work-order.md: which open tasks run in parallel, which in
sequence). This hook enforces it at the next stage command: before
`backlog draft promote` or `backlog task edit <ID> -s/--status "In Progress"`
it denies when backlog/work-order.md is missing or its recorded input hash
doesn't match the current incomplete task set and dependencies, and points
at the generator.

- Freshness is judged by hash, not timestamp: the first line of
  work-order.md is `<!-- work-order-hash: <sha256> -->` over the incomplete
  (status other than Done) task IDs of backlog/tasks/*.md and each one's
  `dependencies`. This hook recomputes it from the task files with verbatim
  copies of the generator's helpers (registered in
  dedup_drift_guard.REGISTRY together with ../scripts/work_order.py), so no
  subprocess is needed. Title/status edits (other than Done) don't make the
  file stale; a new task, a task becoming Done, or a dependency change does.
- Deps on Done or absent tasks count as satisfied (see work_order.py).
- No file and no incomplete task (a fresh project, or everything Done):
  nothing to order, pass. No file while incomplete tasks exist: deny, so a
  project adopting this hook generates the file once.
- No deadlock: the promote itself is judged on the state *before* it (the
  current tasks), so it passes when the file is current; the task it
  creates makes the file stale, and the next promote / In Progress waits
  until the generator runs - which nothing blocks. The work-order commit's
  scope is checked by backlog_commit_scope.py.
- Generator path in the message: install.sh copies scripts/work_order.py
  next to the installed hooks, so the hook names its sibling
  work_order.py; inside this repo (hooks/ next to scripts/) it names
  scripts/work_order.py.

Commands are found the way require_draft_first.py finds `task create`:
command position of a shell segment, heredoc bodies dropped, env
assignments and simple wrappers skipped, backlog compared by basename
(decision-1). If the line can't be tokenized a text match stands in
(conservative: this is a gate). Not seen: `bash -c`, aliases, the backlog
MCP server / browser UI, `cd other && ...` (the session cwd's backlog is
checked).

Fully self-contained: no imports from any other file in this repo."""

import hashlib
import json
import os
import re
import shlex
import sys

TASKS_DIR = os.path.join("backlog", "tasks")
WORK_ORDER = os.path.join("backlog", "work-order.md")
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
HASH_RE = re.compile(r"^<!-- work-order-hash: ([0-9a-f]{64}) -->$", re.MULTILINE)
NATURAL_RE = re.compile(r"(\d+)")
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
PROMOTE_FALLBACK_RE = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?backlog(?:\.md)?\s+drafts?\s+promote\b", re.MULTILINE
)
IN_PROGRESS_FALLBACK_RE = re.compile(
    r"(?:^|[;&|(\s])(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+edit\s+\S+"
    r".*?(?:^|\s)(?:-s|--status)(?:=|\s+)['\"]?in progress\b",
    re.IGNORECASE | re.DOTALL,
)


# --- command parsing (is_backlog_project/strip_heredoc_bodies/tokenize/
# split_segments/command_head are registered in dedup_drift_guard.REGISTRY) ---


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


# --- index inspection --------------------------------------------------------


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


def segment_starts_stage(segment):
    """True for `backlog draft promote ...` or
    `backlog task edit <ID> ... -s "In Progress"` in command position."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
        return False
    rest = segment[i + 1 :]
    words = [t for t in rest if not t.startswith("-")]
    if words[:1] in (["draft"], ["drafts"]) and words[1:2] == ["promote"]:
        return True
    if len(rest) < 2 or rest[0] not in ("task", "tasks") or rest[1] != "edit":
        return False
    target = None
    status = None
    j = 2
    while j < len(rest):
        tok = rest[j]
        if tok in ("-s", "--status"):
            status = rest[j + 1] if j + 1 < len(rest) else None
            j += 2
            continue
        if tok.startswith("--status="):
            status = tok[len("--status=") :]
        elif not tok.startswith("-") and target is None:
            target = tok
        j += 1
    return target is not None and status is not None and status.lower() == "in progress"


def command_starts_stage(command):
    if not command:
        return False
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return bool(
            PROMOTE_FALLBACK_RE.search(stripped)
            or IN_PROGRESS_FALLBACK_RE.search(stripped)
        )
    return any(segment_starts_stage(s) for s in split_segments(tokens))


# --- work order (parse_frontmatter/parse_task/natural_key/read_tasks/
# incomplete_tasks/input_hash are copied from ../scripts/work_order.py and
# registered in dedup_drift_guard.REGISTRY) ---


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


def natural_key(task_id):
    """TASK-2 sorts before TASK-10."""
    return [int(p) if p.isdigit() else p for p in NATURAL_RE.split(task_id)]


def read_tasks(cwd):
    """{ID: task} for every task file in backlog/tasks/."""
    tasks_dir = os.path.join(cwd, TASKS_DIR)
    try:
        names = sorted(os.listdir(tasks_dir))
    except OSError:
        return {}
    tasks = {}
    for name in names:
        if not name.endswith(".md"):
            continue
        with open(os.path.join(tasks_dir, name), encoding="utf-8", errors="replace") as f:
            task = parse_task(f.read())
        if task:
            tasks[task["id"]] = task
    return tasks


def incomplete_tasks(tasks):
    return {
        task_id: task
        for task_id, task in tasks.items()
        if task["status"].strip().lower() != "done"
    }


def input_hash(incomplete):
    """sha256 over the incomplete task ID set and each one's dependencies."""
    lines = [
        f"{task_id}:{','.join(incomplete[task_id]['deps'])}"
        for task_id in sorted(incomplete, key=natural_key)
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def recorded_hash(cwd):
    """The hash on work-order.md's header line, or None."""
    try:
        with open(os.path.join(cwd, WORK_ORDER), encoding="utf-8", errors="replace") as f:
            m = HASH_RE.search(f.read())
    except OSError:
        return None
    return m.group(1) if m else None


def work_order_script():
    """The installed copy next to this hook, or scripts/work_order.py when
    running from the repo checkout."""
    here = os.path.dirname(os.path.abspath(__file__))
    sibling = os.path.join(here, "work_order.py")
    repo_copy = os.path.join(os.path.dirname(here), "scripts", "work_order.py")
    if not os.path.isfile(sibling) and os.path.isfile(repo_copy):
        return repo_copy
    return sibling


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

    if not command_starts_stage(command):
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    incomplete = incomplete_tasks(read_tasks(cwd))
    recorded = recorded_hash(cwd)
    if recorded is None and not incomplete:
        sys.exit(0)
    if recorded == input_hash(incomplete):
        sys.exit(0)

    problem = (
        "작업 순서 파일(backlog/work-order.md)이 없습니다"
        if recorded is None
        else "작업 순서 파일(backlog/work-order.md)이 현재 미완료 태스크 · 의존과 맞지 않습니다"
    )
    deny(
        f"[claude-code-agile-hooks] {problem}. 승격 뒤에는 의존을 "
        "'backlog task edit <ID> --dep <ID>'로 정리하고, 프로젝트 루트에서 "
        f"'python3 {work_order_script()}'로 작업 순서를 다시 만든 다음, "
        "backlog/work-order.md(와 의존을 고친 태스크 파일)만 별도 커밋으로 남기고 "
        "이 명령을 다시 실행하세요."
    )


if __name__ == "__main__":
    main()
