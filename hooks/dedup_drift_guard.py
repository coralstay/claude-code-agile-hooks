#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, if: Bash(git *))
The 27 hooks in this repo are deliberately self-contained (no shared
imports between hook files - see require_active_task.py's module
docstring), which means some functions are hand-copied across several
files. That's exactly how a 2026-09-18 bug happened: a fix to
`is_backlog_project()` landed in require_active_task.py but never
propagated to its four other copies (see decision-2 in this repo's
backlog for the full writeup).

hooks/test_dedup_registry.py already catches this class of bug at the
pytest level, but only if someone actually runs pytest. This hook makes
the same check physically block `git commit` at commit time.

REGISTRY maps a function name to the list of hook files (relative to
hooks/) in which it must appear byte-for-byte-equivalent (compared via
normalized AST, so comments/formatting differences don't matter, but any
behavioral difference does).

Fully self-contained: no imports from any other file in this repo."""

import ast
import json
import os
import shlex
import sys

REGISTRY = {
    "is_backlog_project": [
        "require_active_task.py",
        "pre_commit_check.py",
        "pre_push_check.py",
        "block_stop_if_dirty.py",
        "session_start.py",
        "require_draft_first.py",
        "backlog_commit_scope.py",
    ],
    "command_invokes_git_subcommand": [
        "pre_commit_check.py",
        "pre_push_check.py",
        "pre_push_coverage_check.py",
        "dedup_drift_guard.py",
        "backlog_commit_scope.py",
    ],
    "has_command": [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "pre_push_check.py",
        "require_active_task.py",
        "session_start.py",
        "backlog_commit_scope.py",
    ],
    "has_active_task": [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "require_active_task.py",
    ],
    "run_shell": [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
    ],
    # TASK-29: 셸 명령을 세그먼트 단위로 나누는 토크나이저(드래프트 워크플로 훅 2개)
    "tokenize": [
        "require_draft_first.py",
        "backlog_commit_scope.py",
    ],
    "split_segments": [
        "require_draft_first.py",
        "backlog_commit_scope.py",
    ],
    # TASK-31: Stop payload의 background_tasks로 parallel_session을 판정하는 헬퍼
    "background_tasks_running": [
        "block_stop_if_dirty.py",
        "context_flags.py",
    ],
    # current_branch()는 파일마다 반환값 계약이 다르다(빈 문자열 vs None) —
    # 의도된 차이로 보이므로 REGISTRY에 등록하지 않는다.
}

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def command_invokes_git_subcommand(command, subcommand):
    """True if `command` runs `git <subcommand>` anywhere, regardless of
    global flags (like `-C <path>`) placed before the subcommand."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return subcommand in command

    i = 0
    while i < len(tokens):
        if os.path.basename(tokens[i]) != "git":
            i += 1
            continue
        j = i + 1
        while j < len(tokens):
            tok = tokens[j]
            if tok in FLAGS_WITH_ARG:
                j += 2
                continue
            if tok.startswith("-"):
                j += 1
                continue
            if tok == subcommand:
                return True
            break
        i = j
    return False


def registry_files_present(hooks_dir):
    """Self-guard: only act inside claude-rails' own hooks/ directory. If
    any file the REGISTRY references is missing, this isn't that repo -
    stay quiet."""
    all_files = {f for files in REGISTRY.values() for f in files}
    return all(os.path.isfile(os.path.join(hooks_dir, f)) for f in all_files)


def function_ast_dump(path, function_name):
    """Returns the normalized AST dump of `function_name` defined in
    `path`, or None if the file can't be parsed or the function isn't
    defined there."""
    try:
        with open(path) as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.dump(node, annotate_fields=False, include_attributes=False)
    return None


def find_drift(hooks_dir):
    """Returns a list of human-readable problem descriptions, one per
    (function, files) registry entry that has drifted or is missing
    somewhere. Empty list means everything matches."""
    problems = []
    for function_name, files in REGISTRY.items():
        dumps = {}
        for filename in files:
            path = os.path.join(hooks_dir, filename)
            dumps[filename] = function_ast_dump(path, function_name)

        missing = [f for f, d in dumps.items() if d is None]
        present = {f: d for f, d in dumps.items() if d is not None}

        if missing:
            problems.append(
                f"- {function_name}(): 다음 파일에서 함수를 찾을 수 없습니다 (파싱 실패 또는 "
                f"함수 없음): {', '.join(sorted(missing))}"
            )

        if len(set(present.values())) > 1:
            baseline_file = next(iter(present))
            baseline_dump = present[baseline_file]
            mismatched = [
                f
                for f, d in present.items()
                if d != baseline_dump and f != baseline_file
            ]
            problems.append(
                f"- {function_name}(): {baseline_file} 기준과 다른 파일: {', '.join(sorted(mismatched))}"
            )

    return problems


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

    if not command_invokes_git_subcommand(command, "commit"):
        sys.exit(0)

    hooks_dir = os.path.join(cwd, "hooks")
    if not registry_files_present(hooks_dir):
        sys.exit(0)

    problems = find_drift(hooks_dir)
    if problems:
        deny(
            "[claude-rails] 복붙된 훅 함수가 사본 간에 어긋났습니다 (dedup drift). "
            "모든 사본을 동일하게 수정한 뒤 다시 커밋하세요:\n" + "\n".join(problems)
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
