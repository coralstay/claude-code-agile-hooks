#!/usr/bin/env python3
# ---
# title: require_stage_committed
# description: 카드 생애주기의 이전 단계가 커밋되기 전에는 다음 단계 명령을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
# ---
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

TASK-75: backlog/ is checked in the project the command targets, not the
session cwd - the cwd moved by earlier `cd <dir>` on the same line, or
`BACKLOG_CWD=<dir>`, taken at its git top-level. A target that isn't a
backlog project passes; one that can't be known statically is denied.

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
STAGE_STATUSES = {"in progress", "done"}  # ---- 1
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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 2
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return bool(FALLBACK_RE.search(stripped))  # ---- 3
    return any(segment_runs_stage(s) for s in split_segments(tokens))


# --- working tree -----------------------------------------------------------


def uncommitted_backlog_paths(cwd):
    """Paths under backlog/ that differ from HEAD (staged, unstaged or
    untracked), or None when git status fails."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all", "--", "backlog/"],  # ---- 4
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # ---- 5
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
        if entry[0] in ("R", "C") and i < len(fields):  # ---- 6
            paths.append(fields[i])  # -z puts the rename source next
            i += 1
    return paths


def format_paths(paths):
    listed = "\n".join(f"  - {p}" for p in paths[:MAX_LISTED])
    if len(paths) > MAX_LISTED:
        listed += f"\n  ... 외 {len(paths) - MAX_LISTED}개"
    return listed


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
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    command = (data.get("tool_input") or {}).get("command", "")

    if not command_runs_stage(command):  # ---- 7
        sys.exit(0)
    if not has_command("git"):
        sys.exit(0)
    stages = target_roots(  # ---- 8
        command, cwd, lambda s: True if segment_runs_stage(s) else None, [True]
    )
    for root, _ in stages:
        check_repo(root)
    sys.exit(0)


def check_repo(root):
    paths = uncommitted_backlog_paths(root)
    if not paths:  # ---- 9
        return

    deny(  # ---- 10
        "[claude-code-agile-hooks] 다음 단계(draft create · draft promote · "
        '-s "In Progress" · -s Done)로 넘어가기 전에 이전 단계를 먼저 커밋하세요 — '
        "커밋되지 않은 backlog/ 변경이 있습니다:\n"
        + format_paths(paths)
        + "\n단계마다 커밋한다: draft 1장 → 커밋 → 승격 → 커밋 → In Progress → 커밋 → "
        "작업 → Done → 커밋."
    )


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 관문 대상 상태는 In Progress와 Done
#   설명: draft create, draft promote와 함께 이 두 전환이 카드 생애 단계다. 다른 상태 편집은 단계가 아니므로 막지 않는다.
#   관련: TASK-59
# 2 heredoc 본문과 줄 이음을 먼저 정리
#   설명: heredoc 본문 속 글자나 `\` 줄 이음 뒤에 붙은 단어를 다른 명령으로 오인하지 않게 bash와 같은 순서로 전처리한 뒤 쪼갠다.
#   관련: hooks/require_draft_first.py (같은 규칙)
#   개념: 명령 위치 판정
# 3 토큰화 실패 시 텍스트 매칭
#   설명: 따옴표가 안 닫혀 구문 분석이 안 되면 정규식으로 대신 판정한다. 관문이라 오탐은 커밋 한 번 비용이고 미탐은 이력 손실이라 막는 쪽으로 기운다.
#   개념: fail-closed
# 4 backlog/ 만 검사
#   설명: git status를 backlog/ 경로로 한정해 다른 곳의 작업 중 변경이 단계 전환을 막지 않게 한다. 미추적(all)·이름 변경까지 -z로 정확히 받는다.
#   개념: 범위 한정
# 5 git status 실패는 None
#   설명: 상태를 알 수 없으면 None을 돌려 호출부에서 통과로 처리한다. git 오류로 사용자 작업을 막지 않는다.
#   개념: fail-open
# 6 이름 변경은 원본 경로가 다음 필드
#   설명: -z 출력에서 R/C 항목은 원본 경로가 별도 필드로 따라온다. 소비하지 않으면 다음 항목 파싱이 한 칸씩 어긋난다.
#   관련: git status --porcelain -z
# 7 단계 명령이 아니면 즉시 통과
#   설명: 대부분의 Bash 호출은 여기서 끝난다. git 서브프로세스는 단계 명령일 때만 띄운다.
#   개념: 관문
# 8 세션 cwd가 아니라 명령의 대상 프로젝트로 판정
#   설명: 같은 줄의 앞선 cd와 BACKLOG_CWD로 단계 명령이 겨누는 디렉터리를 정하고, 그 git top-level의 backlog/ 변경으로 판정한다. 대상이 backlog 프로젝트가 아니면 세션 cwd와 무관하게 통과하고, 대상을 정적으로 알 수 없으면 target_roots가 거부한다.
#   관련: TASK-75 (B3 · B4 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
# 9 깨끗하거나 알 수 없으면 통과
#   설명: paths가 비었거나 None이면 거부 사유가 없다. 단계 명령 자신이 만드는 변경은 이 검사 이후에 일어나므로 깨끗한 트리에서 한 명령으로 Done까지 가는 것은 허용된다.
#   개념: 교착 방지
# 10 exit 2로 이전 단계 커밋 요구
#   설명: 커밋되지 않은 backlog/ 변경 목록과 함께 거부한다. 단계마다 커밋해야 backlog_commit_scope.py가 커밋 단위를 검증할 수 있다.
#   관련: hooks/backlog_commit_scope.py, TASK-59#3
