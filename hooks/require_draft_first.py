#!/usr/bin/env python3
# ---
# title: require_draft_first
# description: backlog task create를 막고 draft 생성 후 승격하는 흐름으로 안내하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
# ---
"""PreToolUse (matcher: Bash)
TASK-29 (A): in a backlog.md project, new work must enter as a draft
(`backlog draft create`) and only become a task through
`backlog draft promote` after the user has reviewed it. This hook denies
commands that actually *invoke* `backlog task create` and points the agent
at the draft flow instead.

"Actually invoke" means `backlog task create` sits in command position of
some shell segment (after `;`, `&&`, `||`, `|`, `(`, a newline, or at the
start), optionally behind env assignments (`FOO=1`) and simple wrappers
(`env`, `sudo`, `command`, `exec`, `time`, `nohup`, `npx`, `bunx`). Text
inside a quoted argument of another command - e.g.
`backlog draft create -d "... backlog task create ..."` or
`git commit -m "backlog task create 금지"` - is not an invocation and
passes. Heredoc bodies are skipped too. The executable is compared by
basename, so `/opt/homebrew/bin/backlog task create` is still caught
(decision-1).

Known gaps (decision-1: command-string matching stops at basename
normalization): indirection such as `bash -c "backlog task create ..."`,
`eval`, shell variables/aliases, or the backlog MCP server / browser UI
are not seen by this hook. The commit-time scope check
(backlog_commit_scope.py) is the second line of defense for the
draft -> promote history.

There is deliberately no escape hatch: recording already-finished work
after the fact can also go draft create -> promote -> edit.

TASK-75: the project is the one the command targets, not the session cwd -
the cwd moved by earlier `cd <dir>` on the same line, or `BACKLOG_CWD=<dir>`
(in front, behind `env`, or exported earlier), taken at its git top-level.
A target that isn't a backlog project passes; one that can't be known
statically (`cd "$X"`, `BACKLOG_CWD=$Y`) is denied.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

SEPARATOR_CHARS = set(";&|()\n")  # ---- 1
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")  # ---- 2
FALLBACK_RE = re.compile(  # ---- 3
    r"(?:^|[;&|(])\s*(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+create\b", re.MULTILINE
)


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


def segment_runs_task_create(segment):
    i = 0
    while i < len(segment):
        tok = segment[i]
        if tok in ("{", "!") or ASSIGNMENT_RE.match(tok):
            i += 1
            continue
        if tok in WRAPPERS:  # ---- 4
            i += 1
            while i < len(segment) and segment[i].startswith("-"):
                i += 1
            continue
        break
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:  # ---- 5
        return False

    words = [t for t in segment[i + 1 :] if not t.startswith("-")]
    return len(words) >= 2 and words[0] in ("task", "tasks") and words[1] == "create"


def command_invokes_backlog_task_create(command):
    if not command:
        return False
    stripped = strip_heredoc_bodies(command)
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return bool(FALLBACK_RE.search(stripped))
    return any(segment_runs_task_create(s) for s in split_segments(tokens))


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

    if not command_invokes_backlog_task_create(command):  # ---- 6
        sys.exit(0)
    creates = target_roots(  # ---- 7
        command, cwd, lambda s: True if segment_runs_task_create(s) else None, [True]
    )
    if not creates:
        sys.exit(0)

    deny(
        "[claude-code-agile-hooks] 'backlog task create'로 태스크를 바로 만들 수 없습니다. "
        "새 작업은 먼저 'backlog draft create'(+ 'backlog draft edit')로 드래프트에 담고 "
        "커밋한 뒤, 유저가 드래프트를 검토·승인하면 'backlog draft promote <ID>'로 "
        "승격하고 그 승격을 별도 커밋으로 남기세요."
    )


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 명령 위치 판정의 구분자
#   설명: `backlog task create`가 '실제로 실행되는' 것은 셸 구간의 명령 위치(처음, 또는 `;` `&&` `||` `|` `(` 개행 뒤)에 있을 때뿐이다. 다른 명령의 따옴표 인자 안에 글자로 들어 있는 경우(`git commit -m "backlog task create 금지"`)는 호출이 아니라서 통과한다.
#   관련: TASK-29, decision-1
# 2 히어독 본문은 건너뛴다
#   설명: `<<EOF ... EOF` 본문은 명령이 아니라 데이터이므로 검사에서 뺀다. `<<`가 있는 줄 자체는 실제 명령이라 남긴다. `<<<`(here-string)는 lookaround로 제외한다.
# 3 토큰화에 실패하면 정규식으로 대체
#   설명: shlex가 따옴표 불균형 등으로 실패하면 정규식으로 명령 위치의 `backlog task create`를 찾는다. 실패한 입력을 통과시키지 않기 위한 안전망이다.
# 4 감싸는 명령과 환경 변수 대입은 건너뛴다
#   설명: `FOO=1`, `env`, `sudo`, `command`, `exec`, `time`, `nohup`, `npx`, `bunx` 뒤에 오는 실제 실행 파일을 본다. 래퍼의 옵션(`-x`)도 건너뛴다.
# 5 실행 파일은 basename으로 비교
#   설명: `/opt/homebrew/bin/backlog task create`처럼 절대 경로 호출도 잡는다.
#   관련: decision-1 (basename 정규화까지만, `bash -c`·eval·변수·MCP·브라우저 UI 같은 우회는 범위 밖)
# 6 명령 판정이 프로젝트 판정보다 먼저
#   설명: backlog 프로젝트가 아니면 통과한다. 이 훅에는 우회 문(escape hatch)이 없다. 끝난 일을 사후 기록하려면 draft create, promote, edit 순서를 밟는다.
#   관련: hooks/backlog_commit_scope.py (draft→promote 이력의 2차 방어선)
# 7 세션 cwd가 아니라 명령의 대상 프로젝트로 판정
#   설명: 같은 줄의 앞선 cd와 BACKLOG_CWD로 `backlog task create`가 겨누는 디렉터리를 정하고, 그 git top-level이 backlog 프로젝트일 때만 거부한다. 세션 cwd가 프로젝트가 아니어도 `cd <프로젝트> && backlog task create`는 막히고, 대상을 정적으로 알 수 없으면 target_roots가 거부한다.
#   관련: TASK-75 (B3 · B4 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
