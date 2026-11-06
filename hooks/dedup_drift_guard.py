#!/usr/bin/env python3
# ---
# title: dedup_drift_guard
# description: 훅 사이에 복붙된 함수가 어긋나지 않았는지 REGISTRY로 사후 검증하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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
behavioral difference does). The checked repo's own REGISTRY (read as data
from its hooks/dedup_drift_guard.py) takes precedence over the one embedded
here; see load_repo_registry() (TASK-40).

TASK-46: the `if: Bash(git *)` filter is kept on purpose. It matches the
command text per subcommand (measured 2026-10-04), so `/usr/bin/git commit`
and `FOO=1 git commit` skip this check - accepted, because this is a drift
detector rather than a security control and test_dedup_registry.py catches
the same drift in the test suite. The gap is listed with that reason in
hooks/test_hook_registration_contract.py (`hidden_ok`).

Fully self-contained: no imports from any other file in this repo."""

import ast
import json
import os
import shlex
import sys

REGISTRY = {  # ---- 1
    "is_backlog_project": [
        "require_active_task.py",
        "pre_commit_check.py",
        "pre_push_check.py",
        "block_stop_if_dirty.py",
        "session_start.py",
        "require_draft_first.py",
        "backlog_commit_scope.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_stage_committed.py",
        "require_work_order.py",
        "require_test_layout.py",
        "require_coverage_on_done.py",
    ],
    "has_command": [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "pre_push_check.py",
        "require_active_task.py",
        "session_start.py",
        "backlog_commit_scope.py",
        "require_test_first.py",
        "require_stage_committed.py",
    ],
    "has_active_task": [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "require_active_task.py",
    ],
    "run_shell": [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    # TASK-54: .claude-code-agile-hooks.json 우선, 옛 .claude-rails.json fallback
    "project_config_path": [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_test_layout.py",
        "require_coverage_on_done.py",
    ],
    # TASK-29: 셸 명령을 세그먼트 단위로 나누는 토크나이저(드래프트 워크플로 훅 2개)
    "tokenize": [
        "require_draft_first.py",
        "backlog_commit_scope.py",
        "pipeline_trace.py",
        "pre_push_check.py",
        "config_guard.py",
        "pre_git_safety_check.py",
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_stage_committed.py",
        "require_work_order.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    "split_segments": [
        "require_draft_first.py",
        "backlog_commit_scope.py",
        "pipeline_trace.py",
        "pre_push_check.py",
        "config_guard.py",
        "pre_git_safety_check.py",
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_stage_committed.py",
        "require_work_order.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    # TASK-32: pipeline_trace.py가 드래프트 명령 감지(heredoc 제외)와
    # 프로젝트 안/밖 판정(TASK-27 realpath 로직)을 그대로 복사해 쓴다
    "strip_heredoc_bodies": [
        "require_draft_first.py",
        "pipeline_trace.py",
        "pre_push_check.py",
        "pre_git_safety_check.py",
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "backlog_commit_scope.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_stage_committed.py",
        "require_work_order.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    # TASK-34: pre_push_check.py가 명령 위치의 git push만 판정하도록
    # pipeline_trace.py의 명령 위치 판정(env 할당·래퍼 건너뛰기)을 그대로 복사해 쓴다
    # TASK-37: pre_git_safety_check.py도 같은 4개 헬퍼를 그대로 복사해 쓴다
    # TASK-39: pre_commit_check.py·pre_push_coverage_check.py·
    # backlog_commit_scope.py도 같은 헬퍼로 명령 위치의 git 하위 명령만 판정한다
    "command_head": [
        "pipeline_trace.py",
        "pre_push_check.py",
        "config_guard.py",
        "pre_git_safety_check.py",
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "backlog_commit_scope.py",
        "require_test_first.py",
        "require_implementation_plan.py",
        "require_stage_committed.py",
        "require_work_order.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    "git_subcommand_index": [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "backlog_commit_scope.py",
    ],
    "command_runs_git": [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
        "backlog_commit_scope.py",
    ],
    "is_outside_project": [
        "require_active_task.py",
        "pipeline_trace.py",
        "require_test_first.py",
        "require_test_layout.py",
    ],
    # TASK-61: require_test_layout.py가 testFirst.testGlobs를 같은 의미로 읽도록
    # require_test_first.py의 glob 헬퍼를 그대로 복사해 쓴다
    "is_glob_list": [
        "require_test_first.py",
        "require_test_layout.py",
    ],
    "glob_regex": [
        "require_test_first.py",
        "require_test_layout.py",
    ],
    "glob_matches": [
        "require_test_first.py",
        "require_test_layout.py",
    ],
    "matches_any": [
        "require_test_first.py",
        "require_test_layout.py",
    ],
    # TASK-31: Stop payload의 background_tasks로 parallel_session을 판정하는 헬퍼
    "background_tasks_running": [
        "block_stop_if_dirty.py",
        "context_flags.py",
    ],
    # TASK-60: require_work_order.py가 작업 순서 해시를 직접 다시 계산하도록
    # scripts/work_order.py의 헬퍼를 그대로 복사해 쓴다(hooks/ 기준 상대 경로).
    # backlog_commit_scope.py도 작업 순서 커밋의 의존 변경 판정에 앞의 둘을 쓴다
    "parse_frontmatter": [
        "../scripts/work_order.py",
        "require_work_order.py",
        "backlog_commit_scope.py",
    ],
    "parse_task": [
        "../scripts/work_order.py",
        "require_work_order.py",
        "backlog_commit_scope.py",
    ],
    "natural_key": ["../scripts/work_order.py", "require_work_order.py"],
    "read_tasks": ["../scripts/work_order.py", "require_work_order.py"],
    "incomplete_tasks": ["../scripts/work_order.py", "require_work_order.py"],
    "input_hash": ["../scripts/work_order.py", "require_work_order.py"],
    # TASK-62: 완료(-s Done) 시점 커버리지 게이트 require_coverage_on_done.py가
    # require_test_first.py의 Done 이동 판정과 push 게이트의 언어 감지 ·
    # 설정 읽기를 그대로 복사해 쓴다
    "segment_done_target": [
        "require_test_first.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    "done_targets": [
        "require_test_first.py",
        "require_coverage_on_done.py",
        "require_design_propagation.py",  # TASK-63
    ],
    "configured_coverage_command": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "language_manifests": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "detect_languages": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "missing_command_payload": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    # TASK-62#3: 커버리지 실행과 언어별 리포트(이번 실행 이후 mtime) 확인
    "default_report_paths": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "configured_report_dir": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "report_paths": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "fresh_report": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    "coverage_verdict": [
        "pre_push_coverage_check.py",
        "require_coverage_on_done.py",
    ],
    # TASK-63: require_design_propagation.py가 require_test_first.py의
    # `backlog task edit <ID> -s Done` 명령 위치 판정(segment_done_target ·
    # done_targets · same_task)을 그대로 복사해 쓴다
    "same_task": [
        "require_test_first.py",
        "require_design_propagation.py",
    ],
    # current_branch()는 파일마다 반환값 계약이 다르다(빈 문자열 vs None) —
    # 의도된 차이로 보이므로 REGISTRY에 등록하지 않는다.
}

FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}  # ---- 2


# TASK-39: once copied into four hooks; the other three now use the
# command-position helpers (command_runs_git), so this single copy is no
# longer in REGISTRY. It still looks at the word after any `git` token, so
# `echo git commit` runs the (cheap, read-only) drift check - accepted.
def command_invokes_git_subcommand(command, subcommand):
    """True if `command` runs `git <subcommand>` anywhere, regardless of
    global flags (like `-C <path>`) placed before the subcommand."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return subcommand in command  # ---- 3

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


