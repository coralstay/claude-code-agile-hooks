#!/usr/bin/env python3
# ---
# title: require_work_order
# description: 작업 순서 파일(work-order.md)이 최신이 아니면 승격·착수를 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
# ---
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
MCP server / browser UI. TASK-75: the backlog checked is the one the
command targets - the session cwd moved by an earlier `cd <dir>` on the
line or named by `BACKLOG_CWD=<dir>` - judged at its git top-level; a
target that can't be known statically (`cd "$X"`) is denied.

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
HASH_RE = re.compile(r"^<!-- work-order-hash: ([0-9a-f]{64}) -->$", re.MULTILINE)  # ---- 1
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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 2
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return bool(  # ---- 3
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
    return [int(p) if p.isdigit() else p for p in NATURAL_RE.split(task_id)]  # ---- 4


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
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()  # ---- 5


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
    if not os.path.isfile(sibling) and os.path.isfile(repo_copy):  # ---- 6
        return repo_copy
    return sibling


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


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)  # ---- 7


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:  # ---- 8
        data = {}

    cwd = data.get("cwd", "")
    command = (data.get("tool_input") or {}).get("command", "")

    if not command_starts_stage(command):  # ---- 9
        sys.exit(0)
    stages = target_roots(  # ---- 10
        command, cwd, lambda s: True if segment_starts_stage(s) else None, [True]
    )
    for root, _ in stages:
        check_repo(root)
    sys.exit(0)


def check_repo(root):
    incomplete = incomplete_tasks(read_tasks(root))
    recorded = recorded_hash(root)
    if recorded is None and not incomplete:  # ---- 11
        return
    if recorded == input_hash(incomplete):  # ---- 12
        return

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


# ======== 노트 ========
# 1 해시 헤더 정규식
#   설명: work-order.md 첫 줄의 `<!-- work-order-hash: <sha256> -->`만 신선도 판정 근거로 읽는다. 타임스탬프가 아니라 해시라서 제목·상태(Done 제외) 편집으로는 파일이 낡지 않는다.
#   관련: scripts/work_order.py, TASK-60
#   개념: 신선도 해시
# 2 heredoc 본문 제거 후 토큰화
#   설명: heredoc 본문 안에 적힌 `backlog draft promote` 같은 글자를 실제 명령으로 오인하지 않도록 본문을 먼저 버리고, 줄 끝 `\` 이음도 합친 다음 쪼갠다.
#   관련: hooks/require_draft_first.py (같은 규칙)
#   개념: 명령 위치 판정
# 3 토큰화 실패 시 텍스트 매칭 대체
#   설명: 따옴표가 안 닫히는 등 shlex가 실패하면 정규식으로 대신 판정한다. 이 훅은 관문이라 판정 불가일 때 통과시키지 않고 보수적으로(막는 쪽으로) 본다.
#   개념: fail-closed
# 4 자연 정렬 키
#   설명: TASK-2가 TASK-10보다 앞에 오도록 숫자 조각을 int로 비교한다. 생성기와 해시 입력 순서가 한 글자라도 다르면 항상 낡은 것으로 판정되므로 scripts/work_order.py와 글자 그대로 같아야 한다.
#   관련: scripts/work_order.py, dedup_drift_guard.REGISTRY
#   개념: 드리프트 가드
# 5 입력 해시 계산
#   설명: 미완료 태스크 ID와 각 의존만 해시 입력으로 쓴다. Done 의존이나 없는 태스크 의존은 생성기와 같은 규칙으로 처리되어 해시에 영향이 없다.
#   관련: scripts/work_order.py
#   개념: 멱등
# 6 설치본 우선, 저장소 사본 대체
#   설명: install.sh가 훅 옆에 work_order.py를 복사하므로 형제 파일을 먼저 쓰고, 저장소 안에서 돌릴 때만 scripts/work_order.py를 안내 메시지에 쓴다.
#   관련: install.sh
# 7 exit 2로 거부
#   설명: stderr 메시지와 함께 exit 2로 끝내면 Claude Code가 도구 호출을 막고 메시지를 모델에 되돌려 준다.
#   개념: 훅 종료 코드
# 8 JSON 파싱 실패는 통과
#   설명: stdin이 깨져도 빈 데이터로 두고 아래 명령 판정에서 걸러져 exit 0이 된다. 입력 형식 오류로 사용자 작업을 막지 않는다.
#   개념: fail-open
# 9 관문 대상 명령만 검사
#   설명: promote 또는 In Progress 전환이 아닌 모든 Bash 명령은 즉시 통과한다. 이 훅의 유일한 진입 조건이다.
#   개념: 관문
# 10 세션 cwd가 아니라 명령의 대상 프로젝트로 판정
#   설명: 같은 줄의 앞선 cd와 BACKLOG_CWD로 단계 명령이 겨누는 디렉터리를 정하고, 그 git top-level의 태스크 · work-order.md로 판정한다. 세션 저장소의 작업 순서를 보고 `cd <B> && backlog task edit ...`를 막던 문제(2026-11-17)를 없애고, 대상을 정적으로 알 수 없으면 target_roots가 거부한다.
#   관련: TASK-75 (B3 · B4 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
# 11 새 프로젝트는 통과
#   설명: 파일도 미완료 태스크도 없으면 정렬할 것이 없으므로 통과한다. 파일 없이 미완료 태스크만 있으면 아래로 내려가 거부되어 최초 1회 생성을 강제한다.
#   개념: 교착 방지
# 12 해시 일치면 통과
#   설명: 승격 자체는 승격 이전 상태로 판정하므로 파일이 최신이면 통과한다. 승격이 만든 태스크 때문에 낡아지면 다음 승격·착수가 생성기 실행을 기다리고, 생성기는 막히지 않아 교착이 없다.
#   관련: TASK-60, hooks/backlog_commit_scope.py
#   개념: 교착 방지
