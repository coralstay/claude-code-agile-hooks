#!/usr/bin/env python3
"""PreToolUse (matcher: Edit|Write)
TASK-56: test first, one acceptance criterion at a time (AC-level TDD),
and the tests cover the card's business rules too (RAIL-019).

Applies only when all of these hold, otherwise the hook passes:
- a backlog.md project (`.git` + `backlog/config.yml` in cwd),
- the project opted in through its config (`.claude-code-agile-hooks.json`,
  legacy `.claude-rails.json`) with
  `"testFirst": {"sourceGlobs": [...], "testGlobs": [...]}`,
- the branch is `task/<ID>` and `backlog task view <ID> --plain` shows that
  task In Progress.

Task card: ACs are the `- [ ] #n ...` / `- [x] #n ...` lines. Business rules
live in the Description under a `## 비즈니스 규칙` heading (up to the next
markdown heading), one per line as `- B<k> (AC #<n>) <rule>`; each rule
names the AC it belongs to.

Test markers: a test names what it covers with `<ID>#<n>` (AC) and
`<ID>#B<k>` (rule), e.g. `@DisplayName("AO-27#B2 ...")`. A marker counts
when its exact string appears in any file matched by testGlobs in the
working tree, with no letter/digit/`-` right before it and no digit right
after it (`AO-27#1` is not satisfied by `AO-27#10`).

Edit|Write on a file whose repo-relative path matches a sourceGlob and no
testGlob: find the first unchecked AC n; `<ID>#<n>` and the marker of every
rule tied to AC n must exist, else deny listing the missing markers and
their texts. All ACs checked -> allow (clean-up phase). Tests, docs,
config and files outside the project are never gated.

Glob semantics (repo-relative posix paths, whole path must match): `**`
matches any run of characters including `/` (so `**/` also matches zero
directories), `*` any run without `/`, `?` one character other than `/`;
every other character, `[` included, is literal. testGlobs are searched
from their static prefix (the directories before the first wildcard);
`.git` is skipped.

Known limits: source files written through Bash (`cat > X.java`, `sed -i`)
are not seen; whether the marked test actually fails first (red) is not
checked; only marker strings are matched - a marker in a comment counts the
same as one in a real assertion.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shutil
import subprocess
import sys

TAG = "[claude-code-agile-hooks]"
SECTION_RE = re.compile(r"^([A-Z][A-Za-z ]+):$")
RULE_LINE = "- B<k> (AC #<n>) <규칙>"
RULES_HEADING_RE = re.compile(r"^##\s+비즈니스\s+규칙\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")
AC_RE = re.compile(r"^- \[( |x|X)\] #(\d+) ?(.*)$")
RULE_RE = re.compile(r"^- B(\d+) \(AC #(\d+)\) (\S.*)$")
TASK_LINE_RE = re.compile(r"^Task (\S+) - ")
STATUS_RE = re.compile(r"^Status:.*\bIn Progress\s*$")


def has_command(name):
    return shutil.which(name) is not None


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


def project_config_path(cwd):
    """TASK-54: the project config was renamed from .claude-rails.json to
    .claude-code-agile-hooks.json. Prefer the new name and fall back to the legacy one so
    projects can rename at their own pace; None when neither exists."""
    for name in (".claude-code-agile-hooks.json", ".claude-rails.json"):
        path = os.path.join(cwd, name)
        if os.path.isfile(path):
            return path
    return None


def is_outside_project(path, cwd):
    """True if `path` (relative paths resolve against `cwd`) lands outside the
    project root after realpath on both sides, so `..` and symlinks pointing
    back into the project still count as inside. Empty path -> False."""
    if not path or not cwd:
        return False
    root = os.path.realpath(cwd)
    target = os.path.realpath(os.path.join(cwd, path))
    return os.path.commonpath([root, target]) != root


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_view(cwd, task_id):
    """`backlog task view <ID> --plain` output, or None when it fails."""
    result = subprocess.run(
        ["backlog", "task", "view", task_id, "--plain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def load_test_first(cwd):
    """(sourceGlobs, testGlobs) when the project opted in, else None."""
    path = project_config_path(cwd)
    if path is None:
        return None
    with open(path) as f:
        config = json.load(f)
    block = config.get("testFirst")
    if not block:
        return None
    return list(block.get("sourceGlobs") or []), list(block.get("testGlobs") or [])


# --- globs ---


def glob_regex(pattern):
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z", re.DOTALL)


def glob_matches(pattern, relpath):
    return bool(glob_regex(pattern).match(relpath))


def matches_any(relpath, globs):
    return any(glob_matches(g, relpath) for g in globs)


def glob_base(pattern):
    """The directories before the first wildcard segment."""
    parts = pattern.split("/")[:-1]
    base = []
    for part in parts:
        if "*" in part or "?" in part:
            break
        base.append(part)
    return "/".join(base)


def iter_test_files(cwd, test_globs):
    found = set()
    for pattern in test_globs:
        start = os.path.join(cwd, glob_base(pattern))
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, cwd).replace(os.sep, "/")
                if glob_matches(pattern, rel):
                    found.add(full)
    return sorted(found)


def missing_markers(cwd, test_globs, markers):
    """Markers (in the given order) that no test file contains."""
    patterns = {
        m: re.compile(r"(?<![A-Za-z0-9-])" + re.escape(m) + r"(?!\d)") for m in markers
    }
    remaining = list(markers)
    for path in iter_test_files(cwd, test_globs):
        if not remaining:
            break
        with open(path, errors="ignore") as f:
            text = f.read()
        remaining = [m for m in remaining if not patterns[m].search(text)]
    return remaining


# --- task card ---


def card_sections(text):
    """{section name: body} for the `Name:` + dashes blocks of a plain view."""
    lines = text.split("\n")
    sections = {}
    name = None
    i = 0
    while i < len(lines):
        m = SECTION_RE.match(lines[i])
        if m and i + 1 < len(lines) and re.match(r"^-{10,}$", lines[i + 1]):
            name = m.group(1)
            sections[name] = []
            i += 2
            continue
        if name is not None:
            sections[name].append(lines[i])
        i += 1
    return {k: "\n".join(v).strip("\n") for k, v in sections.items()}


def parse_card(text):
    """dict(id, in_progress, acs=[(n, checked, text)], rules=[(k, n, text)],
    errors=[bad rule lines])."""
    card = {"id": None, "in_progress": False, "acs": [], "rules": [], "errors": []}
    for line in text.split("\n"):
        m = TASK_LINE_RE.match(line)
        if m and card["id"] is None:
            card["id"] = m.group(1)
        if STATUS_RE.match(line):
            card["in_progress"] = True
    sections = card_sections(text)
    for line in sections.get("Acceptance Criteria", "").split("\n"):
        m = AC_RE.match(line.strip())
        if m:
            card["acs"].append((int(m.group(2)), m.group(1) != " ", m.group(3)))
    in_rules = False
    for line in sections.get("Description", "").split("\n"):
        stripped = line.strip()
        if RULES_HEADING_RE.match(stripped):
            in_rules = True
            continue
        if in_rules and HEADING_RE.match(stripped):
            in_rules = False
        if not in_rules or not stripped:
            continue
        m = RULE_RE.match(stripped)
        if m:
            card["rules"].append((int(m.group(1)), int(m.group(2)), m.group(3)))
        else:
            card["errors"].append(stripped)
    return card


def ac_marker(task_id, n):
    return f"{task_id}#{n}"


def rule_marker(task_id, k):
    return f"{task_id}#B{k}"


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def deny_missing(task_id, missing, labels, why):
    lines = [f"  - {m}  {labels[m]}" for m in missing]
    deny(
        f"{TAG} {why} 테스트 표식이 먼저 있어야 합니다(테스트 먼저, AC 단위 TDD).\n"
        "빠진 표식 (testGlobs의 테스트 이름 · 표시 이름 · 주석에 넣으세요):\n"
        + "\n".join(lines)
    )


def check_edit(cwd, path, source_globs, test_globs, card):
    if not path or is_outside_project(path, cwd):
        return
    target = os.path.realpath(os.path.join(cwd, path))
    rel = os.path.relpath(target, os.path.realpath(cwd)).replace(os.sep, "/")
    if not matches_any(rel, source_globs) or matches_any(rel, test_globs):
        return
    task_id = card["id"]
    pending = [ac for ac in card["acs"] if not ac[1]]
    if not pending:
        return
    n, _, ac_text = pending[0]
    labels = {ac_marker(task_id, n): f"(AC #{n}) {ac_text}"}
    for k, rule_ac, rule_text in card["rules"]:
        if rule_ac == n:
            labels[rule_marker(task_id, k)] = f"(B{k}) {rule_text}"
    missing = missing_markers(cwd, test_globs, list(labels))
    if missing:
        deny_missing(task_id, missing, labels, f"소스 {rel}을(를) 고치기 전에 AC #{n}의")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict) or tool_name not in ("Edit", "Write"):
        sys.exit(0)
    path = tool_input.get("file_path") or ""

    if not has_command("backlog") or not is_backlog_project(cwd):
        sys.exit(0)
    globs = load_test_first(cwd)
    if globs is None:
        sys.exit(0)
    source_globs, test_globs = globs

    branch = current_branch(cwd)
    if not branch.startswith("task/"):
        sys.exit(0)
    text = task_view(cwd, branch[len("task/") :])
    if text is None:
        sys.exit(0)
    card = parse_card(text)
    if not card["in_progress"]:
        sys.exit(0)

    check_edit(cwd, path, source_globs, test_globs, card)
    sys.exit(0)


if __name__ == "__main__":
    main()
