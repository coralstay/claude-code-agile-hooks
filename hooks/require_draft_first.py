#!/usr/bin/env python3
# ---
# title: require_draft_first
# description: backlog task create를 막고 draft 생성 후 승격하는 흐름으로 안내하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
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


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
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
    if not is_backlog_project(cwd):
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
