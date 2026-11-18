#!/usr/bin/env python3
# ---
# title: pre_commit_check
# description: 커밋이 task/<ID> 브랜치에서만 되게 하고 설정된 테스트가 통과해야 커밋을 허용하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
Phase 3-1 + 3-4: commits must happen on a task/<ID> branch, and (if the
project opted in via .claude-code-agile-hooks.json, or the legacy .claude-rails.json)
tests must pass first.

TASK-39: registered without `if: Bash(git *)` - that filter matches the
command text, so `/usr/bin/git commit` or `FOO=1 git commit` never reached
this gate (same finding as TASK-37). The cost is one short python process
per Bash call; every non-commit line exits right after parsing.

Only a `git commit` in *command position* counts, found the way
pre_push_check.py (TASK-34) finds a push: heredoc bodies dropped,
backslash-newline continuations joined, the line tokenized and split into
shell segments (`;`, `&&`, `||`, `|`, `&`, `(`, newline), env assignments
and simple wrappers (`env`, `sudo`, ...) skipped (`command_head`), git
compared by basename (decision-1) and its global flags (`-C <path>`,
`-c k=v`, `--git-dir=...`) skipped. `echo git commit`, quoted text
(`--notes "... git commit ..."`) and heredoc bodies are not a commit.

Parse failure (unbalanced quote): command position can't be told apart
from text, so any `commit` substring counts as a commit - this is a gate,
and an unneeded branch/test check is recoverable while a skipped one is not.

Known gaps (decision-1): `bash -c "git commit"`, `eval`, aliases, scripts,
backtick substitution, and runners such as `xargs git commit` are not seen.

TASK-75: the commit is judged on the repository it targets, not the session
cwd - the cwd moved by earlier `cd <dir>` on the same line and the commit's
own `git -C <dir>`, taken at its git top-level (so a subdirectory or linked
worktree counts): that repository's active task, branch and testCommand. A
target that isn't a backlog project passes; one that can't be known
statically (`cd "$X"`, `git -C "$D"`, `cd -`, a missing directory) is denied
with the reason.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")


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
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")  # ---- 1
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
    if i >= len(segment) or os.path.basename(segment[i]) != "git":  # ---- 2
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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 3
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return subcommand in stripped  # ---- 4
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


