#!/usr/bin/env python3
# ---
# title: require_design_propagation
# description: 최상위 설계 문서 변경이 컴포넌트 설계 문서에 전파되기 전에는 Done을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-63 (decision-15, RAIL-024): a change to the top-level design/ must be
propagated to the affected component design/ before the top-level task
moves to Done.

The 장 대응표 (chapter map) is never hardcoded: it is read on every run from
the top-level `design/00-문서-정보.md`, section `## 문서 계층` >
`### 장 대응표`, by the parse rules written above that table:

- columns: `최상위 장 | 범위 | <component> | ...`; a component column head is
  the directory name under `components/`.
- `최상위 장`: `00` is `design/00-문서-정보.md`, `N.MM` is
  `design/N-*/MM-*.md`, `부록 <이름>` is `design/부록-<이름, spaces as ->.md`.
- `범위`: `전체` is the whole chapter, `§n` the `## §n...` section, an area
  prefix (`ORC`, `RAIL`, ...) the `## <prefix>...` section. A change outside
  every listed section (chapter head, `## 원천`, any other `## ` section)
  counts for every row of that chapter.
- a cell lists the component's chapters joined by ` · `; `—` means none.

Applies only in a git repo whose root has `design/00-문서-정보.md` with
that heading pair (a component repo's own 00 doc has none): otherwise the
hook passes. A heading pair whose table breaks the rules denies the Done
move with the bad line - a broken map must not turn the check off.

Trigger: `backlog task edit <ID> -s Done` (`--status Done`, `--status=Done`,
any case) in command position, parsed like require_test_first.py (whose
helpers are copied here and kept equal by dedup_drift_guard.REGISTRY).

Range: the local `task/<ID>` branch of the target (`TASK-16`, `task-16`,
`16`), the current branch first; none -> pass. Its own commits are those
not reachable from any base ref that exists among origin/HEAD's target,
main, master, origin/main and origin/master (so neither a stale local nor
a stale remote main drags merged work in); no base -> pass. Only committed
changes count: the workflow commits each stage before Done, so the
working tree and index are not read. Merge commits are skipped.

Mapping: for each design/ file of a non-merge commit that names a chapter
of the table, every removed line is placed by the parent's `## ` headings
and every added line by the commit's (fenced code ignored); files outside
the table (diagrams, build scripts) are ignored.

Evidence per affected component C (a non-empty cell in a touched row):
- `components/C` (relative to the repo root, its own `.git`) has, on any
  ref (`git log --all`), a commit whose message has a line
  `Refs: coralstay-software-factory <...ID...>` - the ID matched case-
  insensitively and word-bounded (TASK-1 is not TASK-16 nor TASK-1.1), or
- a commit of the range carries the git trailer
  `Propagation-None: C: <non-empty reason>` (last paragraph of the
  message, as `git interpret-trailers` reads it). History is not
  rewritten, so it is added as a new commit, e.g.
  `git commit --allow-empty -m "..." -m "Propagation-None: C: 사유"`.
A missing components/C repo counts as no propagation (and says so).
Otherwise deny, listing each missing component with the top-level
chapters that hit it, its component chapters and both ways out.

Known limits (decision-1): command strings only - `bash -c`, scripts and
the backlog MCP server / web UI are not seen; the session cwd decides the
repo, so `cd elsewhere && backlog ...` is judged in the session's repo.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys

TAG = "[claude-code-agile-hooks]"
DOC_PATH = os.path.join("design", "00-문서-정보.md")
SECTION_HEADING = "문서 계층"
TABLE_HEADING = "장 대응표"
FIRST_COLUMNS = ["최상위 장", "범위"]
NONE_CELL = "—"
CELL_JOIN = " · "
WHOLE = "전체"
SCOPE_RE = re.compile(r"^(?:전체|§\d+|[A-Z]+)$")
CHAPTER_RE = re.compile(r"^(?:00|\d+\.\d{2}|부록 \S.*)$")
NUMBERED_RE = re.compile(r"^(\d+)\.(\d{2})$")
SEPARATOR_ROW_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
REFS_REPO = "coralstay-software-factory"
REFS_RE = re.compile(
    r"^[ \t]*refs:[ \t]*" + re.escape(REFS_REPO) + r"[ \t]+(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
TRAILER_KEY = "Propagation-None"
TRAILER_VALUE_RE = re.compile(r"^\s*([^\s:]+)\s*:\s*(\S.*)$")
BASE_CANDIDATES = (
    "refs/heads/main",
    "refs/heads/master",
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
)
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
DONE_FALLBACK_RE = re.compile(
    r"(?:^|[;&|(\s])(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+edit\s+(\S+)"
    r".*?(?:^|\s)(?:-s|--status)(?:=|\s+)['\"]?done\b",
    re.IGNORECASE | re.DOTALL,
)


class TableError(Exception):
    pass


# --- the 장 대응표 ---


def markdown_lines(text):
    """(line, heading level or 0, heading text) for every line, with fenced
    code blocks reported as plain lines (level 0) so a `## ` inside a fence
    is not a heading."""
    out = []
    in_fence = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):  # ---- 1
            in_fence = not in_fence
            out.append((line, 0, ""))
            continue
        m = None if in_fence else ATX_RE.match(line)
        if m:
            out.append((line, len(m.group(1)), m.group(2)))
        else:
            out.append((line, 0, ""))
    return out


def table_block(text):
    """Lines under `## 문서 계층` > `### 장 대응표` up to the next heading of
    level <= 3, or None when either heading is missing."""
    lines = markdown_lines(text)
    in_section = False
    start = None
    for i, (_, level, title) in enumerate(lines):
        if level == 2:
            in_section = title == SECTION_HEADING
        elif level == 3 and in_section and title == TABLE_HEADING:
            start = i + 1
            break
    if start is None:
        return None
    block = []
    for line, level, _ in lines[start:]:
        if 0 < level <= 3:
            break
        block.append(line)
    return block


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_cell(cell, where):
    if cell == NONE_CELL:
        return []
    if not cell:
        raise TableError(f"{where}: 빈 칸입니다(대응 장이 없으면 '{NONE_CELL}')")
    return [part.strip() for part in cell.split(CELL_JOIN)]


def parse_table(text):
    """{'components': [...], 'rows': [{'chapter', 'scope', 'cells'}]} from the
    top-level 00 doc, None when it has no `## 문서 계층` > `### 장 대응표`.
    TableError when the heading is there but the table breaks the rules -
    a broken map must not silently turn the check off."""
    block = table_block(text)
    if block is None:
        return None  # ---- 2
    table_lines = []
    for line in block:
        if line.strip().startswith("|"):
            table_lines.append(line.strip())
        elif table_lines:
            break
    if len(table_lines) < 3:  # ---- 3
        raise TableError("표가 없거나 머리 · 구분 줄 뒤에 행이 없습니다")
    header = split_row(table_lines[0])
    components = header[2:]
    if header[:2] != FIRST_COLUMNS or not components or not all(components):
        raise TableError(
            "표 머리는 '| 최상위 장 | 범위 | <컴포넌트> | ... |' 형식이어야 합니다: "
            + table_lines[0]
        )
    if not SEPARATOR_ROW_RE.match(table_lines[1].replace(" ", "")):
        raise TableError("표 머리 다음 줄은 구분 줄(| --- | ... |)이어야 합니다")
    rows = []
    for line in table_lines[2:]:
        cells = split_row(line)
        if len(cells) != len(header):
            raise TableError(f"칸 수가 머리({len(header)})와 다릅니다: {line}")
        chapter, scope = cells[0], cells[1]
        if not CHAPTER_RE.match(chapter):
            raise TableError(f"최상위 장 표기를 읽을 수 없습니다: {line}")
        if not SCOPE_RE.match(scope):
            raise TableError(f"범위 표기를 읽을 수 없습니다(전체 · §n · 영역 접두어): {line}")
        rows.append(
            {
                "chapter": chapter,
                "scope": scope,
                "cells": {
                    name: parse_cell(cell, line)
                    for name, cell in zip(components, cells[2:])
                },
            }
        )
    return {"components": components, "rows": rows}


def chapter_matches(chapter, relpath):
    """True if the repo-relative posix `relpath` is the file of `chapter`."""
    if chapter == "00":
        return relpath == "design/00-문서-정보.md"
    m = NUMBERED_RE.match(chapter)
    if m:
        pattern = rf"design/{m.group(1)}-[^/]+/{m.group(2)}-[^/]+\.md"  # ---- 4
        return re.fullmatch(pattern, relpath) is not None
    name = chapter[len("부록 ") :].replace(" ", "-")
    return relpath == f"design/부록-{name}.md"


# --- command parsing (copied from require_test_first.py; kept identical
# by dedup_drift_guard.REGISTRY) ---


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


def segment_done_target(segment):
    """The task argument of `backlog task edit <ID> ... -s Done` in command
    position, else None."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
        return None
    rest = segment[i + 1 :]
    if len(rest) < 2 or rest[0] not in ("task", "tasks") or rest[1] != "edit":
        return None
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
    if target is None or status is None or status.lower() != "done":
        return None
    return target


def done_targets(command):
    """Task arguments of every `backlog task edit <ID> ... -s Done` in
    command position. Unbalanced quotes: a text match stands in (gate)."""
    if not command:
        return []
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return [m.group(1) for m in DONE_FALLBACK_RE.finditer(stripped)]  # ---- 5
    targets = [segment_done_target(s) for s in split_segments(tokens)]
    return [t for t in targets if t is not None]


def same_task(token, task_id):
    """`AO-27`, `ao-27` and `27` all name task AO-27."""
    if token.upper() == task_id.upper():
        return True
    return token.isdigit() and task_id.rsplit("-", 1)[-1] == token


# --- git ---


def git_out(cwd, *args):
    """stdout of `git -C cwd args...`, or None when git fails."""
    result = subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def repo_root(cwd):
    out = git_out(cwd, "rev-parse", "--show-toplevel") if cwd else None
    return out.strip() if out else None


def find_task_branch(root, targets):
    """The local `task/<ID>` branch of a Done target, preferring the current
    branch; (branch, ID) or None."""
    head = (git_out(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip()
    refs = git_out(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/task/")
    branches = [head] + (refs or "").split()  # ---- 6
    for branch in branches:
        if not branch.startswith("task/"):
            continue
        task_id = branch[len("task/") :]
        if any(same_task(t, task_id) for t in targets):
            return branch, task_id
    return None


def base_refs(root):
    """Refs whose history is not the task's own: the remote default branch
    (origin/HEAD), main, master and their origin copies - whichever exist.
    Commits reachable from any of them are excluded, so a stale local or
    remote main can't pull already-merged work into the range."""
    candidates = []
    origin_head = git_out(root, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if origin_head and origin_head.strip():
        candidates.append(origin_head.strip())
    candidates.extend(BASE_CANDIDATES)
    found = []
    for ref in candidates:
        if ref not in found and git_out(root, "rev-parse", "--verify", "-q", ref) is not None:  # ---- 7
            found.append(ref)
    return found


def branch_log(root, branch, bases, *args, paths=()):
    """`git log` of the task branch's own commits (not reachable from any
    base)."""
    return git_out(root, "log", *args, branch, "--not", *bases, "--", *paths) or ""  # ---- 8


# --- which rows a commit touches ---


def section_titles(text):
    """[None] + the `## ` section title (or None) of every 1-based line."""
    titles = [None]
    current = None
    for _, level, title in markdown_lines(text):
        if level == 1:
            current = None
        elif level == 2:
            current = title
        titles.append(current)
    return titles


def changed_sections(old_text, new_text, diff):
    """Section titles (None = outside any `## `) of the lines a -U0 diff
    removes (placed in the old file) or adds (placed in the new file)."""
    old_titles = section_titles(old_text)
    new_titles = section_titles(new_text)
    found = set()
    for line in diff.split("\n"):
        m = HUNK_RE.match(line)
        if not m:
            continue
        for start, count, titles in (
            (m.group(1), m.group(2), old_titles),
            (m.group(3), m.group(4), new_titles),
        ):
            first = int(start)
            for n in range(first, first + int(count or "1")):
                found.add(titles[n] if n < len(titles) else None)
    return found


def scope_matches(scope, title):
    if title is None:
        return False
    tail = r"(?!\d)" if scope.startswith("§") else r"(?![A-Za-z0-9])"  # ---- 9
    return re.match(re.escape(scope) + tail, title) is not None


def rows_hit(rows, chapter, title):
    """Rows of `chapter` a change in section `title` belongs to: the matching
    §n / prefix rows plus 전체 rows, or every row of the chapter when no
    listed section matches (chapter head, `## 원천`, ...)."""
    of_chapter = [r for r in rows if r["chapter"] == chapter]
    specific = [
        r for r in of_chapter if r["scope"] != WHOLE and scope_matches(r["scope"], title)
    ]
    if not specific:  # ---- 10
        return of_chapter
    return specific + [r for r in of_chapter if r["scope"] == WHOLE]


def show(root, spec):
    return git_out(root, "show", spec) or ""


def commit_rows(root, sha, rows):
    chapters = list(dict.fromkeys(r["chapter"] for r in rows))
    names = git_out(
        root, "diff-tree", "--root", "--no-commit-id", "--no-renames", "-r",
        "--name-only", "-z", sha, "--", "design/",
    ) or ""
    hit = []
    for path in filter(None, names.split("\0")):
        matched = [c for c in chapters if chapter_matches(c, path)]
        if not matched:
            continue
        diff = git_out(
            root, "diff-tree", "--root", "--no-renames", "--no-ext-diff", "-p",
            "-U0", "--no-color", sha, "--", f":(literal){path}",  # ---- 11
        ) or ""
        titles = changed_sections(show(root, f"{sha}^:{path}"), show(root, f"{sha}:{path}"), diff)
        for chapter in matched:
            for title in titles:
                hit.extend(rows_hit(rows, chapter, title))
    return hit


def affected_components(root, shas, table):
    """{component: (top-level chapter labels, component chapters)} for every
    component with a non-empty cell in a touched row."""
    affected = {}
    for sha in shas:
        for row in commit_rows(root, sha, table["rows"]):
            label = row["chapter"] if row["scope"] == WHOLE else f"{row['chapter']} {row['scope']}"
            for name, chapters in row["cells"].items():
                if chapters:
                    labels, targets = affected.setdefault(name, (set(), set()))
                    labels.add(label)
                    targets.update(chapters)
    return affected


# --- propagation evidence ---


def trailer_components(root, branch, bases):
    """Components named by a `Propagation-None: <component>: <reason>`
    trailer (non-empty reason) on the task branch's commits."""
    out = branch_log(
        root, branch, bases, f"--format=%(trailers:key={TRAILER_KEY},valueonly,unfold)"
    )
    names = set()
    for line in out.split("\n"):
        m = TRAILER_VALUE_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


def component_repo(root, name):
    path = os.path.join(root, "components", name)
    return path if os.path.exists(os.path.join(path, ".git")) else None


def has_refs_commit(path, task_id):
    """True if any commit on any branch of the repo at `path` carries a
    `Refs: coralstay-software-factory <ID>` line (ID case-insensitive and
    word-bounded: TASK-1 is not TASK-16 or TASK-1.1)."""
    out = git_out(
        path, "log", "--all", "-i", f"--grep={REFS_REPO}", "--format=%B%x00"
    ) or ""
    id_re = re.compile(
        r"(?<![A-Za-z0-9-])" + re.escape(task_id) + r"(?![A-Za-z0-9]|\.\d)",  # ---- 12
        re.IGNORECASE,
    )
    return any(id_re.search(m.group(1)) for m in REFS_RE.finditer(out))


def sort_labels(labels):
    return ", ".join(sorted(labels))


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def deny_missing(task_id, missing):
    lines = []
    for name, (labels, targets), has_repo in missing:
        lines.append(
            f"  - {name} (최상위 장: {sort_labels(labels)} → 컴포넌트 장: {sort_labels(targets)})"
        )
        if not has_repo:
            lines.append(f"      components/{name} 저장소가 없습니다")
    examples = [
        f'     git commit --allow-empty -m "{task_id}: {name} 전파 영향 없음 기록" '
        f'-m "{TRAILER_KEY}: {name}: <사유>"'
        for name, _, _ in missing
    ]
    deny(
        f"{TAG} {task_id}을(를) Done으로 옮기기 전에 이 태스크 브랜치의 최상위 design/ 변경을 "
        "영향받는 컴포넌트 design/에 전파해야 합니다(장 대응표, RAIL-024, decision-15).\n"
        "전파가 확인되지 않은 컴포넌트:\n"
        + "\n".join(lines)
        + "\n통과하는 방법(컴포넌트마다 하나):\n"
        f"  1) 컴포넌트 저장소의 카드로 그 장을 고쳐 커밋하고, 커밋 본문에 "
        f"'Refs: {REFS_REPO} {task_id}' 줄을 넣습니다(components/<이름>의 어느 브랜치든 됩니다).\n"
        f"  2) 영향이 없으면 이 태스크 브랜치에 '{TRAILER_KEY}: <컴포넌트>: <사유>' 트레일러"
        "(커밋 메시지 마지막 문단)를 단 커밋을 더합니다. 히스토리는 고치지 않으므로 새 커밋으로 "
        "남깁니다. 예:\n" + "\n".join(examples)
    )


def check(root, targets, table):
    found = find_task_branch(root, targets)
    if found is None:
        return
    branch, task_id = found
    task_id = task_id.upper()
    bases = base_refs(root)
    if not bases:  # ---- 13
        return
    shas = branch_log(
        root, branch, bases, "--no-merges", "--format=%H", paths=("design/",)
    ).split()
    if not shas:
        return
    affected = affected_components(root, shas, table)
    if not affected:
        return
    exempt = trailer_components(root, branch, bases)
    missing = []
    for name in table["components"]:
        if name not in affected or name in exempt:
            continue
        path = component_repo(root, name)
        if path is not None and has_refs_commit(path, task_id):
            continue
        missing.append((name, affected[name], path is not None))
    if missing:
        deny_missing(task_id, missing)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}
    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") != "Bash" or not isinstance(tool_input, dict):
        sys.exit(0)
    # cheap parse first: most Bash lines leave before any subprocess
    targets = done_targets(tool_input.get("command") or "")  # ---- 14
    if not targets:
        sys.exit(0)
    root = repo_root(data.get("cwd") or "")
    if root is None:
        sys.exit(0)
    doc = os.path.join(root, DOC_PATH)
    if not os.path.isfile(doc):  # ---- 15
        sys.exit(0)
    with open(doc, errors="replace") as f:
        text = f.read()
    try:
        table = parse_table(text)
    except TableError as exc:  # ---- 16
        deny(f"{TAG} {DOC_PATH}의 장 대응표를 읽을 수 없습니다: {exc}")
    if table is None:
        sys.exit(0)
    check(root, targets, table)
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 펜스 코드 블록 안의 ## 는 제목이 아니다
#   설명: 코드 블록 예시에 들어 있는 `## ` 줄을 제목으로 읽으면 변경 줄이 엉뚱한 절에 배치되고 장 대응표 파싱도 깨진다. 그래서 펜스 안은 level 0 일반 줄로 보고한다.
#   개념: fenced code block
# 2 표 헤딩 부재는 통과(None)
#   설명: 컴포넌트 저장소의 자체 00 문서에는 `## 문서 계층 > ### 장 대응표`가 없다. None을 돌려 main이 통과시키게 해서 최상위 저장소에만 이 검사가 적용되게 한다. 헤딩은 있는데 표가 깨진 경우와 구분되는 점이 핵심이다.
#   관련: design/00-문서-정보.md, TASK-63, decision-15
# 3 깨진 표는 TableError로 fail-closed
#   설명: 헤딩은 있는데 표가 없거나 행이 없으면 예외를 낸다. main이 이를 Done 차단으로 바꾼다. 깨진 대응표가 검사를 조용히 꺼 버리면 전파 누락을 영영 못 잡기 때문이다.
#   개념: fail-closed
# 4 최상위 장 표기를 design/ 경로로 번역
#   설명: N.MM 표기는 design/N-*/MM-*.md 로 푼다. 장 대응표를 코드에 하드코딩하지 않고 매 실행마다 문서에서 읽는 것이 TASK-63의 핵심 결정이라, 번역 규칙도 표 위에 적힌 파싱 규칙과 같아야 한다.
#   관련: design/00-문서-정보.md, decision-15
# 5 따옴표 불균형 시 텍스트 매칭으로 대체(fail-closed)
#   설명: 토큰화가 실패하면 명령 위치를 알 수 없다. 이 훅은 게이트이므로 정규식으로 `backlog task edit <ID> -s done` 문구를 찾아 Done 시도로 간주한다. 불필요한 검사는 복구 가능하고 건너뛴 검사는 복구할 수 없다.
#   관련: hooks/require_test_first.py (같은 파서 사본, dedup_drift_guard.REGISTRY가 동일성 보장)
#   개념: fail-closed
# 6 현재 브랜치를 먼저 본다
#   설명: 같은 ID의 task 브랜치가 여럿일 수 있으므로 현재 브랜치를 우선해 사용자가 실제로 작업 중인 범위를 검사한다. 대상 ID는 TASK-16, task-16, 16 어느 표기든 same_task로 맞춘다.
# 7 존재하는 기준 ref만 사용
#   설명: origin/HEAD, main, master, origin/main, origin/master 중 실제로 있는 것만 쓴다. 낡은 로컬 main이든 낡은 원격 main이든 하나만 쓰면 이미 병합된 작업이 범위에 끌려오거나 빠지므로 존재하는 모두를 제외 기준으로 삼는다.
# 8 태스크 브랜치 고유 커밋 범위
#   설명: 어느 기준 ref에서도 도달할 수 없는 커밋만 이 태스크의 커밋으로 센다. paths는 design/ 로 한정해 비설계 커밋을 건너뛴다.
# 9 범위 접두어의 단어 경계
#   설명: §1 이 §10 에, RAIL 이 RAILS 에 걸리면 엉뚱한 행이 영향받는 것으로 계산된다. §n 은 뒤에 숫자가, 영역 접두어는 뒤에 영숫자가 오지 않아야 일치로 본다.
# 10 표에 없는 절의 변경은 장의 모든 행에 해당
#   설명: 장 머리, `## 원천`, 목록에 없는 `## ` 절의 변경은 어느 컴포넌트에 영향 가는지 알 수 없으므로 그 장의 모든 행에 닿은 것으로 본다. 과소 판정으로 전파 누락을 놓치는 쪽보다 과대 판정이 안전하다.
#   개념: 보수적 판정
# 11 경로를 literal pathspec으로 고정
#   설명: design/ 파일명에 *, ? 같은 pathspec 마법 문자가 있어도 해당 파일만 diff하도록 :(literal)을 붙인다. 파일명은 -z로 받아 한글·특수문자가 인용 부호로 깨지는 것도 막는다.
# 12 Refs 줄의 ID는 단어 경계로 일치
#   설명: TASK-1 이 TASK-16 이나 TASK-1.1 로 오인되면 다른 카드의 전파 증거가 이 카드의 증거로 인정된다. 앞뒤 영숫자와 `.숫자`를 제외해 정확히 같은 ID만 인정한다.
# 13 기준 ref가 없으면 통과(fail-open)
#   설명: 범위를 정할 기준이 없으면 어느 커밋이 이 태스크 것인지 알 수 없다. 이 경우만 검사를 포기하고 통과시킨다.
#   개념: fail-open
# 14 값싼 파싱 먼저
#   설명: 모든 Bash 호출에 등록돼 있으므로 대부분의 줄은 서브프로세스 없이 여기서 빠져나가야 한다. git 호출은 Done 시도가 확인된 뒤에만 한다.
#   관련: TASK-39
# 15 00 문서가 없는 저장소는 통과
#   설명: 최상위 design/00-문서-정보.md 가 있는 저장소에서만 적용된다. 다른 저장소의 Done 이동은 이 규칙의 대상이 아니다.
#   개념: fail-open
# 16 표가 깨지면 Done을 거부
#   설명: 읽을 수 없는 대응표의 원인 줄을 메시지에 담아 deny한다. 깨진 대응표가 검사를 끄지 않게 하는 마지막 관문이다.
#   관련: TASK-63, RAIL-024, decision-15
#   개념: fail-closed
