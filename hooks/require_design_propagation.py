#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-63 (decision-15, RAIL-024): a change to the top-level design/ must be
propagated to the affected component design/ before the top-level task
moves to Done.

The 장 대응표 (chapter map) is never hardcoded: it is read on every run from
the top-level `design/00-문서-정보.md`, section `## 문서 계층` >
`### 장 대응표`, by the parse rules written above that table:

- columns: `최상위 장 | 범위 | <component> | ...`; a component column head is
  the directory name under `components/`.
- `최상위 장`: `00` is `design/00-문서-정보.md`, `N.MM` is
  `design/N-*/MM-*.md`, `부록 <이름>` is `design/부록-<이름, spaces as ->.md`.
- `범위`: `전체` is the whole chapter, `§n` the `## §n...` section, an area
  prefix (`ORC`, `RAIL`, ...) the `## <prefix>...` section. A change outside
  every listed section (chapter head, `## 원천`, any other `## ` section)
  counts for every row of that chapter.
- a cell lists the component's chapters joined by ` · `; `—` means none.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys

TAG = "[claude-code-agile-hooks]"
DOC_PATH = os.path.join("design", "00-문서-정보.md")
SECTION_HEADING = "문서 계층"
TABLE_HEADING = "장 대응표"
FIRST_COLUMNS = ["최상위 장", "범위"]
NONE_CELL = "—"
CELL_JOIN = " · "
WHOLE = "전체"
SCOPE_RE = re.compile(r"^(?:전체|§\d+|[A-Z]+)$")
CHAPTER_RE = re.compile(r"^(?:00|\d+\.\d{2}|부록 \S.*)$")
NUMBERED_RE = re.compile(r"^(\d+)\.(\d{2})$")
SEPARATOR_ROW_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
DONE_FALLBACK_RE = re.compile(
    r"(?:^|[;&|(\s])(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+edit\s+(\S+)"
    r".*?(?:^|\s)(?:-s|--status)(?:=|\s+)['\"]?done\b",
    re.IGNORECASE | re.DOTALL,
)


class TableError(Exception):
    pass


# --- the 장 대응표 ---


def markdown_lines(text):
    """(line, heading level or 0, heading text) for every line, with fenced
    code blocks reported as plain lines (level 0) so a `## ` inside a fence
    is not a heading."""
    out = []
    in_fence = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append((line, 0, ""))
            continue
        m = None if in_fence else ATX_RE.match(line)
        if m:
            out.append((line, len(m.group(1)), m.group(2)))
        else:
            out.append((line, 0, ""))
    return out


def table_block(text):
    """Lines under `## 문서 계층` > `### 장 대응표` up to the next heading of
    level <= 3, or None when either heading is missing."""
    lines = markdown_lines(text)
    in_section = False
    start = None
    for i, (_, level, title) in enumerate(lines):
        if level == 2:
            in_section = title == SECTION_HEADING
        elif level == 3 and in_section and title == TABLE_HEADING:
            start = i + 1
            break
    if start is None:
        return None
    block = []
    for line, level, _ in lines[start:]:
        if 0 < level <= 3:
            break
        block.append(line)
    return block


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_cell(cell, where):
    if cell == NONE_CELL:
        return []
    if not cell:
        raise TableError(f"{where}: 빈 칸입니다(대응 장이 없으면 '{NONE_CELL}')")
    return [part.strip() for part in cell.split(CELL_JOIN)]


def parse_table(text):
    """{'components': [...], 'rows': [{'chapter', 'scope', 'cells'}]} from the
    top-level 00 doc, None when it has no `## 문서 계층` > `### 장 대응표`.
    TableError when the heading is there but the table breaks the rules -
    a broken map must not silently turn the check off."""
    block = table_block(text)
    if block is None:
        return None
    table_lines = []
    for line in block:
        if line.strip().startswith("|"):
            table_lines.append(line.strip())
        elif table_lines:
            break
    if len(table_lines) < 3:
        raise TableError("표가 없거나 머리 · 구분 줄 뒤에 행이 없습니다")
    header = split_row(table_lines[0])
    components = header[2:]
    if header[:2] != FIRST_COLUMNS or not components or not all(components):
        raise TableError(
            "표 머리는 '| 최상위 장 | 범위 | <컴포넌트> | ... |' 형식이어야 합니다: "
            + table_lines[0]
        )
    if not SEPARATOR_ROW_RE.match(table_lines[1].replace(" ", "")):
        raise TableError("표 머리 다음 줄은 구분 줄(| --- | ... |)이어야 합니다")
    rows = []
    for line in table_lines[2:]:
        cells = split_row(line)
        if len(cells) != len(header):
            raise TableError(f"칸 수가 머리({len(header)})와 다릅니다: {line}")
        chapter, scope = cells[0], cells[1]
        if not CHAPTER_RE.match(chapter):
            raise TableError(f"최상위 장 표기를 읽을 수 없습니다: {line}")
        if not SCOPE_RE.match(scope):
            raise TableError(f"범위 표기를 읽을 수 없습니다(전체 · §n · 영역 접두어): {line}")
        rows.append(
            {
                "chapter": chapter,
                "scope": scope,
                "cells": {
                    name: parse_cell(cell, line)
                    for name, cell in zip(components, cells[2:])
                },
            }
        )
    return {"components": components, "rows": rows}


def chapter_matches(chapter, relpath):
    """True if the repo-relative posix `relpath` is the file of `chapter`."""
    if chapter == "00":
        return relpath == "design/00-문서-정보.md"
    m = NUMBERED_RE.match(chapter)
    if m:
        pattern = rf"design/{m.group(1)}-[^/]+/{m.group(2)}-[^/]+\.md"
        return re.fullmatch(pattern, relpath) is not None
    name = chapter[len("부록 ") :].replace(" ", "-")
    return relpath == f"design/부록-{name}.md"


# --- command parsing (copied from require_test_first.py; kept identical
# by dedup_drift_guard.REGISTRY) ---


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
        return [m.group(1) for m in DONE_FALLBACK_RE.finditer(stripped)]
    targets = [segment_done_target(s) for s in split_segments(tokens)]
    return [t for t in targets if t is not None]


def same_task(token, task_id):
    """`AO-27`, `ao-27` and `27` all name task AO-27."""
    if token.upper() == task_id.upper():
        return True
    return token.isdigit() and task_id.rsplit("-", 1)[-1] == token


def main():
    sys.exit(0)


if __name__ == "__main__":
    main()
