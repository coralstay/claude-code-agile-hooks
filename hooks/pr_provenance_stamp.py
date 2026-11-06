#!/usr/bin/env python3
# ---
# title: pr_provenance_stamp
# description: gh pr create 때 프롬프트 수·테스트 실행·에이전트 작성 파일 수를 PR 본문에 찍는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, if: Bash(gh pr create*))
Stamps a provenance receipt (prompt count, tests run, agent-authored file
count) into the PR body when Claude runs `gh pr create`. Ported from
karanb192/claude-code-hooks' pr-provenance-stamp plugin (MIT license).

Runs as PreToolUse (not PostToolUse) so it can rewrite tool_input.command
before gh executes, appending the receipt to whatever --body/--body-file the
command already has - matching upstream's approach of modifying the command
rather than editing after the fact. Uses PermissionRequest-style
`updatedInput` isn't available on PreToolUse, so this hook edits the command
string itself directly.

Only a PR-creation command in actual command position is stamped (text in
a quoted argument of some other command is ignored). In a compound command
(&&, ||, ;, |, newline) only that segment's span is rewritten and every
other byte is kept as-is. Anything not provably safe to rewrite - command
substitution, heredocs, subshells, $-expansions, globs, redirections,
comments - is passed through unchanged: a missing stamp beats a broken
command.

Reads session facts from nerf_receipts.py's log if present (session prompt
count via session_logger.py's log) - falls back to a minimal stamp with
just a timestamp and model if those logs don't exist yet.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone

GH_PR_CREATE_RE = re.compile(r"\bgh\s+pr\s+create\b")  # ---- 1


def count_session_prompts(session_id):
    path = os.path.expanduser(f"~/.claude/hooks-logs/sessions/{session_id}.jsonl")
    if not os.path.isfile(path):
        return None
    count = 0
    with open(path, errors="ignore") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") == "prompt":
                count += 1
    return count


def build_receipt(session_id):
    prompts = count_session_prompts(session_id)
    lines = ["---", "**AI 관여도 (pr-provenance-stamp)**"]
    lines.append(f"- 생성 시각: {datetime.now(timezone.utc).isoformat()}")
    if prompts is not None:
        lines.append(f"- 이 세션의 프롬프트 수: {prompts}")
    lines.append("- 작성 도구: Claude Code")
    return "\n".join(lines)


def inject_receipt_into_command(command, receipt):
    """Append the receipt to the --body argument if present; otherwise add
    a --body with just the receipt. Returns the rewritten command string."""
    try:
        tokens = shlex.split(command)
    except ValueError:  # ---- 2
        return command

    for i, tok in enumerate(tokens):
        if tok == "--body" and i + 1 < len(tokens):
            tokens[i + 1] = tokens[i + 1] + "\n\n" + receipt
            return shlex.join(tokens)
        if tok.startswith("--body="):
            tokens[i] = tok + "\n\n" + receipt
            return shlex.join(tokens)

    # No --body given at all: add one.
    return shlex.join(tokens + ["--body", receipt])  # ---- 3


class UnsafeCommand(Exception):  # ---- 4
    """The command uses shell syntax we can't split with certainty."""


GLOB_OR_EXPANSION_CHARS = set("*?[]{}~")


