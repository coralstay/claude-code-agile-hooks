#!/usr/bin/env python3
# ---
# title: require_coverage_on_done
# description: 태스크를 Done으로 옮길 때도 커버리지 게이트를 돌리는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
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
project (`.git` + `backlog/config.yml` at the git top-level of the directory
the command aims at - TASK-75: an earlier `cd <dir>` or `BACKLOG_CWD=<dir>`
on the line, else the session cwd; an aim that can't be known statically is
denied, exit 2). Any task ID counts: coverage
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


def project_root(path):
    """TASK-75 B1: the git top-level holding `path` (a directory or a file,
    existing or not) - the nearest of `path` and its parents with a `.git`
    entry, a directory or (linked worktree, submodule) a file. None outside
    any repository or for an empty path. Walks the logical path (no
    realpath) and runs no subprocess."""
    if not path:
        return None
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_backlog_project(cwd):
    """TASK-75 B1: True if `cwd` lies in a git repository (judged at its
    top-level, project_root) with backlog/config.yml - so a subdirectory
    or a linked worktree of a backlog project is that project too."""
    root = project_root(cwd)
    return root is not None and os.path.isfile(
        os.path.join(root, "backlog", "config.yml")
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


def command_target_dir(command, cwd):
    """TASK-75 B2/B4/B6: [(segment, directory)] for every shell segment of
    `command` (the segments split_segments gives, after heredoc bodies are
    dropped and `\\`-newline continuations joined). `directory` is the one
    the segment acts on: the session `cwd`, moved by the earlier
    `cd`/`pushd <dir>` of the same line (relative to the directory before
    it), then for git its `-C <dir>` options in order, and for backlog a
    `BACKLOG_CWD=<dir>` in front of it (also behind `env`) or exported
    earlier on the line (relative to the segment's directory).

    A cd counts only where bash keeps it: not inside `( )` or `$( )` once
    they close, not in a pipeline (`cd x | ...`), not in a list sent to the
    background (`... &`).

    `directory` is None when it can't be known statically: a path with
    `$`, a backtick, a glob or `{` (`cd "$X"`, `cd $(...)`), `cd -`,
    `popd`, `pushd` without a directory, a cd with more than one argument,
    a relative cd while CDPATH is set, a directory that doesn't exist, a cd
    that may not have run (after `||` or a shell keyword such as `then`; a
    cd behind `&&` once its `&&` chain ends; any cd once an `||` other than
    `|| exit` / `|| return` follows it), a bare `BACKLOG_CWD=...` assignment
    (exported or not is unknown), and git with `--git-dir`, `--work-tree`,
    `GIT_DIR=` or `GIT_WORK_TREE=`. A line that can't be tokenized gives
    [(None, cwd)], or [(None, None)] when its text mentions a directory
    changer."""

    def resolve(base, path):
        if path is None:
            return None
        if path.startswith("~"):
            path = os.path.expanduser(path)
        if not path or path.startswith("~") or any(c in path for c in "$`*?[{"):
            return None
        if not os.path.isabs(path):
            if not base:
                return None
            path = os.path.join(base, path)
        path = os.path.normpath(path)
        return path if os.path.isdir(path) else None

    def operands(args):
        words = []
        i = 0
        while i < len(args):
            tok = args[i]
            if tok and set(tok) <= set("<>&"):
                if words and words[-1].isdigit():
                    words.pop()
                i += 2
                continue
            words.append(tok)
            i += 1
        return words

    def cd_target(name, args, base):
        words = operands(args)
        while words and words[0].startswith("-") and words[0] != "-":
            if words.pop(0) == "--":
                break
        if name == "popd" or len(words) > 1:
            return None
        if not words:
            return None if name == "pushd" else resolve(None, os.path.expanduser("~"))
        word = words[0]
        if word == "-" or (name == "pushd" and word[:1] in ("+", "-")):
            return None
        word = os.path.expanduser(word)
        if os.environ.get("CDPATH") and word.split("/")[0] not in ("", ".", ".."):
            return None
        return resolve(base, word)

    stripped = strip_heredoc_bodies(command or "").replace("\\\n", "")
    try:
        tokens = tokenize(stripped)
    except ValueError:
        changer = re.search(
            r"\b(?:cd|pushd|popd)\b|(?:^|\s)-C\b|--git-dir|--work-tree"
            r"|GIT_DIR|GIT_WORK_TREE|BACKLOG_CWD",
            stripped,
        )
        return [(None, None if changer else cwd)]

    def operator(run):
        if "||" in run:
            return ("op", "or")
        if "&&" in run:
            return ("op", "and")
        if "|" in run:
            return ("op", "pipe")
        if "&" in run:
            return ("op", "bg")
        return ("op", "seq")

    # a separator token can hold several operators and parens (`)&&(`)
    events = []
    current = []
    for tok in tokens:
        if not (tok and set(tok) <= set(";&|()\n")):
            current.append(tok)
            continue
        if current:
            events.append(("segment", current))
            current = []
        for part in re.findall(r"[()]|[^()]+", tok):
            events.append(("paren", part) if part in "()" else operator(part))
    if current:
        events.append(("segment", current))

    keywords = {"if", "then", "else", "elif", "do", "while", "until"}
    directory, backlog_cwd, git_env = cwd, "", False
    snapshot = (directory, backlog_cwd, git_env)
    fragile = None
    previous = "seq"
    stack = []
    pairs = []
    for index, (kind, value) in enumerate(events):
        following = events[index + 1] if index + 1 < len(events) else ("op", "seq")
        if kind == "paren":
            if value == "(":
                stack.append((directory, backlog_cwd, git_env, snapshot, fragile))
                snapshot = (directory, backlog_cwd, git_env)
                fragile = None
                previous = "seq"
            elif stack:
                directory, backlog_cwd, git_env, snapshot, fragile = stack.pop()
            continue
        if kind == "op":
            if value == "or" and fragile is not None:
                nxt = following[1] if following[0] == "segment" else []
                head = command_head(nxt)
                if head >= len(nxt) or nxt[head] not in ("exit", "return"):
                    directory = None
            elif value == "seq":
                if fragile == "end":
                    directory = None
                fragile = None
                snapshot = (directory, backlog_cwd, git_env)
            elif value == "bg":
                directory, backlog_cwd, git_env = snapshot
                fragile = None
            previous = value
            continue

        segment = value
        start = 0
        while start < len(segment) and segment[start] in keywords:
            start += 1
        head = start + command_head(segment[start:])
        name = segment[head] if head < len(segment) else ""
        target = directory
        if os.path.basename(name) == "git":
            if git_env or any(
                t.startswith(("GIT_DIR=", "GIT_WORK_TREE=")) for t in segment[:head]
            ):
                target = None
            j = head + 1
            while target is not None and j < len(segment):
                tok = segment[j]
                if tok == "-C":
                    target = resolve(target, segment[j + 1] if j + 1 < len(segment) else None)
                    j += 2
                elif tok in ("--git-dir", "--work-tree") or tok.startswith(
                    ("--git-dir=", "--work-tree=")
                ):
                    target = None
                elif tok in ("-c", "--namespace"):
                    j += 2
                elif tok.startswith("-"):
                    j += 1
                else:
                    break
        elif os.path.basename(name) in ("backlog", "backlog.md"):
            env_value = backlog_cwd
            for tok in segment[:head]:
                if tok.startswith("BACKLOG_CWD="):
                    env_value = tok[len("BACKLOG_CWD=") :]
            if env_value is None:
                target = None
            elif env_value:
                target = resolve(target, env_value)
        pairs.append((segment, target))

        if previous == "pipe" or following == ("op", "pipe"):
            continue
        conditional = start > 0 or previous in ("and", "or")
        if name in ("cd", "pushd", "popd"):
            if start > 0 or previous == "or":
                directory = None
            else:
                directory = cd_target(name, segment[head + 1 :], directory)
                fragile = "end" if previous == "and" else "or"
        elif name in ("export", "unset") or head == len(segment):
            for tok in segment[start:]:
                key, eq, val = tok.partition("=")
                if key == "BACKLOG_CWD":
                    if name == "unset":
                        backlog_cwd = ""
                    elif conditional or name != "export" or not eq:
                        backlog_cwd = None
                    else:
                        backlog_cwd = val
                elif key in ("GIT_DIR", "GIT_WORK_TREE") and name != "unset":
                    git_env = True
    return pairs


def target_roots(command, cwd, match, fallback):
    """TASK-75: [(root, [results])] - the gated segments of `command`
    (`match(segment)` is not None) grouped by the git top-level of the
    directory each one targets (command_target_dir), in first-seen order.
    A target that isn't a backlog project is dropped, whatever the session
    cwd is (B7). A gated segment whose directory can't be known statically
    is denied (B6). An untokenizable line counts the hook's own text-match
    results (`fallback`) against its single pseudo-segment."""
    groups = []
    for segment, directory in command_target_dir(command, cwd):
        if segment is None:
            found = list(fallback)
        else:
            value = match(segment)
            found = [] if value is None else [value]
        if not found:
            continue
        if directory is None:
            deny(
                "[claude-code-agile-hooks] 이 명령이 어느 저장소를 겨누는지 정적으로 알 수 "
                '없어 거부합니다(cd "$X" · cd $(...) · cd - · git -C "$D" · '
                "BACKLOG_CWD=$Y · 없는 디렉터리 · || 뒤나 조건부 cd 등). 대상 디렉터리를 "
                "리터럴 경로로 적거나(cd /path/to/repo && ...), 그 저장소에서 명령을 "
                "따로 실행하세요."
            )
        root = project_root(directory) or directory
        if not is_backlog_project(root):
            continue
        for known, values in groups:
            if known == root:
                values.extend(found)
                break
        else:
            groups.append((root, found))
    return groups


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") != "Bash" or not isinstance(tool_input, dict):
        sys.exit(0)
    # cheap parse first: most Bash lines leave before any file or subprocess
    command = tool_input.get("command") or ""
    targets = done_targets(command)
    if not targets:  # ---- 10
        sys.exit(0)
    cwd = data.get("cwd", "")
    roots = target_roots(command, cwd, segment_done_target, targets)  # ---- 11
    payloads = [p for p in (repo_payload(root) for root, _ in roots) if p is not None]
    denials = [p for p in payloads if "hookSpecificOutput" in p]
    if payloads:
        print(json.dumps((denials or payloads)[0]))  # ---- 12
    sys.exit(0)


def repo_payload(root):
    """The PreToolUse output for a Done move in the project at `root`: a
    deny decision, a pass report, or None (nothing to say)."""
    command = configured_coverage_command(root)
    languages = detect_languages(root)
    if not command:  # ---- 13
        return missing_command_payload(languages) if languages else None

    exit_code, output, problem = coverage_verdict(
        root, command, languages, configured_report_dir(root)
    )
    report = f"{TAG} 커버리지 리포트 ('{command}', exit {exit_code}):\n" + output[-4000:]
    if problem is None:
        # pass: show the measured report, leave the permission decision alone
        return {"systemMessage": report}  # ---- 14
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",  # ---- 15
            "permissionDecisionReason": (
                f"{TAG} -s Done 전에 커버리지 게이트를 통과해야 합니다: "
                f"{problem}\n" + report
            ),
        }
    }


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
# 11 대상이 backlog 프로젝트가 아니면 통과
#   설명: 같은 줄의 앞선 cd와 BACKLOG_CWD로 Done 이동이 겨누는 디렉터리를 정하고, 그 git top-level이 backlog 프로젝트일 때만 그 저장소의 coverageCommand로 판정한다. 다른 프로젝트의 Done 명령은 세션 cwd와 무관하게 건드리지 않고, 대상을 정적으로 알 수 없으면 target_roots가 거부한다(exit 2).
#   관련: TASK-75 (B3 · B4 · B6 · B7), hooks/dedup_drift_guard.py REGISTRY(is_backlog_project · command_target_dir · target_roots)
#   개념: fail-open, 대상 저장소
# 12 출력은 한 번만
#   설명: 한 줄이 여러 프로젝트의 Done을 겨누면 저장소마다 판정하고, stdout JSON은 하나뿐이어야 하므로 거부가 있으면 첫 거부를, 없으면 첫 리포트를 낸다.
#   관련: TASK-75
# 13 명령이 없을 때의 분기
#   설명: 언어가 감지되면 deny 페이로드를 출력하고, 감지된 언어가 없으면 이전처럼 옵트인으로 조용히 통과한다. 어느 쪽이든 exit 0이고 결정은 JSON이 전달한다.
#   관련: TASK-62
#   개념: 옵트인, 필수 언어
# 14 통과 시 허가 결정을 하지 않음
#   설명: 측정된 리포트만 보여 주고 permissionDecision을 내지 않는다. 이 훅이 다른 훅이나 사용자 설정의 판단을 allow로 덮어쓰지 않게 하려는 결정이다.
# 15 Done 이동 거부
#   설명: 커버리지 미달이면 JSON deny로 Done 전환을 막고 사유와 실제 리포트를 함께 보여 준다.
#   관련: hooks/pre_push_coverage_check.py
