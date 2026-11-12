#!/usr/bin/env python3
# ---
# title: pre_push_coverage_check
# description: push 전에 설정된 커버리지 명령을 돌려 실제 리포트를 보이고 실패하면 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
Coverage gate (opt-in, and mandatory for detected languages since TASK-62 -
see below): if the project's .claude-code-agile-hooks.json (or the legacy
.claude-rails.json, see project_config_path()) configures a
`coverageCommand` (e.g. "python3 -m pytest --cov=. --cov-fail-under=100"),
run it before every push and show the real, measured report - every time,
pass or fail. Blocks the push only when the command itself fails (e.g.
coverage.py's own --cov-fail-under exits non-zero below the threshold).
Never fabricates a percentage; a project with no coverageCommand configured
gets no message at all. Every attempt (pass or fail) is also appended to
<cwd>/.claude-code-agile-hooks/coverage-log.jsonl (legacy projects: .claude-rails/, see
log_path()) so there's a permanent record beyond
the transcript, which scrolls away.

TASK-62: the gate is mandatory for the five languages it detects by their
manifest at the project root (package.json -> javascript, tsconfig.json ->
typescript, pom.xml / build.gradle(.kts) -> java, pyproject.toml /
setup.cfg / pytest.ini -> python, CMakeLists.txt -> cpp):
- a language detected and no coverageCommand -> the push is denied;
- no language detected -> opt-in exactly as before (no config, no message;
  with a coverageCommand only its exit code counts).
After a successful run every detected language must have a report written
by this run (mtime at or after the run start, floored to the second) in
its report location - coverage/ for javascript, typescript and cpp;
target/site/jacoco/ or build/reports/jacoco/ for java; htmlcov/ or
coverage.xml for python - else the push is denied. `coverageReportDir`
overrides the location: a path string for every language, or a
{"<language>": "<path>"} map (unnamed languages keep their defaults); a
malformed value denies without running the command. The 100% (line +
branch) threshold itself lives in the tool's config; this hook judges the
exit code. require_coverage_on_done.py runs the same gate on
`backlog task edit <ID> -s Done`.

This script does its own subcommand detection so `git -C <path> push`
(flags before the subcommand) is still recognized as a push, not just
`git push`.

TASK-39: only a `git push` in *command position* counts, found the way
pre_push_check.py (TASK-34) finds it - heredoc bodies dropped, the line
split into shell segments, env assignments/wrappers skipped, git compared
by basename and its global flags skipped. `echo git push`, quoted text and
heredoc bodies no longer run the coverage command. If the line can't be
tokenized, any `push` substring counts as a push (conservative, like
TASK-34: an extra coverage run costs time, a skipped one lets an
under-covered push through).

TASK-46: registered without `if: Bash(git *)` (TASK-39 had kept it). The
filter matches the command text per subcommand (measured 2026-10-04), so
`/usr/bin/git push` or `FOO=1 git push` skipped this report - and when the
coverage command fails this hook denies the push, so it acts as a gate for
projects that opt in. Same registration as pre_push_check.py for
consistency; the cost is one short python process per Bash call, and a
line without a push exits right after parsing, before reading the config
or starting any subprocess. hooks/test_hook_registration_contract.py keeps
the registration and this detection in agreement.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone

TAG = "[claude-code-agile-hooks]"
FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")


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


def git_subcommand_index(segment):
    """Index of the git subcommand in `segment` when the segment runs git
    in command position (basename compare, git's global flags skipped),
    else None."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) != "git":
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
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 1
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return subcommand in stripped  # ---- 2
    for segment in split_segments(tokens):
        j = git_subcommand_index(segment)
        if j is not None and segment[j] == subcommand:
            return True
    return False


def project_config_path(cwd):
    """TASK-54: the project config was renamed from .claude-rails.json to
    .claude-code-agile-hooks.json. Prefer the new name and fall back to the legacy one so
    projects can rename at their own pace; None when neither exists."""
    for name in (".claude-code-agile-hooks.json", ".claude-rails.json"):  # ---- 3
        path = os.path.join(cwd, name)
        if os.path.isfile(path):
            return path
    return None


def configured_coverage_command(cwd):
    config_path = project_config_path(cwd)
    if config_path is None:
        return None
    with open(config_path) as f:
        config = json.load(f)  # ---- 4
    return config.get("coverageCommand") or None


# --- TASK-62: languages and their coverage reports (the data lives inside
# the functions so a dedup REGISTRY AST comparison covers it too) ---


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
    raise ValueError(  # ---- 5
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
    since = int(time.time())  # ---- 6
    exit_code, output = run_shell(cwd, command)
    if exit_code != 0:  # ---- 7
        return exit_code, output, f"커버리지 기준 미달 (exit {exit_code})"
    missing = [
        f"{lang}: {' 또는 '.join(candidates)}"
        for lang, candidates in paths.items()
        if not any(fresh_report(cwd, p, since) for p in candidates)
    ]
    if missing:
        return exit_code, output, (
            "coverageCommand는 성공했지만 이번 실행이 만든 커버리지 리포트가 없습니다 - "
            + "; ".join(missing)
            + " (위치는 coverageReportDir로 바꿀 수 있습니다)"
        )
    return exit_code, output, None


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


def current_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_id_from_branch(branch):
    """Extract "TASK-7" from "task/TASK-7", or None for branches that don't
    follow that convention (main, feature branches from other workflows,
    etc.)."""
    prefix = "task/"
    if branch.startswith(prefix):
        return branch[len(prefix) :]
    return None


def run_shell(cwd, command):
    result = subprocess.run(
        command, cwd=cwd, shell=True, capture_output=True, text=True  # ---- 8
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def log_path(cwd):
    """TASK-54: the log dir follows the config rename. Keep writing to the
    legacy .claude-rails/ only while the project still uses only the legacy
    .claude-rails.json and has no .claude-code-agile-hooks/ yet; otherwise .claude-code-agile-hooks/."""
    legacy_only = project_config_path(cwd) == os.path.join(  # ---- 9
        cwd, ".claude-rails.json"
    ) and not os.path.isdir(os.path.join(cwd, ".claude-code-agile-hooks"))
    log_dir = ".claude-rails" if legacy_only else ".claude-code-agile-hooks"
    return os.path.join(cwd, log_dir, "coverage-log.jsonl")


def append_log(cwd, record):
    path = log_path(cwd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    bash_command = (data.get("tool_input") or {}).get("command", "")

    if not command_runs_git(bash_command, "push"):  # ---- 10
        sys.exit(0)

    command = configured_coverage_command(cwd)
    if not command:
        languages = detect_languages(cwd)
        if not languages:
            sys.exit(0)
        # TASK-62: a detected language makes the coverage gate mandatory
        print(json.dumps(missing_command_payload(languages)))  # ---- 11
        sys.exit(0)

    languages = detect_languages(cwd)
    exit_code, output, problem = coverage_verdict(
        cwd, command, languages, configured_report_dir(cwd)
    )
    passed = problem is None

    branch = current_branch(cwd)

    append_log(
        cwd,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": data.get("session_id"),
            "project": os.path.basename(os.path.normpath(cwd)) if cwd else None,
            "branch": branch or None,
            "task_id": task_id_from_branch(branch),
            "command": command,
            "languages": languages,
            "exit_code": exit_code,
            "passed": passed,
            "problem": problem,
            "output": output[-4000:],  # ---- 12
        },
    )

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if passed else "deny",  # ---- 13
            "permissionDecisionReason": (
                "커버리지 기준 통과" if passed else f"{TAG} {problem}"
            ),
            "systemMessage": (
                f"{TAG} 커버리지 리포트 ('{command}', exit {exit_code}):\n"
                + output[-4000:]
            ),
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 명령 위치의 git push만 인정
#   설명: heredoc 본문을 지우고 백슬래시 개행을 이어 붙인 뒤 세그먼트별로 본다. `echo git push`나 커밋 메시지에 적힌 문구가 커버리지 실행을 일으키지 않게 한다.
#   관련: TASK-39
# 2 토큰화 실패 시 push로 간주
#   설명: 따옴표가 불균형이면 push 문자열만 있어도 push로 본다. 커버리지를 한 번 더 도는 비용보다 미달 상태 push가 통과하는 비용이 크다는 보수적 결정이다.
#   관련: TASK-34
#   개념: fail-closed 폴백
# 3 설정 파일 이름 마이그레이션
#   설명: 새 이름을 우선하고 옛 `.claude-rails.json`으로 폴백해 프로젝트가 각자 속도로 이름을 바꾸게 한다. 로그 디렉터리 이름도 이 결과를 따른다.
#   관련: TASK-54, hooks/dedup_drift_guard.py REGISTRY(project_config_path)
# 4 설정 JSON 오류는 잡지 않는다
#   설명: 깨진 설정이면 예외로 훅이 비정상 종료한다(차단 코드가 아니라 비차단 오류). 조용히 게이트를 끄지 않고 오류를 드러내는 쪽이지만 push는 막지 못한다는 한계가 있다.
#   개념: fail-open 한계
# 5 coverageReportDir 형식 오류
#   설명: 경로 문자열이나 `{언어: 경로}` 맵이 아니면 명령을 돌리지 않고 거부한다. 잘못된 위치를 보고 있으면 어떤 리포트도 신선도를 증명할 수 없기 때문이다.
#   관련: TASK-62#3
# 6 실행 시작 시각을 초로 내림
#   설명: mtime 해상도가 1초인 파일시스템에서 같은 초에 쓰인 리포트가 `since`보다 이르다고 오판되지 않도록 내린다. 옛 리포트와 이번 실행의 리포트를 구분하는 기준점이다.
#   관련: TASK-62#3
#   개념: mtime 신선도
# 7 종료 코드가 판정
#   설명: 100%(line+branch) 임계값은 도구 설정에 있고 훅은 종료 코드만 본다. 퍼센트를 훅이 계산하거나 지어내지 않는다.
#   개념: 종료 코드 게이트
# 8 설정 명령을 셸로 실행
#   설명: coverageCommand는 사용자가 적은 셸 문자열이라 shell=True로 돌린다. 프로젝트 설정을 신뢰한다는 전제이며, 출력은 stdout과 stderr를 합쳐 리포트로 보인다.
#   개념: 외부 명령 실행
# 9 로그 디렉터리 이름 규칙
#   설명: 옛 설정 파일만 쓰고 새 디렉터리가 아직 없을 때만 `.claude-rails/`에 계속 쓴다. 그 외에는 새 이름이라 기록이 두 곳으로 갈라지지 않는다.
#   관련: TASK-54
# 10 push가 아니면 설정 읽기 전에 종료
#   설명: 모든 Bash 호출에 붙는 훅이라 파싱만 하고 바로 나간다. 설정 읽기와 서브프로세스는 push일 때만 일어난다.
#   관련: TASK-46
# 11 감지된 언어는 커버리지 필수
#   설명: 명령이 없으면 deny 페이로드를 출력하고 exit 0으로 끝낸다. 결정은 JSON의 permissionDecision이 전달하며 종료 코드는 차단 수단이 아니다.
#   관련: TASK-62
#   개념: JSON deny
# 12 출력은 뒤 4000자만
#   설명: 커버리지 리포트는 끝에 요약이 있어 꼬리를 남기면 충분하다. 로그 파일이 푸시마다 무한히 커지는 것도 막는다.
# 13 통과해도 리포트를 보인다
#   설명: 통과든 실패든 측정된 실제 리포트를 systemMessage로 보여 준다. allow를 명시해 이 훅이 다른 훅의 deny를 덮지 않는 범위에서만 통과시킨다.
