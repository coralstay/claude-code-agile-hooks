#!/usr/bin/env python3
"""PreToolUse (matcher: Edit|Write)
TASK-61: test files keep a fixed layout - summary header, then the tests
written from the card's AC/DoD, then the tests that only fill coverage.

Applies only in a backlog.md project (`.git` + `backlog/config.yml` in cwd)
and only to test files of five languages:

- target paths: the project's `testFirst.testGlobs` (`.claude-code-agile-
  hooks.json`, legacy `.claude-rails.json`; same glob semantics as
  require_test_first.py) when that block is well-formed, otherwise these
  basename defaults -
  Python `test_*.py` / `*_test.py`;
  JS/TS `*.test.<ext>` / `*.spec.<ext>` for js, jsx, ts, tsx, mjs, cjs;
  Java `*Test.java` / `*Tests.java`;
  C++ `*_test.cc` / `*_test.cpp` / `*_test.cxx` / `test_*.cpp`.
  Under testGlobs only files with those languages' extensions (.py, .js,
  .jsx, .ts, .tsx, .mjs, .cjs, .java, .cc, .cpp, .cxx) are checked.
- comment syntax: Python `#`; JS/TS/Java/C++ `//`, and the header may also
  be one leading `/* ... */` block.

Layout (Python shown; `//` for the others):

    # TASK-61: 테스트 파일 구조 훅        <- header, one `<ID>: <summary>` per task
    import ...
    # == AC/DoD ==
    def test_x():  # TASK-61#1           <- AC/rule/DoD markers live only here
    # == Coverage ==
    def test_edge(): ...                 <- tests that only fill coverage

Rules (each violation denies the Edit/Write, exit 2, all problems listed):
1. Header: the file's first comment block (leading blank lines and a `#!`
   line skipped; the block ends at the first blank or non-comment line)
   has at least one `<ID>: <summary>` line before any section marker.
   Other comment lines in the block are allowed.

What is checked is the file as it would be after the tool call: Write's
`content`; for Edit the current file with `old_string` replaced by
`new_string` (first occurrence, every one with `replace_all`). An Edit that
would fail anyway (file missing, `old_string` absent) passes.

Scope: a Write that creates a file is always checked. A change to an
existing file is checked when the file before or after the change has the
header or a section marker (a file that adopted the layout can't drop it
quietly). An existing file with neither (grandfathered) passes, with a
non-blocking hint describing the layout (JSON `systemMessage` for the user
and `additionalContext` for the model on stdout, exit 0).

Known limits: files written through Bash (`cat >`, `sed -i`) are not seen;
comments are found line by line, so a string literal line that looks like a
comment counts as one.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys

TAG = "[claude-code-agile-hooks]"
HASH, SLASH = "#", "//"
LANGUAGES = {
    ".py": HASH,
    ".js": SLASH,
    ".jsx": SLASH,
    ".ts": SLASH,
    ".tsx": SLASH,
    ".mjs": SLASH,
    ".cjs": SLASH,
    ".java": SLASH,
    ".cc": SLASH,
    ".cpp": SLASH,
    ".cxx": SLASH,
}
DEFAULT_TEST_NAME_RE = re.compile(
    r"^(?:test_[^/]*\.py|[^/]*_test\.py"
    r"|[^/]*\.(?:test|spec)\.(?:js|jsx|ts|tsx|mjs|cjs)"
    r"|[^/]*Tests?\.java"
    r"|[^/]*_test\.(?:cc|cpp|cxx)|test_[^/]*\.cpp)\Z"
)
TASK_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+:\s+\S")
AC_SECTION = "== AC/DoD =="
COVERAGE_SECTION = "== Coverage =="


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
    return os.path.commonpath([root, target]) != root


def is_glob_list(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(g, str) and g for g in value)
    )


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


def load_test_globs(cwd):
    """testFirst.testGlobs when the project config has a well-formed
    testFirst block, else None (the defaults apply; a malformed block is
    require_test_first.py's to report)."""
    path = project_config_path(cwd)
    if path is None:
        return None
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, ValueError):
        return None
    block = config.get("testFirst") if isinstance(config, dict) else None
    if not isinstance(block, dict) or not is_glob_list(block.get("testGlobs")):
        return None
    return block["testGlobs"]


def is_target(rel, test_globs):
    if test_globs is not None:
        return matches_any(rel, test_globs)
    return bool(DEFAULT_TEST_NAME_RE.match(os.path.basename(rel)))


# --- layout parsing ---