def valid_registry(value):
    """True if `value` has REGISTRY's shape: dict of str -> list of
    non-empty str."""
    return isinstance(value, dict) and all(  # ---- 4
        isinstance(name, str)
        and isinstance(files, list)
        and all(isinstance(f, str) and f for f in files)
        for name, files in value.items()
    )


def load_repo_registry(hooks_dir):
    """TASK-40: returns the REGISTRY of the checked repo's own
    hooks/dedup_drift_guard.py, or None if it can't be used. The installed
    copy otherwise judges the repo with its own (possibly stale) REGISTRY,
    which blocks every commit that edits the repo REGISTRY.

    Read as data only - the file is parsed with `ast` and just the last
    top-level `REGISTRY = {...}` is evaluated with ast.literal_eval, so
    nothing from the repo is imported or executed (self-contained design,
    decision-3). Read from the working tree, the same snapshot find_drift()
    reads the hook copies from.

    The repo REGISTRY is trusted as-is, even if emptied or weakened: it is
    the reviewed source of truth, and this guard is a drift detector, not a
    security control."""
    path = os.path.join(hooks_dir, "dedup_drift_guard.py")
    try:
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)  # ---- 5
    except (OSError, SyntaxError, ValueError):
        return None
    value_node = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "REGISTRY"
        ):
            value_node = node.value  # ---- 6
    if value_node is None:
        return None
    try:
        value = ast.literal_eval(value_node)  # ---- 7
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    return value if valid_registry(value) else None


def registry_files_present(hooks_dir, registry=REGISTRY):
    """Self-guard: only act inside claude-code-agile-hooks's own hooks/ directory. If
    any file the REGISTRY references is missing, this isn't that repo -
    stay quiet."""
    all_files = {f for files in registry.values() for f in files}
    return all(os.path.isfile(os.path.join(hooks_dir, f)) for f in all_files)  # ---- 8


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
            return ast.dump(node, annotate_fields=False, include_attributes=False)  # ---- 9
    return None


