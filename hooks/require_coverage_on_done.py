#!/usr/bin/env python3
# ---
# title: require_coverage_on_done
# description: 태스크를 Done으로 옮길 때도 커버리지 게이트를 돌리는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-62: the coverage gate also runs when a task is moved to Done, not only
before a push (pre_push_coverage_check.py). Same nature as that hook, so it
is a separate self-contained hook (decision-3) sharing its detection code
by copy (dedup_drift_guard.REGISTRY, decision-2).

Applies to a `backlog task edit <ID> ... -s Done` (`--status Done`,
`--status=Done`, any case) in command position - parsed like
require_test_first.py (heredoc bodies dropped, continuations joined,
segments split, env assignments and wrappers skipped, `backlog` compared by
basename; unbalanced quotes: a text match stands in) - in a backlog.md
project (`.git` + `backlog/config.yml` in cwd). Any task ID counts: coverage
is a property of the whole project, not of the branch's task. Indirection
(`bash -c`, `eval`, scripts) and the backlog MCP server / web UI are not
seen.

Languages are detected by their manifest at the project root
(package.json -> javascript, tsconfig.json -> typescript, pom.xml /
build.gradle(.kts) -> java, pyproject.toml / setup.cfg / pytest.ini ->
python, CMakeLists.txt -> cpp).

- a language detected and no `coverageCommand` in the project config
  (.claude-code-agile-hooks.json, legacy .claude-rails.json) -> deny;