def comment_text(line, lang):
    """The text of a full-line comment, else None. Python: `#`; the others:
    `//`, `/*` (a trailing `*/` dropped) or a `*` continuation line."""
    s = line.strip()
    prefixes = ("#",) if lang == HASH else ("//", "/*", "*")
    for prefix in prefixes:
        if s.startswith(prefix):
            text = s[len(prefix) :]
            if lang == SLASH and text.endswith("*/"):
                text = text[:-2]
            return text.strip()
    return None


def first_comment_block(lines, lang):
    """Comment texts of the file's first comment block."""
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if lang == SLASH and i < len(lines) and lines[i].startswith("#!"):
        i += 1
    if i >= len(lines):
        return []
    if lang == SLASH and lines[i].lstrip().startswith("/*"):
        block = []
        for line in lines[i:]:
            s = line.strip()
            end = "*/" in s
            s = s.split("*/", 1)[0]
            if s.startswith("/*"):
                s = s[2:]
            elif s.startswith("*"):
                s = s[1:]
            block.append(s.strip())
            if end:
                break
        return block
    block = []
    for line in lines[i:]:
        if lang == SLASH and not line.strip().startswith("//"):
            break
        text = comment_text(line, lang)
        if text is None:
            break
        block.append(text)
    return block


def has_header(lines, lang):
    for text in first_comment_block(lines, lang):
        if text in (AC_SECTION, COVERAGE_SECTION):
            return False
        if TASK_LINE_RE.match(text):
            return True
    return False


def section_lines(lines, lang, name):
    return [i for i, line in enumerate(lines) if comment_text(line, lang) == name]


def adopted(text, lang):
    """The file already follows the layout: header or any section marker."""
    lines = text.split("\n")
    return (
        has_header(lines, lang)
        or bool(section_lines(lines, lang, AC_SECTION))
        or bool(section_lines(lines, lang, COVERAGE_SECTION))
    )


def layout_problems(text, lang):
    lines = text.split("\n")
    problems = []
    if not has_header(lines, lang):
        problems.append(
            "첫 주석 블록에 '<ID>: <한 줄 요약>' 헤더가 없습니다(태스크마다 한 줄)."
        )
    return problems


def example(lang):
    c = "#" if lang == HASH else "//"
    return "\n".join(
        [
            f"  {c} TASK-12: 이 테스트 파일이 다루는 내용 한 줄 요약",
            f"  {c} {AC_SECTION}",
            f"  ...AC/DoD 테스트 ({c} TASK-12#1 · TASK-12#B1 · TASK-12#D1 표식은 여기에만)",
            f"  {c} {COVERAGE_SECTION}",
            "  ...커버리지를 채우는 테스트",
        ]
    )


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def hint(rel, lang):
    message = (
        f"{TAG} {rel}은(는) 테스트 파일 구조 규약(헤더 → AC/DoD → Coverage)을 아직 따르지 "
        "않는 기존 파일이라 검사하지 않았습니다. 규약을 적용하려면:\n" + example(lang)
    )
    print(
        json.dumps(
            {
                "systemMessage": message,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": message,
                },
            },
            ensure_ascii=False,
        )
    )


def read_file(path):
    """Current text of `path`, None when it doesn't exist or can't be read."""
    try:
        with open(path, errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def result_text(tool_name, tool_input, old):
    """The file text after the tool call, None when the call would fail."""
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    old_string = tool_input.get("old_string")
    new_string = tool_input.get("new_string")
    if old is None or not isinstance(old_string, str) or not isinstance(new_string, str):
        return None
    if not old_string or old_string not in old:
        return None
    count = -1 if tool_input.get("replace_all") else 1
    return old.replace(old_string, new_string, count)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if tool_name not in ("Edit", "Write") or not isinstance(tool_input, dict):
        sys.exit(0)
    path = tool_input.get("file_path") or ""
    if not isinstance(path, str) or not path or not is_backlog_project(cwd):
        sys.exit(0)
    if is_outside_project(path, cwd):
        sys.exit(0)
    target = os.path.realpath(os.path.join(cwd, path))
    rel = os.path.relpath(target, os.path.realpath(cwd)).replace(os.sep, "/")
    lang = LANGUAGES.get(os.path.splitext(rel)[1])
    if lang is None or not is_target(rel, load_test_globs(cwd)):
        sys.exit(0)

    old = read_file(target) if os.path.isfile(target) else None
    new = result_text(tool_name, tool_input, old)
    if new is None:
        sys.exit(0)
    if old is not None and not adopted(old, lang) and not adopted(new, lang):
        hint(rel, lang)
        sys.exit(0)
    problems = layout_problems(new, lang)
    if problems:
        deny(
            f"{TAG} 테스트 파일 {rel}이(가) 구조 규약(헤더 → AC/DoD → Coverage)을 어깁니다:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n예:\n"
            + example(lang)
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