def has_active_task(cwd):
    result = subprocess.run(
        ["backlog", "task", "list", "--status", "In Progress", "--plain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return "No tasks found." not in (result.stdout or "")


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def project_config_path(cwd):
    """TASK-54: the project config was renamed from .claude-rails.json to
    .claude-code-agile-hooks.json. Prefer the new name and fall back to the legacy one so
    projects can rename at their own pace; None when neither exists."""
    for name in (".claude-code-agile-hooks.json", ".claude-rails.json"):  # ---- 5
        path = os.path.join(cwd, name)
        if os.path.isfile(path):
            return path
    return None


def configured_test_command(cwd):
    config_path = project_config_path(cwd)
    if config_path is None:
        return None
    with open(config_path) as f:
        config = json.load(f)
    return config.get("testCommand") or None


def run_shell(cwd, command):
    result = subprocess.run(
        command, cwd=cwd, shell=True, capture_output=True, text=True
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


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

    if not command_runs_git(command, "commit"):  # ---- 6
        sys.exit(0)
    if not has_command("backlog"):  # ---- 7
        sys.exit(0)

    for root, _ in target_roots(command, cwd, segment_commits, [True]):  # ---- 8
        check_repo(root)
    sys.exit(0)


def check_repo(root):
    if has_active_task(root):  # ---- 9
        branch = current_branch(root)
        if not branch.startswith("task/"):  # ---- 10
            deny(
                f"[claude-code-agile-hooks] 커밋하기 전에 태스크 브랜치(task/TASK-ID)로 전환하세요. 현재 브랜치: {branch}"
            )

    test_command = configured_test_command(root)
    if test_command:
        exit_code, output = run_shell(root, test_command)
        if exit_code != 0:  # ---- 11
            deny(
                f"[claude-code-agile-hooks] 커밋 전 테스트 실패 ('{test_command}', exit {exit_code}):\n"
                + output[-800:]
            )


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 shlex 토크나이저 설정
#   설명: punctuation_chars로 ; && | ( ) 를 독립 토큰으로 쪼개 세그먼트 분리가 가능하게 한다. commenters를 비워 두는 것도 의도다: 쉘 주석 처리를 하면 따옴표 안의 # 이후가 잘려 나가 커밋 명령을 놓친다.
#   관련: hooks/dedup_drift_guard.py (REGISTRY로 다른 훅의 사본과 동일성 검사)
#   개념: shlex, 쉘 세그먼트
# 2 git 실행 파일 이름 비교
#   설명: 경로가 아니라 basename으로 git을 비교해 /usr/bin/git commit 같은 절대경로 호출도 잡는다(TASK-39 발견 사항, decision-1). 명령 위치(command position)에 있는 git만 인정하므로 echo git commit은 커밋이 아니다.
#   관련: TASK-39, TASK-37, decision-1
# 3 히어독 본문 제거와 줄 잇기 결합
#   설명: bash는 단어를 나누기 전에 백슬래시-개행을 이어 붙인다. 같은 순서로 전처리하지 않으면 줄 이은 git commit이 토큰으로 갈라져 게이트를 우회한다. 히어독 본문은 명령이 아니라 텍스트이므로 먼저 버린다.
#   관련: TASK-34 (pre_push_check.py의 같은 방식)
#   개념: 히어독, 라인 컨티뉴에이션
# 4 파싱 실패 시 fail-closed
#   설명: 따옴표가 닫히지 않아 토큰화에 실패하면 명령 위치와 텍스트를 구분할 수 없다. 이 훅은 게이트이므로 부분 문자열만 있어도 커밋으로 간주한다. 불필요한 브랜치/테스트 검사는 복구 가능하지만 건너뛴 검사는 복구할 수 없기 때문이다.
#   개념: fail-closed
# 5 설정 파일 이름 폴백
#   설명: TASK-54에서 .claude-rails.json이 .claude-code-agile-hooks.json으로 바뀌었다. 새 이름을 먼저 보고 옛 이름으로 폴백해 프로젝트가 각자 속도로 이름을 바꿀 수 있게 한다.
#   관련: TASK-54
# 6 비커밋 명령은 즉시 통과
#   설명: 이 훅은 if 필터 없이 모든 Bash 호출에 등록돼 있어서(TASK-39) 커밋이 아닌 줄은 파싱 직후 바로 exit 0 해야 파이썬 프로세스 비용이 한 번의 짧은 파싱으로 끝난다.
#   관련: TASK-39
# 7 backlog 부재 시 fail-open
#   설명: backlog CLI가 없거나 커밋 대상이 backlog 프로젝트가 아니면 이 워크플로 대상이 아니므로 통과시킨다. 워크플로 밖의 저장소 커밋을 막으면 안 된다.
#   개념: fail-open
# 8 세션 cwd가 아니라 커밋 대상 저장소로 판정
#   설명: 같은 줄의 앞선 cd와 git -C로 커밋이 겨누는 디렉터리를 정하고 그 git top-level의 브랜치 · 카드 · testCommand로 판정한다. 대상이 backlog 프로젝트가 아니면 세션 cwd가 프로젝트여도 통과하고, 대상을 정적으로 알 수 없으면(cd "$X" 등) target_roots가 거부한다. 여러 저장소를 겨누면 저장소마다 검사한다.
#   관련: TASK-75 (B2 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
# 9 In Progress 태스크가 있을 때만 브랜치 강제
#   설명: 진행 중 태스크가 없으면 브랜치 규칙을 적용하지 않는다. 태스크 없이 하는 작업까지 task/ 브랜치로 몰지 않기 위함이다.
#   관련: hooks/require_active_task.py
# 10 task/ 브랜치 접두사 검사
#   설명: Phase 3-1 규칙: 커밋은 task/<ID> 브랜치에서만 한다. ID 형식까지 검사하지 않고 접두사만 보는 것은 의도다.
# 11 테스트 실패 시 커밋 차단
#   설명: Phase 3-4: 프로젝트가 testCommand로 옵트인했을 때만 실행하고, 실패하면 exit 2로 커밋을 막는다. 출력은 뒤 800자만 보여 줘 에러 메시지가 길어지지 않게 한다.
#   관련: .claude-code-agile-hooks.json (testCommand)
