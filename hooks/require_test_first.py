#!/usr/bin/env python3
# ---
# title: require_test_first
# description: AC 단위로 테스트를 먼저 쓰도록 소스 편집과 Done 전환을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Edit|Write, and Bash with no `if` filter)
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

Test markers: a test names what it covers with `<ID>#<n>` (AC),
`<ID>#B<k>` (rule) and `<ID>#D<n>` (Definition of Done item, TASK-61),
e.g. `@DisplayName("AO-27#B2 ...")`. A marker counts
when its exact string appears in any file matched by testGlobs in the
working tree, with no letter/digit/`-` right before it and no digit right
after it (`AO-27#1` is not satisfied by `AO-27#10`).

Edit|Write on a file whose repo-relative path matches a sourceGlob and no
testGlob: find the first unchecked AC n; `<ID>#<n>` and the marker of every
rule tied to AC n must exist, else deny listing the missing markers and
their texts. All ACs checked -> allow (clean-up phase). Tests, docs,
config and files outside the project are never gated.

Bash `backlog task edit <ID> ... -s Done` (`--status Done`,
`--status=Done`, any case) for the branch's task (`AO-27`, `ao-27`, `27`):
every AC marker, every rule marker and (TASK-61) a `<ID>#D<n>` marker for
every Definition of Done item (`- [ ] #n` / `- [x] #n`, checked or not)
must exist, else deny listing the missing ones - no rule ends untested.
DoD items belong to no AC, so the Edit|Write check never asks for them. The command is parsed in command
position like pre_commit_check.py (heredoc bodies dropped, continuations
joined, segments split, env assignments and wrappers skipped, `backlog`
compared by basename), so `echo ... -s Done` or a commit message quoting it
is not a Done move. Unbalanced quotes: a text match stands in (gate).
Indirection (`bash -c`, `eval`, scripts) and the backlog MCP server / web UI
are not seen.

Both checks deny first when the card has a `## 비즈니스 규칙` heading with a
line under it that isn't `- B<k> (AC #<n>) <rule>` or names an AC the card
lacks (the message shows the expected format). No heading -> only AC
markers are required. A card with no ACs and no DoD items requires nothing. A malformed
`testFirst` block (or unreadable config) denies on the task branch - the
project asked for the gate - except edits of the config file itself.

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
import shlex
import shutil
import subprocess
import sys

TAG = "[claude-code-agile-hooks]"
CONFIG_NAMES = (".claude-code-agile-hooks.json", ".claude-rails.json")
SECTION_RE = re.compile(r"^([A-Z][A-Za-z ]+):$")
RULE_LINE = "- B<k> (AC #<n>) <규칙>"
RULES_HEADING_RE = re.compile(r"^##\s+비즈니스\s+규칙\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")
AC_RE = re.compile(r"^- \[( |x|X)\] #(\d+) ?(.*)$")
RULE_RE = re.compile(r"^- B(\d+) \(AC #(\d+)\) (\S.*)$")
TASK_LINE_RE = re.compile(r"^Task (\S+) - ")
STATUS_RE = re.compile(r"^Status:.*\bIn Progress\s*$")
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
DONE_FALLBACK_RE = re.compile(  # ---- 1
    r"(?:^|[;&|(\s])(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+edit\s+(\S+)"
    r".*?(?:^|\s)(?:-s|--status)(?:=|\s+)['\"]?done\b",
    re.IGNORECASE | re.DOTALL,
)


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
    return os.path.commonpath([root, target]) != root  # ---- 2


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


class ConfigError(Exception):
    pass


def is_glob_list(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(g, str) and g for g in value)
    )


def load_test_first(cwd):
    """(sourceGlobs, testGlobs) when the project opted in, else None.
    ConfigError when the config can't be read or the opt-in block is
    malformed - the project asked for the gate, so it must not silently
    turn off."""
    path = project_config_path(cwd)
    if path is None:
        return None
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{os.path.basename(path)}을(를) 읽을 수 없습니다: {exc}")  # ---- 3
    block = config.get("testFirst") if isinstance(config, dict) else None
    if block is None:
        return None
    if not isinstance(block, dict) or not (
        is_glob_list(block.get("sourceGlobs")) and is_glob_list(block.get("testGlobs"))
    ):
        raise ConfigError(
            'testFirst는 {"sourceGlobs": ["..."], "testGlobs": ["..."]} 형식이어야 '
            "합니다(둘 다 비어 있지 않은 문자열 목록)."
        )
    return block["sourceGlobs"], block["testGlobs"]


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
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")  # ---- 4
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def split_segments(tokens):
    segments = [[]]
    for tok in tokens:
        if tok and set(tok) <= SEPARATOR_CHARS:  # ---- 5
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
        return [m.group(1) for m in DONE_FALLBACK_RE.finditer(stripped)]  # ---- 6
    targets = [segment_done_target(s) for s in split_segments(tokens)]
    return [t for t in targets if t is not None]


