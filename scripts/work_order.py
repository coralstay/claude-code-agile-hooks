#!/usr/bin/env python3
"""TASK-60: writes backlog/work-order.md - the order in which the open
tasks of a backlog.md project can be worked on.

Usage: work_order.py [project_dir]     (default: the current directory)

install.sh copies this script next to the hooks
($HOME/.claude/hooks/claude-code-agile-hooks/work_order.py), so in any
project it runs as
`python3 $HOME/.claude/hooks/claude-code-agile-hooks/work_order.py`.

How it works:
- Dependencies are read straight from the `dependencies:` key of each
  backlog/tasks/*.md frontmatter (block list `- TASK-1`, inline
  `[TASK-1, TASK-2]` or `[]`), not from CLI output - the same data
  `backlog task edit --dep` writes, and readable by a hook without a
  subprocess. IDs are compared upper-cased.
- Incomplete = status other than Done (case-insensitive). Only files in
  backlog/tasks/ are read; backlog/completed/ and backlog/archive/ are not.
- A dependency on a task outside the incomplete set counts as satisfied:
  a Done task is finished, and an absent ID (archived, completed/, typo)
  can't hold anything back. Absent IDs are listed in the file so a typo
  stays visible.
- The incomplete tasks are sorted into levels (Kahn): level 1 = no open
  dependency, level n = depends on something at level n-1. Same level =
  parallel, levels run in order. Rows are sorted by level, then by ID in
  natural order (TASK-2 before TASK-10), so the output is deterministic.
- A dependency cycle exits 1 with one cycle listed and writes nothing.
- The first line is `<!-- work-order-hash: <sha256> -->`. The hash covers
  only the incomplete task ID set and each one's dependencies - not
  titles, statuses other than Done, or timestamps - so the hook
  require_work_order.py can tell whether the file is current without
  regenerating it.

parse_frontmatter/parse_task/natural_key/read_tasks/incomplete_tasks/
input_hash are copied verbatim into hooks/require_work_order.py and
registered in dedup_drift_guard.REGISTRY (decision-2, decision-3)."""

import hashlib
import os
import re
import sys

TASKS_DIR = os.path.join("backlog", "tasks")
WORK_ORDER = os.path.join("backlog", "work-order.md")
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
HASH_RE = re.compile(r"^<!-- work-order-hash: ([0-9a-f]{64}) -->$", re.MULTILINE)
NATURAL_RE = re.compile(r"(\d+)")


class CycleError(Exception):
    def __init__(self, cycle):
        super().__init__(" -> ".join(cycle))
        self.cycle = cycle


# --- shared with hooks/require_work_order.py (dedup REGISTRY) ---


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


# --- levels / rendering -------------------------------------------------------


def compute_levels(incomplete):
    """Lists of task IDs per level. Raises CycleError on a cycle."""
    open_deps = {
        task_id: {d for d in task["deps"] if d in incomplete}
        for task_id, task in incomplete.items()
    }
    levels = []
    done = set()
    while len(done) < len(open_deps):
        ready = [t for t, deps in open_deps.items() if t not in done and deps <= done]
        if not ready:
            raise CycleError(find_cycle(open_deps, done))
        levels.append(sorted(ready, key=natural_key))
        done.update(ready)
    return levels


def find_cycle(open_deps, done):
    """Every task left over by compute_levels has a dependency that is also
    left over, so following the smallest one must come back around."""
    current = min((t for t in open_deps if t not in done), key=natural_key)
    path = []
    while current not in path:
        path.append(current)
        current = min((d for d in open_deps[current] if d not in done), key=natural_key)
    return path[path.index(current) :] + [current]


def render(incomplete, all_ids):
    lines = [
        f"<!-- work-order-hash: {input_hash(incomplete)} -->",
        "# 작업 순서",
        "",
        "`work_order.py`가 backlog/tasks의 의존(`dependencies`)으로 만든 파일이다 — 직접 "
        "고치지 말고 다시 생성한다. 같은 단계의 태스크는 병렬로, 단계는 위에서 아래로 "
        "순차로 진행한다. Done 태스크와 없는 태스크에 대한 의존은 충족된 것으로 본다.",
        "",
    ]
    levels = compute_levels(incomplete)
    if not levels:
        lines.append("미완료 태스크가 없습니다.")
    else:
        lines += ["| 단계 | ID | 제목 |", "|---|---|---|"]
        for n, level in enumerate(levels, 1):
            for task_id in level:
                title = incomplete[task_id]["title"].replace("|", "\\|")
                lines.append(f"| {n} | {task_id} | {title} |")
    absent = sorted(
        {d for task in incomplete.values() for d in task["deps"] if d not in all_ids},
        key=natural_key,
    )
    if absent:
        lines += [
            "",
            "없는 태스크에 대한 의존(충족으로 간주): " + ", ".join(absent),
        ]
    return "\n".join(lines) + "\n"


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print("사용법 (Usage): work-order [project_dir]")
        print("  backlog/tasks/*.md의 의존 관계를 위상 정렬(Kahn)하여 backlog/work-order.md를 생성합니다.")
        print("  project_dir 생략 시 현재 디렉터리($PWD)를 대상으로 합니다.")
        return 0
    if len(argv) > 1:
        print("usage: work_order.py [project_dir]", file=sys.stderr)
        return 2
    cwd = argv[0] if argv else os.getcwd()
    if not os.path.isfile(os.path.join(cwd, "backlog", "config.yml")):
        print(f"backlog.md 프로젝트가 아닙니다 (backlog/config.yml 없음): {cwd}", file=sys.stderr)
        return 1
    tasks = read_tasks(cwd)
    try:
        text = render(incomplete_tasks(tasks), set(tasks))
    except CycleError as exc:
        print(f"순환 의존이 있어 작업 순서를 만들 수 없습니다: {exc}", file=sys.stderr)
        return 1
    path = os.path.join(cwd, WORK_ORDER)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"작성: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
