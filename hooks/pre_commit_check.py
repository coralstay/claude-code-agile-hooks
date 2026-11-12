#!/usr/bin/env python3
# ---
# title: pre_commit_check
# description: 커밋이 task/<ID> 브랜치에서만 되게 하고 설정된 테스트가 통과해야 커밋을 허용하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
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


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


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
    if not is_backlog_project(cwd):
        sys.exit(0)

    if has_active_task(cwd):  # ---- 8
        branch = current_branch(cwd)
        if not branch.startswith("task/"):  # ---- 9
            deny(
                f"[claude-code-agile-hooks] 커밋하기 전에 태스크 브랜치(task/TASK-ID)로 전환하세요. 현재 브랜치: {branch}"
            )

    test_command = configured_test_command(cwd)
    if test_command:
        exit_code, output = run_shell(cwd, test_command)
        if exit_code != 0:  # ---- 10
            deny(
                f"[claude-code-agile-hooks] 커밋 전 테스트 실패 ('{test_command}', exit {exit_code}):\n"
                + output[-800:]
            )

    sys.exit(0)


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
#   설명: backlog CLI가 없거나 backlog 프로젝트가 아니면 이 워크플로 대상이 아니므로 통과시킨다. 워크플로 밖의 저장소 커밋을 막으면 안 된다.
#   개념: fail-open
# 8 In Progress 태스크가 있을 때만 브랜치 강제
#   설명: 진행 중 태스크가 없으면 브랜치 규칙을 적용하지 않는다. 태스크 없이 하는 작업까지 task/ 브랜치로 몰지 않기 위함이다.
#   관련: hooks/require_active_task.py
# 9 task/ 브랜치 접두사 검사
#   설명: Phase 3-1 규칙: 커밋은 task/<ID> 브랜치에서만 한다. ID 형식까지 검사하지 않고 접두사만 보는 것은 의도다.
# 10 테스트 실패 시 커밋 차단
#   설명: Phase 3-4: 프로젝트가 testCommand로 옵트인했을 때만 실행하고, 실패하면 exit 2로 커밋을 막는다. 출력은 뒤 800자만 보여 줘 에러 메시지가 길어지지 않게 한다.
#   관련: .claude-code-agile-hooks.json (testCommand)