- no language detected and no coverageCommand -> pass (opt-in, as before);
- otherwise the coverageCommand runs (the whole suite - a Done move costs
  one coverage run) and the move is denied when it exits non-zero (the
  tool's own 100% line + branch threshold failed), when coverageReportDir
  is malformed, or when a detected language has no report written by this
  run in its report location (defaults: coverage/ for javascript,
  typescript and cpp; target/site/jacoco/ or build/reports/jacoco/ for
  java; htmlcov/ or coverage.xml for python; overridable with
  `coverageReportDir`, a path string for every language or a
  {"<language>": "<path>"} map). On a pass the measured report is shown
  and no permission decision is made.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys
import time

TAG = "[claude-code-agile-hooks]"
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
DONE_FALLBACK_RE = re.compile(  # ---- 1
    r"(?:^|[;&|(\s])(?:\S*/)?backlog(?:\.md)?\s+tasks?\s+edit\s+(\S+)"
    r".*?(?:^|\s)(?:-s|--status)(?:=|\s+)['\"]?done\b",
    re.IGNORECASE | re.DOTALL,
)


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
    for name in (".claude-code-agile-hooks.json", ".claude-rails.json"):  # ---- 2
        path = os.path.join(cwd, name)
        if os.path.isfile(path):
            return path
    return None


def configured_coverage_command(cwd):
    config_path = project_config_path(cwd)
    if config_path is None:
        return None
    with open(config_path) as f:
        config = json.load(f)  # ---- 3
    return config.get("coverageCommand") or None


# --- command parsing (strip_heredoc_bodies/tokenize/split_segments/
# command_head/segment_done_target/done_targets are registered in
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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 4
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return [m.group(1) for m in DONE_FALLBACK_RE.finditer(stripped)]  # ---- 5
    targets = [segment_done_target(s) for s in split_segments(tokens)]
    return [t for t in targets if t is not None]


# --- languages, coverage run and reports (registered in
# dedup_drift_guard.REGISTRY, same code as pre_push_coverage_check.py) ---


def language_manifests():
    """(language, manifest file names at the project root), in report
    order."""
    return [
        ("javascript", ("package.json",)),
        ("typescript", ("tsconfig.json",)),
        ("java", ("pom.xml", "build.gradle", "build.gradle.kts")),
        ("python", ("pyproject.toml", "setup.cfg", "pytest.ini")),
        ("cpp", ("CMakeLists.txt",)),
    ]


def detect_languages(cwd):
    """Languages whose manifest is a file directly in `cwd` (subdirectories
    are not searched), in language_manifests() order."""
    if not cwd:
        return []
    return [
        language
        for language, names in language_manifests()
        if any(os.path.isfile(os.path.join(cwd, n)) for n in names)
    ]


def missing_command_payload(languages):
    """PreToolUse deny for a project whose languages need coverage but
    whose config has no coverageCommand."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{TAG} 감지된 언어({', '.join(languages)})는 커버리지 100%(line + "
                "branch)가 필수인데 프로젝트 설정(.claude-code-agile-hooks.json)에 "
                "coverageCommand가 없습니다. 언어별 설정 예와 리포트 위치는 "
                "claude-code-agile-hooks README의 '커버리지 100%' 절을 보세요."
            ),
        }
    }


def run_shell(cwd, command):
    result = subprocess.run(
        command, cwd=cwd, shell=True, capture_output=True, text=True  # ---- 6
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def default_report_paths():
    """Where each language's coverage report lands by default, relative to
    the project root; a fresh file at any one of a language's paths (a
    file, or any file under a directory) counts as its report. Sources:
    README '커버리지 100%' 절."""
    return {
        "javascript": ("coverage",),
        "typescript": ("coverage",),
        "java": ("target/site/jacoco", "build/reports/jacoco"),
        "python": ("htmlcov", "coverage.xml"),
        "cpp": ("coverage",),
    }


def configured_report_dir(cwd):
    """The raw `coverageReportDir` value of the project config, or None."""
    config_path = project_config_path(cwd)
    if config_path is None:
        return None
    with open(config_path) as f:
        config = json.load(f)
    return config.get("coverageReportDir")


def report_paths(languages, override):
    """{language: paths} for the detected languages. `override` (the
    config's coverageReportDir): None -> defaults; a non-empty string ->
    that one path for every language; a map of known language -> non-empty
    string -> that path for the languages it names, defaults for the rest.
    Anything else raises ValueError."""
    defaults = default_report_paths()
    if override is None:
        return {lang: defaults[lang] for lang in languages}
    if isinstance(override, str) and override:
        return {lang: (override,) for lang in languages}
    if isinstance(override, dict) and all(
        key in defaults and isinstance(value, str) and value
        for key, value in override.items()
    ):
        return {
            lang: (override[lang],) if lang in override else defaults[lang]
            for lang in languages
        }
    raise ValueError(
        "coverageReportDir는 비어 있지 않은 경로 문자열이거나 "
        '{"<언어>": "<경로>"} 맵이어야 합니다(언어: '
        + ", ".join(defaults)
        + ")."
    )


def fresh_report(cwd, path, since):
    """True if `path` (relative to cwd) is a file, or a directory holding a
    file anywhere below it, whose mtime is at or after `since`. Entries
    that can't be stat'ed (dangling symlinks, races) are skipped."""
    full = os.path.join(cwd, path)
    candidates = [full] if os.path.isfile(full) else (
        os.path.join(dirpath, name)
        for dirpath, _, names in os.walk(full)
        for name in names
    )
    for candidate in candidates:
        try:
            if os.path.getmtime(candidate) >= since:
                return True
        except OSError:
            continue
    return False


def coverage_verdict(cwd, command, languages, report_dir):
    """Run the coverage command and judge it: (exit code or None, output,
    problem or None). Problems: a malformed coverageReportDir (the command
    is not run), a non-zero exit (the tool's own 100% threshold failed), or
    a detected language with no report written by this run. The run start
    is floored to the whole second so a report written in the same second
    still counts on file systems with 1 s mtime resolution."""
    try:
        paths = report_paths(languages, report_dir)
    except ValueError as exc:
        return None, "", str(exc)
    since = int(time.time())  # ---- 7
    exit_code, output = run_shell(cwd, command)
    if exit_code != 0:  # ---- 8
        return exit_code, output, f"커버리지 기준 미달 (exit {exit_code})"
    missing = [
        f"{lang}: {' 또는 '.join(candidates)}"
        for lang, candidates in paths.items()
        if not any(fresh_report(cwd, p, since) for p in candidates)  # ---- 9
    ]
    if missing:
        return exit_code, output, (
            "coverageCommand는 성공했지만 이번 실행이 만든 커버리지 리포트가 없습니다 - "
            + "; ".join(missing)
            + " (위치는 coverageReportDir로 바꿀 수 있습니다)"
        )
    return exit_code, output, None


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") != "Bash" or not isinstance(tool_input, dict):
        sys.exit(0)
    # cheap parse first: most Bash lines leave before any file or subprocess
    if not done_targets(tool_input.get("command") or ""):  # ---- 10
        sys.exit(0)
    cwd = data.get("cwd", "")
    if not is_backlog_project(cwd):  # ---- 11
        sys.exit(0)

    command = configured_coverage_command(cwd)
    languages = detect_languages(cwd)
    if not command:  # ---- 12
        if languages:
            print(json.dumps(missing_command_payload(languages)))
        sys.exit(0)

    exit_code, output, problem = coverage_verdict(
        cwd, command, languages, configured_report_dir(cwd)
    )
    report = f"{TAG} 커버리지 리포트 ('{command}', exit {exit_code}):\n" + output[-4000:]
    if problem is None:
        # pass: show the measured report, leave the permission decision alone
        print(json.dumps({"systemMessage": report}))  # ---- 13
        sys.exit(0)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",  # ---- 14
                    "permissionDecisionReason": (
                        f"{TAG} -s Done 전에 커버리지 게이트를 통과해야 합니다: "
                        f"{problem}\n" + report
                    ),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 Done 이동 텍스트 폴백 정규식
#   설명: 따옴표 불균형으로 토큰화가 실패한 줄에서도 `-s Done`을 놓치지 않도록 문자열로 잡는다. require_test_first.py와 같은 복사본이며 REGISTRY가 어긋남을 감시한다.
#   관련: hooks/require_test_first.py
#   개념: fail-closed 폴백
# 2 설정 파일 이름 마이그레이션
#   설명: 새 이름을 우선하고 옛 이름으로 폴백한다. 사본이 여럿이라 REGISTRY가 같게 유지하는지 감시한다.
#   관련: TASK-54, hooks/dedup_drift_guard.py REGISTRY(project_config_path)
# 3 설정 JSON 오류를 잡지 않음
#   설명: 깨진 설정이면 예외로 훅이 비정상 종료한다. 조용히 게이트를 끄지 않고 오류를 드러내지만 차단은 되지 않는 한계가 있다.
#   개념: fail-open 한계
# 4 백슬래시 개행 접합
#   설명: heredoc 본문을 지우고 `\`+개행을 이어 붙인 뒤 파싱한다. 커밋 메시지에 적힌 Done 문구가 게이트를 일으키지 않게 한다.
#   관련: hooks/require_test_first.py
# 5 텍스트 매칭으로 대체
#   설명: 토큰화가 불가능하면 정규식 결과를 그대로 대상으로 삼아 게이트를 건다. 놓치는 것보다 더 도는 것이 안전한 쪽이다.
#   개념: fail-closed 폴백
# 6 설정 명령을 셸로 실행
#   설명: coverageCommand는 사용자가 적은 셸 문자열이며 프로젝트 설정을 신뢰한다는 전제다. 스위트 전체를 돌리므로 Done 이동 한 번이 커버리지 한 번의 비용이다.
#   관련: hooks/pre_push_coverage_check.py
# 7 실행 시작 시각을 초로 내림
#   설명: 1초 해상도 mtime에서 같은 초에 쓰인 리포트를 옛 것으로 오판하지 않도록 내린다. 이번 실행이 만든 리포트인지 가르는 기준이다.
#   관련: TASK-62#3
#   개념: mtime 신선도
# 8 종료 코드가 판정
#   설명: 100% 임계값은 도구 설정이 정하고 훅은 종료 코드만 본다. 임계값 미달이면 도구가 non-zero로 끝난다.
#   개념: 종료 코드 게이트
# 9 언어별 리포트 신선도
#   설명: 감지된 언어마다 이번 실행이 만든 리포트가 있어야 한다. 성공 코드만으로는 옛 리포트를 보고 통과하는 허점이 있어서다.
#   관련: TASK-62#3
# 10 Bash는 싼 파싱으로 먼저 거름
#   설명: 대부분의 Bash 호출은 Done 이동이 아니므로 파일 · 서브프로세스 접근 전에 파싱만으로 종료한다. 어느 task ID든 대상이 된다 - 커버리지는 프로젝트 전체의 속성이다.
#   개념: 조기 종료
# 11 backlog 프로젝트가 아니면 통과
#   설명: `.git`과 backlog/config.yml이 있는 프로젝트에만 적용한다. 다른 프로젝트의 Done 명령은 건드리지 않는다.
#   관련: hooks/dedup_drift_guard.py REGISTRY(is_backlog_project)
#   개념: fail-open
# 12 명령이 없을 때의 분기
#   설명: 언어가 감지되면 deny 페이로드를 출력하고, 감지된 언어가 없으면 이전처럼 옵트인으로 조용히 통과한다. 어느 쪽이든 exit 0이고 결정은 JSON이 전달한다.
#   관련: TASK-62
#   개념: 옵트인, 필수 언어
# 13 통과 시 허가 결정을 하지 않음
#   설명: 측정된 리포트만 보여 주고 permissionDecision을 내지 않는다. 이 훅이 다른 훅이나 사용자 설정의 판단을 allow로 덮어쓰지 않게 하려는 결정이다.
# 14 Done 이동 거부
#   설명: 커버리지 미달이면 JSON deny로 Done 전환을 막고 사유와 실제 리포트를 함께 보여 준다.
#   관련: hooks/pre_push_coverage_check.py