def find_drift(hooks_dir, registry=REGISTRY):
    """Returns a list of human-readable problem descriptions, one per
    (function, files) registry entry that has drifted or is missing
    somewhere. Empty list means everything matches."""
    problems = []
    for function_name, files in registry.items():
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

        if len(set(present.values())) > 1:  # ---- 10
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

    if not command_invokes_git_subcommand(command, "commit"):  # ---- 11
        sys.exit(0)

    hooks_dir = os.path.join(cwd, "hooks")
    registry = load_repo_registry(hooks_dir)
    if registry is None:
        registry = REGISTRY
    if not registry_files_present(hooks_dir, registry):  # ---- 12
        sys.exit(0)

    problems = find_drift(hooks_dir, registry)
    if problems:
        deny(
            "[claude-code-agile-hooks] 복붙된 훅 함수가 사본 간에 어긋났습니다 (dedup drift). "
            "모든 사본을 동일하게 수정한 뒤 다시 커밋하세요:\n" + "\n".join(problems)
        )

    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 복붙 함수 REGISTRY
#   설명: 함수 이름 → 그 함수가 AST까지 같아야 하는 훅 파일 목록이다. 훅끼리 import하지 않는 설계(자립)의 대가로 생기는 복붙 어긋남을, 이 표 하나로 기계가 검사하게 만든다.
#   관련: hooks/test_dedup_registry.py, decision-2, decision-3
#   개념: SSOT 보완, 자립 훅
# 2 값을 받는 git 전역 플래그
#   설명: `git -C <path> commit`처럼 서브커맨드 앞에 값 인자가 오는 플래그는 값까지 건너뛰어야 한다. 빠뜨리면 `-C /path`의 경로를 서브커맨드로 오인한다.
# 3 토큰화 실패 시 부분 문자열 폴백
#   설명: 따옴표가 안 닫힌 명령은 구조를 알 수 없어 단순 포함 검사로 대신한다. 이 훅은 드리프트 탐지기이고 보안 통제가 아니므로 과검사(싼 읽기 전용)가 안전한 쪽이다.
#   관련: TASK-39
# 4 레포 REGISTRY 모양 검증
#   설명: 리터럴로 읽은 값이 dict[str, list[비어 있지 않은 str]]일 때만 쓴다. 모양이 틀린 값을 쓰면 이후 순회에서 예외가 나므로 사용 불가(None)로 돌려 내장 REGISTRY로 폴백한다.
#   관련: TASK-40
# 5 레포 파일을 실행하지 않고 파싱만
#   설명: 검사 대상 레포의 hooks/dedup_drift_guard.py를 import하지 않고 ast로만 읽는다. 검사 대상이 임의 코드를 실행하게 두지 않는 자립 설계(decision-3)의 보안 근거다.
#   관련: decision-3
#   개념: 데이터로만 읽기
# 6 마지막 REGISTRY 대입이 이긴다
#   설명: 최상위에 REGISTRY 대입이 여러 번이면 파이썬 의미대로 마지막 값을 쓰도록 덮어쓴다.
# 7 literal_eval로 평가
#   설명: 리터럴만 허용하는 평가라 호출 · 이름 참조가 있으면 실패한다. 어떤 예외든 None으로 돌려 내장 REGISTRY를 쓴다(실패해도 커밋을 막지 않는다).
#   관련: TASK-40
#   개념: literal_eval
# 8 자기 레포 자가 판별
#   설명: REGISTRY가 가리키는 파일이 하나라도 없으면 이 레포가 아니다. 다른 프로젝트의 커밋에서는 조용히 있도록(fail-open) 하는 안전장치다.
#   개념: fail-open
# 9 정규화한 AST로 비교
#   설명: 주석 · 공백 · 줄 번호(include_attributes=False)를 빼고 구조만 덤프해 문서화 편집은 허용하고 동작 차이는 잡아낸다. 소스 헤더 본문 노트 표식도 주석이라 이 비교에 영향이 없다.
#   개념: AST 정규화
# 10 어긋남 판정
#   설명: 덤프 문자열이 한 종류를 넘으면 사본끼리 다르다는 뜻이다. 첫 파일을 기준으로 삼아 다른 파일 목록을 보고한다.
# 11 커밋일 때만 검사
#   설명: 설정에서 `if: Bash(git *)` 필터를 의도적으로 유지하므로 git 명령만 들어온다. 그 안에서도 commit이 아니면 즉시 종료한다.
#   관련: TASK-46, hooks/test_hook_registration_contract.py
#   개념: 훅 필터
# 12 다른 레포에서는 조용히 통과
#   설명: REGISTRY의 파일이 없으면 이 도구 레포가 아니므로 아무것도 막지 않는다. 설치된 훅이 모든 프로젝트의 커밋에 걸려 있기 때문에 필요한 자가 가드다.
#   개념: fail-open
