#!/usr/bin/env python3
# ---
# title: pre_push_check
# description: 태스크가 Done이고 최종 요약이 있을 때만 task 브랜치 push를 허용하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
Phase 4.3: only push a task/<ID> branch once that task is Done and carries
a final summary.

TASK-46: registered without `if: Bash(git *)`. Measured 2026-10-04 in
Claude Code: the filter matches each subcommand of a compound line by text
prefix, so `true && git push ...` ran this hook but `/usr/bin/git push ...`
skipped it and executed - a gate that a path-qualified call bypasses. The
cost is one short python process per Bash call; a line without a push
exits right after parsing, before any subprocess.
hooks/test_hook_registration_contract.py keeps the registration and this
detection in agreement.

This script does its own subcommand detection so `git -C <path> push`
(flags before the subcommand) is still recognized as a push, not just
`git push`.

TASK-34: only a `git push` in *command position* counts - the start of a
shell segment (after `;`, `&&`, `||`, `|`, `&`, `(`, `{`, a newline, or the
start of the line), optionally behind env assignments (`FOO=1`) and simple
wrappers (`env`, `sudo`, `command`, `exec`, `time`, `nohup`, `npx`, `bunx`),
the same rules as require_draft_first.py / pipeline_trace.py. The executable
is compared by basename (`/usr/bin/git`, decision-1) and git's global flags
(`-C <path>`, `-c k=v`, `--git-dir=...`) are skipped. The words inside a
quoted argument (`git commit -m "... git push ..."`, backlog doc/notes text),
as plain arguments of another command (`echo git push`), or in a heredoc
body are not a push and pass without a task-status check.

Fallback: if the line can't be tokenized (an unbalanced quote outside any
heredoc), command position can't be told apart from text, so any `push`
substring in the heredoc-stripped line is treated as a push - the old
conservative behaviour. A spurious block is recoverable; a missed check on a
real push is not.

Timing caveat (inherent to PreToolUse): the hook runs once, before the whole
Bash line. In `backlog task edit <ID> -s Done ... && git push` the status
edit hasn't run yet when this is judged, so the push is still denied. Run
the status edit as its own command first.

Known gaps (decision-1): `bash -c "git push"`, `eval`, aliases, scripts, and
backtick substitution are not seen.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}  # ---- 1
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")


def has_command(name):
    return shutil.which(name) is not None


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


def segment_runs_git_push(segment):
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) != "git":  # ---- 2
        return False
    j = i + 1
    while j < len(segment):
        tok = segment[j]
        if tok in FLAGS_WITH_ARG:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        break
    return j < len(segment) and segment[j] == "push"


def command_invokes_git_push(command):
    """True if some shell segment of `command` runs `git push` in command
    position. Heredoc bodies and quoted/plain arguments of other commands
    don't count. Falls back to a substring check when unparsable."""
    if not command:
        return False
    # bash joins backslash-newline continuations before parsing words
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return "push" in stripped  # ---- 3
    return any(segment_runs_git_push(s) for s in split_segments(tokens))


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_view(cwd, task_id):
    result = subprocess.run(
        ["backlog", "task", "view", task_id, "--json"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():  # ---- 4
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


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

    if not command_invokes_git_push(command):  # ---- 5
        sys.exit(0)
    if not has_command("backlog"):  # ---- 6
        sys.exit(0)
    if not is_backlog_project(cwd):
        sys.exit(0)

    branch = current_branch(cwd)
    if not branch.startswith("task/"):  # ---- 7
        sys.exit(0)
    task_id = branch[len("task/") :]

    view = task_view(cwd, task_id)
    if view is None:  # ---- 8
        sys.exit(0)

    task = view.get("task", {})
    status = task.get("status", "")
    summary = (task.get("finalSummary") or "").strip()

    if status != "Done":  # ---- 9
        deny(
            f"[claude-code-agile-hooks] {task_id} 가 아직 Done 상태가 아닙니다 (현재: {status}). 완료 처리 후 push하세요."
        )
    if not summary:  # ---- 10
        deny(
            f"[claude-code-agile-hooks] {task_id} 의 final summary가 비어있습니다. "
            f"'backlog task edit {task_id} --final-summary \"...\"' 로 작성 후 push하세요."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 값을 받는 git 전역 플래그
#   설명: `git -C <path> push`처럼 서브커맨드 앞의 전역 플래그와 그 값을 건너뛰어야 push를 찾을 수 있다. 이 집합에 없는 값 플래그는 값이 서브커맨드로 읽힌다.
#   관련: TASK-46
# 2 실행 파일은 basename으로 비교
#   설명: `/usr/bin/git push`처럼 경로로 부른 호출도 같은 git으로 본다. 경로 한정 호출이 관문을 우회하던 문제를 막는다.
#   관련: TASK-46, decision-1
#   개념: 관문 우회
# 3 토큰화 실패 시 push 부분문자열
#   설명: 구문 분석이 안 되면 명령 위치를 알 수 없으니 heredoc 제거 후 'push'가 있으면 push로 본다. 오탐은 복구 가능하지만 진짜 push 미검사는 복구 불가라서다.
#   개념: fail-closed
# 4 task view 실패는 None
#   설명: backlog 조회 실패나 빈 출력이면 상태를 알 수 없다. 호출부가 None을 통과로 처리하므로 도구 오류가 push를 막지 않는다.
#   개념: fail-open
# 5 push가 아니면 즉시 통과
#   설명: TASK-46 이후 이 훅은 모든 Bash 호출에 등록되므로, push 없는 줄은 서브프로세스 없이 파싱 직후 끝나야 한다.
#   관련: TASK-46, hooks/test_hook_registration_contract.py
#   개념: 관문
# 6 backlog CLI 없으면 통과
#   설명: 확인 수단이 없는 환경에서 push를 막으면 영구 차단이 된다.
#   개념: fail-open
# 7 task/ 브랜치만 검사
#   설명: task/<ID> 브랜치가 아니면 어떤 카드의 push인지 알 수 없다. 이 훅의 대상이 아니다.
#   개념: 범위 한정
# 8 카드를 못 읽으면 통과
#   설명: 브랜치명에 해당하는 카드가 없거나 조회가 실패한 경우다. 확인 불가를 막음으로 처리하지 않는다.
#   개념: fail-open
# 9 Done이 아니면 push 거부
#   설명: 완료 처리 전 push를 막는다. 같은 줄의 `-s Done ... && git push`도 상태 편집이 아직 실행되기 전이라 거부되므로 상태 편집을 먼저 단독 실행해야 한다.
#   개념: PreToolUse 타이밍
# 10 final summary가 비면 거부
#   설명: Done이어도 요약이 없으면 완료의 객관적 기록이 없다. 작성 명령을 메시지에 안내한다.