def same_task(token, task_id):
    """`AO-27`, `ao-27` and `27` all name task AO-27."""
    if token.upper() == task_id.upper():
        return True
    return token.isdigit() and task_id.rsplit("-", 1)[-1] == token


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
        m: re.compile(r"(?<![A-Za-z0-9-])" + re.escape(m) + r"(?!\d)") for m in markers  # ---- 7
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
        if m and i + 1 < len(lines) and re.match(r"^-{10,}$", lines[i + 1]):  # ---- 8
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
    dod=[(n, checked, text)], errors=[bad rule lines])."""
    card = {
        "id": None,
        "in_progress": False,
        "acs": [],
        "rules": [],
        "dod": [],
        "errors": [],
    }
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
    # TASK-61: Definition of Done items use the same checkbox lines as ACs
    for line in sections.get("Definition of Done", "").split("\n"):  # ---- 9
        m = AC_RE.match(line.strip())
        if m:
            card["dod"].append((int(m.group(2)), m.group(1) != " ", m.group(3)))
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


def dod_marker(task_id, n):
    return f"{task_id}#D{n}"


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def rule_errors(card):
    """Bad lines under `## 비즈니스 규칙`, plus rules naming an AC the card
    doesn't have."""
    errors = list(card["errors"])
    numbers = {n for n, _, _ in card["acs"]}
    for k, n, text in card["rules"]:
        if n not in numbers:
            errors.append(f"- B{k} (AC #{n}) {text}  <- 카드에 AC #{n}이 없습니다")
    return errors


def deny_if_rules_malformed(card):
    errors = rule_errors(card)
    if errors:
        deny(
            f"{TAG} 태스크 카드의 '## 비즈니스 규칙' 절 형식이 틀렸습니다. "
            f"한 줄에 규칙 하나, '{RULE_LINE}' 형식으로 적으세요 "
            "(예: '- B1 (AC #1) 예상 토큰이 음수면 거부한다').\n"
            "틀린 줄:\n" + "\n".join(f"  {e}" for e in errors)
        )


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
    if not matches_any(rel, source_globs) or matches_any(rel, test_globs):  # ---- 10
        return
    deny_if_rules_malformed(card)
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


def check_done(cwd, test_globs, card):
    deny_if_rules_malformed(card)
    task_id = card["id"]
    labels = {}
    for n, _, ac_text in card["acs"]:
        labels[ac_marker(task_id, n)] = f"(AC #{n}) {ac_text}"
    for k, rule_ac, rule_text in card["rules"]:
        labels[rule_marker(task_id, k)] = f"(B{k}, AC #{rule_ac}) {rule_text}"
    for n, _, dod_text in card["dod"]:
        labels[dod_marker(task_id, n)] = f"(DoD #{n}) {dod_text}"
    missing = missing_markers(cwd, test_globs, list(labels))
    if missing:
        deny_missing(
            task_id,
            missing,
            labels,
            f"{task_id}을(를) Done으로 옮기기 전에 모든 AC · 비즈니스 규칙 · DoD의",
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)
    path = ""
    targets = []
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path") or ""
    elif tool_name == "Bash":
        # cheap parse first: most Bash lines leave before any subprocess
        targets = done_targets(tool_input.get("command") or "")  # ---- 11
        if not targets:
            sys.exit(0)
    else:
        sys.exit(0)

    if not has_command("backlog") or not is_backlog_project(cwd):
        sys.exit(0)
    config_error = None
    try:
        globs = load_test_first(cwd)
    except ConfigError as exc:
        config_error = str(exc)
        globs = ([], [])
    if globs is None:
        sys.exit(0)
    source_globs, test_globs = globs

    branch = current_branch(cwd)
    if not branch.startswith("task/"):
        sys.exit(0)
    branch_task = branch[len("task/") :]
    text = task_view(cwd, branch_task)
    if text is None:  # ---- 12
        sys.exit(0)
    card = parse_card(text)
    card["id"] = card["id"] or branch_task
    if not card["in_progress"]:
        sys.exit(0)

    if config_error is not None:
        # the opted-in project's config is broken: block, but keep the
        # config itself editable so it can be fixed
        if os.path.basename(path) in CONFIG_NAMES:  # ---- 13
            sys.exit(0)
        deny(f"{TAG} testFirst 설정 오류: {config_error}")

    if tool_name == "Bash":
        if any(same_task(t, card["id"]) for t in targets):
            check_done(cwd, test_globs, card)
    else:
        check_edit(cwd, path, source_globs, test_globs, card)
    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 Done 이동 텍스트 폴백 정규식