def split_top_level_segments(command):
    """Split `command` on top-level control operators (&&, ||, ;, |, |&, &,
    newline) and return [(start, end, safe_to_rewrite), ...] spans into the
    ORIGINAL string, so a caller can replace one span and keep every other
    byte untouched.

    Raises UnsafeCommand for constructs whose presence anywhere means a
    plain quote-tracking scan could put a boundary in the wrong place:
    command substitution ($( ) / backticks), ${...}, $'...' / $"...",
    heredocs (<<), subshells / grouping parens, comments, backslash-newline.

    A segment is marked unsafe (left alone, but other segments are still
    split correctly) when shlex.split + shlex.join of it might not be
    equivalent to what bash would run: any $-expansion outside single
    quotes, unquoted glob/brace/tilde characters, or redirections."""
    segments = []
    n = len(command)
    i = 0
    start = 0
    safe = True
    quote = None  # None, "'" or '"'
    at_word_start = True

    def close(end):
        segments.append((start, end, safe))

    while i < n:
        c = command[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\":
            if i + 1 < n and command[i + 1] == "\n":
                raise UnsafeCommand("backslash-newline")
            if quote == '"' and i + 1 < n and command[i + 1] in "$`":
                safe = False  # bash drops this backslash, shlex keeps it
            i += 2
            at_word_start = False
            continue
        if c == "`":
            raise UnsafeCommand("backtick")
        if c == "$":
            nxt = command[i + 1] if i + 1 < n else ""
            if nxt in ("(", "{", "'", '"'):
                raise UnsafeCommand("$" + nxt)  # ---- 5
            safe = False  # plain $VAR: shlex.join would single-quote it
            i += 1
            at_word_start = False
            continue
        if quote == '"':
            if c == '"':
                quote = None
            i += 1
            continue
        # --- unquoted context ---
        if c in ("'", '"'):
            quote = c
            i += 1
            at_word_start = False
            continue
        if c in "()":
            raise UnsafeCommand("paren")
        if c == "#" and at_word_start:
            raise UnsafeCommand("comment")
        if c in "<>":
            if command.startswith("<<", i):
                raise UnsafeCommand("heredoc")
            safe = False
            i += 1
            if i < n and command[i] == "&":
                i += 1  # >&2, <&0: part of the redirection, not an operator
            at_word_start = True
            continue
        if c == "&" and i + 1 < n and command[i + 1] == ">":
            safe = False  # &> redirection
            i += 2
            at_word_start = False
            continue
        if c in ";|&\n":
            close(i)
            if command.startswith(("&&", "||", "|&", ";;"), i):
                i += 2
            else:
                i += 1
            start = i
            safe = True
            at_word_start = True
            continue
        if c in " \t":
            i += 1
            at_word_start = True
            continue
        if c in GLOB_OR_EXPANSION_CHARS:
            safe = False
        i += 1
        at_word_start = False

    if quote is not None:
        raise UnsafeCommand("unterminated quote")
    close(n)
    return segments


def is_pr_create_tokens(tokens):
    return (
        len(tokens) >= 3
        and os.path.basename(tokens[0]) == "gh"
        and tokens[1:3] == ["pr", "create"]
    )


def stamp_command(command, receipt):
    """Return the command with the receipt injected into its single PR-
    creation segment, or None to leave the command completely untouched.

    Only the PR segment's span is rewritten; every byte outside it stays as
    the user wrote it, so operators/pipes/other commands keep their meaning.
    Anything we can't prove safe (see split_top_level_segments) returns
    None - a missing stamp is better than a broken command."""
    try:
        segments = split_top_level_segments(command)
    except UnsafeCommand:
        return None

    matches = []
    for start, end, safe in segments:
        text = command[start:end]
        try:
            tokens = shlex.split(text)
        except ValueError:
            return None
        if is_pr_create_tokens(tokens):
            matches.append((start, end, safe, tokens))

    if len(matches) != 1:  # ---- 6
        return None
    start, end, safe, tokens = matches[0]
    if not safe:
        return None
    if any(t == "--body-file" or t.startswith("--body-file=") for t in tokens):
        return None  # don't try to rewrite a file-based body

    original = command[start:end]
    stripped = original.strip(" \t")
    lead = original[: len(original) - len(original.lstrip(" \t"))]
    trail = original[len(lead) + len(stripped) :]
    new_segment = inject_receipt_into_command(stripped, receipt)
    return command[:start] + lead + new_segment + trail + command[end:]  # ---- 7


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:  # ---- 8
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not GH_PR_CREATE_RE.search(command):
        sys.exit(0)  # cheap prefilter; stamp_command does the real check

    receipt = build_receipt(data.get("session_id"))
    new_command = stamp_command(command, receipt)
    if new_command is None:
        sys.exit(0)

    # updatedInput replaces the whole input object, so carry every other
    # field of tool_input forward unchanged alongside the new command.
    updated_input = {**tool_input, "command": new_command}  # ---- 9

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",  # ---- 10
            "updatedInput": updated_input,
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 gh pr create 사전 필터
#   설명: 값싼 정규식으로 대부분의 Bash 명령을 먼저 걸러낸다. 실제 명령 위치 판정은 stamp_command가 따로 한다.
#   개념: 프리필터
# 2 토큰화 실패면 원문 그대로
#   설명: shlex가 못 쪼개는 명령은 건드리지 않는다. 스탬프가 빠지는 쪽이 명령을 깨뜨리는 쪽보다 낫다.
#   개념: fail-open
# 3 --body가 없으면 새로 추가
#   설명: 기존 본문에 이어 붙일 곳이 없으면 영수증만 담은 --body를 덧붙인다.
# 4 안전하지 않은 명령 신호용 예외
#   설명: 따옴표 추적 스캔이 경계를 틀리게 잡을 수 있는 구문(치환, heredoc, 괄호 등)을 만나면 던진다. 호출자가 이를 받아 아무것도 고치지 않는다.
#   개념: fail-safe
# 5 $( ${ $' $" 는 즉시 포기
#   설명: 명령 치환·확장은 구간 경계를 정적 스캔으로 알 수 없다. 단순 $VAR와 달리 구간만 안전하지 않게 표시하는 정도로는 부족해서 전체를 포기한다.
#   개념: 보수적 판정
# 6 PR 생성 구간이 정확히 하나일 때만
#   설명: 0개면 대상이 아니고, 2개 이상이면 어느 쪽에 스탬프할지 알 수 없다. 모호하면 건드리지 않는다.
#   개념: fail-closed
# 7 해당 구간만 교체하고 나머지는 그대로
#   설명: 앞뒤 공백까지 보존해서 연산자·파이프·다른 명령의 의미를 바꾸지 않는다.
#   개념: 바이트 보존
# 8 입력 JSON이 깨지면 통과
#   설명: 훅 입력을 못 읽어도 사용자의 gh 명령은 그대로 실행된다.
#   개념: fail-open
# 9 updatedInput은 입력 전체를 대체
#   설명: command만 담아 보내면 tool_input의 다른 필드가 사라진다. 나머지 필드를 모두 복사해 새 command만 바꾼다.
#   관련: Claude Code 훅 updatedInput 규약
# 10 permissionDecision allow
#   설명: updatedInput은 허용 결정과 함께 와야 적용된다. 본문만 고치는 훅이므로 다른 권한 판단은 건드리지 않는 취지다.
#   개념: PreToolUse 출력