#   설명: 따옴표가 안 닫혀 shlex가 못 쪼개는 줄에서도 `backlog task edit <ID> -s Done`을 놓치지 않으려는 마지막 그물이다. 훅이 게이트이므로 파싱 실패를 통과로 두지 않고 문자열 매칭으로 대신 막는다.
#   관련: hooks/require_coverage_on_done.py (같은 정규식 복사본)
#   개념: fail-closed 폴백
# 2 프로젝트 밖 경로 판정
#   설명: realpath를 양쪽에 적용한 뒤 commonpath를 비교한다. `..`나 프로젝트 안을 가리키는 심볼릭 링크로 소스 게이트를 우회하거나, 반대로 밖의 파일을 안으로 오판하는 것을 막는다.
#   관련: hooks/dedup_drift_guard.py REGISTRY(is_outside_project 사본 4개)
#   개념: realpath, 경로 탈출
# 3 설정 오류는 fail-closed
#   설명: testFirst를 켠 프로젝트의 설정이 깨졌다고 조용히 게이트를 끄면 TDD 강제가 사라진다. 그래서 예외를 올려 task 브랜치에서 deny로 이어지게 한다(설정 파일 자체의 편집만 예외).
#   개념: fail-closed
# 4 셸 명령 토큰화
#   설명: punctuation_chars로 `;&|()<>`를 별도 토큰으로 떼어 낸다. 이 토크나이저 설정이 명령 위치 판정의 기반이라 사본들과 바이트 단위로 같아야 한다.
#   관련: hooks/dedup_drift_guard.py REGISTRY(tokenize)
#   개념: 토크나이저, 사본 동기화
# 5 세그먼트 분리 판정
#   설명: 토큰이 전부 구분자 문자로만 이뤄졌을 때만 새 세그먼트를 연다. `echo ... -s Done`처럼 다른 명령의 인자는 backlog 명령 위치로 보지 않기 위한 전제다.
#   개념: 명령 위치
# 6 따옴표 불균형이면 텍스트 매칭
#   설명: shlex가 ValueError를 내는 줄은 구조를 알 수 없으므로 정규식으로 Done 이동을 추정해 게이트를 건다. 놓치는 것(우회)보다 잘못 막는 쪽이 낫다는 보수적 결정이다.
#   개념: fail-closed 폴백
# 7 표식 정확 일치 규칙
#   설명: 표식 앞에 영문/숫자/`-`가 없고 뒤에 숫자가 없어야 센다. `AO-27#1`이 `AO-27#10`이나 `XAO-27#1`로 잘못 충족되는 것을 막는 핵심 불변식이다.
#   개념: 경계 일치(lookaround)
# 8 카드 절 헤더 인식
#   설명: `Name:` 다음 줄이 대시 10개 이상일 때만 절 제목으로 본다. 설명 본문에 우연히 `Foo:` 줄이 있어도 절이 갈라지지 않게 한다.
#   관련: backlog task view --plain 출력 형식
# 9 DoD 항목 파싱
#   설명: DoD는 AC와 같은 체크박스 줄이라 같은 정규식을 쓴다. DoD는 어느 AC에도 묶이지 않으므로 Edit 게이트는 보지 않고 Done 이동 때만 `<ID>#D<n>`을 요구한다.
#   관련: TASK-61
# 10 게이트 대상 파일 판정
#   설명: sourceGlob에 맞고 testGlob에는 안 맞는 파일만 막는다. 테스트 · 문서 · 설정은 절대 막지 않아 테스트를 먼저 쓰는 길이 열려 있어야 한다는 불변식이다.
#   개념: glob 게이트
# 11 Bash는 싼 파싱으로 먼저 거름
#   설명: 대부분의 Bash 호출은 Done 이동이 아니므로 서브프로세스(backlog, git)를 띄우기 전에 문자열 파싱만으로 종료한다. 모든 Bash 호출에 붙는 훅이라 지연 비용을 최소화하는 결정이다.
# 12 카드를 못 읽으면 fail-open
#   설명: `backlog task view`가 실패하면 판정 근거가 없으므로 통과시킨다. 반면 testFirst 설정이 깨진 경우는 의도적으로 막는다는 점과 대비된다.
#   개념: fail-open
# 13 깨진 설정 파일은 고칠 수 있게 허용
#   설명: 설정이 깨져 모든 편집이 deny되는데 설정 파일 자체까지 막으면 복구할 방법이 없다. 설정 파일 편집만 예외로 열어 둔다.
#   개념: 자기 잠금 방지
