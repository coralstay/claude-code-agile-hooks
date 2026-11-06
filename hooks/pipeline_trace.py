#!/usr/bin/env python3
# ---
# title: pipeline_trace
# description: 플랜 모드부터 승격까지 작업 파이프라인을 세션별로 기록하고 플랜 기록 없는 편집을 경고하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""UserPromptSubmit + PostToolUse + Stop
TASK-32: observe-and-record (never block) the work pipeline
"plan mode -> human review -> auto mode -> draft -> verify -> commit ->
promote -> commit" per session, and warn once at Stop when a session edited
project files without any plan-mode record. Steps 4/6/7 are *enforced* by
require_draft_first.py / backlog_commit_scope.py (TASK-29); this hook only
records them so a session's trace is in one place.

File: $CC_PIPELINE_DIR/<session_id>.json
      (default ~/.claude/hooks-logs/pipeline/<session_id>.json - a sibling
      of TASK-31's flags/ dir, kept separate so this hook and
      context_flags.py never race on the same file at Stop)

Schema (every key optional for readers - treat missing as "not seen"):
  session_id, updated_at
  plan_mode_seen / plan_mode_seen_at  permission_mode == "plan" on any
                        event that carries it, or EnterPlanMode/ExitPlanMode
                        reached PostToolUse
  plan_approved_count / plan_approved_at / last_plan_title
                        PostToolUse(ExitPlanMode). Measured (TASK-32 AC#1):
                        PostToolUse fires only for *approved* ExitPlanMode;
                        rejected ones leave no PostToolUse/Failure record.
                        This is the step-2 "human approved" proxy - recorded,
                        never gated on (DRAFT-8: the signal is not proof).
  draft_create_count / draft_promote_count
                        PostToolUse(Bash) whose command *invokes*
                        `backlog draft create|promote` in command position
  commit_count          PostToolUse(Bash) invoking `git commit` (attempts
                        that reached PostToolUse; success isn't verified)
  project_edit_count / first_project_edit_at
                        PostToolUse(Edit|Write|NotebookEdit) on a path
                        inside cwd (realpath, TASK-27 logic) and outside
                        backlog/ (backlog docs are not implementation)
  edited_before_plan    a project edit happened while no plan was recorded
  warned_at             Stop warning already shown (at most once/session)

The Stop warning only fires in git repos: outside version control there is
no "project" whose history the pipeline protects, and scratch dirs would
just be noise. It is non-blocking (exit 0): JSON `systemMessage` on stdout
(shown to the user) plus the same text on stderr.

Fail-open: any exception exits 0. Writes are atomic (temp + os.replace)
under an fcntl lock so parallel PostToolUse calls don't lose counts.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:
    import fcntl  # ---- 1
except ImportError:  # non-POSIX: record without the file lock
    fcntl = None

SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
EXCLUDED_PREFIXES = ("backlog/",)

WARNING = (
    "[claude-code-agile-hooks] 이 세션은 plan mode/ExitPlanMode 기록 없이 프로젝트 파일을 수정했습니다. "
    "작업 파이프라인(plan mode로 계획 → 유저 검토·승인 → 실행)을 건너뛴 것이라면 "
    "다음 작업부터는 plan mode로 계획을 먼저 보여주세요. (관측 전용 경고 — 차단하지 않음)"
)


def state_dir():
    return os.environ.get("CC_PIPELINE_DIR") or os.path.expanduser(  # ---- 2
        "~/.claude/hooks-logs/pipeline"
    )


def state_path(session_id):
    name = os.path.basename(str(session_id or "")) or "unknown"  # ---- 3
    return os.path.join(state_dir(), f"{name}.json")


def now():
    return datetime.now(timezone.utc).isoformat()


# --- command parsing (tokenize/split_segments/strip_heredoc_bodies are
# registered in dedup_drift_guard.REGISTRY with require_draft_first.py) ---


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


def segments_of(command):
    if not command:
        return []
    try:
        return split_segments(tokenize(strip_heredoc_bodies(command)))
    except ValueError:
        return []  # ---- 4


def backlog_actions(command):
    """{'draft_create', 'draft_promote'} subset that `command` invokes."""
    actions = set()
    for segment in segments_of(command):
        i = command_head(segment)
        if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
            continue
        words = [t for t in segment[i + 1 :] if not t.startswith("-")]
        if len(words) >= 2 and words[0] in ("draft", "drafts"):
            if words[1] == "create":
                actions.add("draft_create")
            elif words[1] == "promote":
                actions.add("draft_promote")
    return actions


def command_runs_git_commit(command):
    for segment in segments_of(command):
        i = command_head(segment)
        if i >= len(segment) or os.path.basename(segment[i]) != "git":
            continue
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
        if j < len(segment) and segment[j] == "commit":
            return True
    return False


# --- paths --------------------------------------------------------------------


def is_outside_project(path, cwd):
    """True if `path` (relative paths resolve against `cwd`) lands outside the
    project root after realpath on both sides, so `..` and symlinks pointing
    back into the project still count as inside. Empty path -> False."""
    if not path or not cwd:
        return False
    root = os.path.realpath(cwd)
    target = os.path.realpath(os.path.join(cwd, path))
    return os.path.commonpath([root, target]) != root


def is_project_edit(tool_input, cwd):
    if not isinstance(tool_input, dict) or not cwd:
        return False
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not isinstance(path, str) or not path or is_outside_project(path, cwd):
        return False
    rel = os.path.relpath(
        os.path.realpath(os.path.join(cwd, path)), os.path.realpath(cwd)
    ).replace(os.sep, "/")
    return not rel.startswith(EXCLUDED_PREFIXES)  # ---- 5


def is_git_repo(cwd):
    if not cwd or not os.path.isdir(cwd):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,  # ---- 6
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


# --- state ----------------------------------------------------------------------


def read_state(session_id):
    try:
        with open(state_path(session_id)) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {}
    return st if isinstance(st, dict) else {}


def write_state(session_id, st):
    path = state_path(session_id)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")  # ---- 7
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # ---- 8
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def has_plan(st):
    return bool(st.get("plan_mode_seen") or st.get("plan_approved_count"))  # ---- 9


def bump(st, key):
    st[key] = int(st.get(key) or 0) + 1


def mark_plan_mode(st):
    if not st.get("plan_mode_seen"):
        st["plan_mode_seen"] = True
        st["plan_mode_seen_at"] = now()


def plan_title(plan):
    if not isinstance(plan, str):
        return None
    for line in plan.splitlines():
        if line.strip():
            return line.strip()[:120]
    return None


def apply_event(st, data):
    """Mutates `st` for one hook event. Returns True if anything changed."""
    changed = False
    if data.get("permission_mode") == "plan" and not st.get("plan_mode_seen"):  # ---- 10
        mark_plan_mode(st)
        changed = True

    if data.get("hook_event_name") != "PostToolUse":
        return changed

    tool = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd", "")

    if tool == "EnterPlanMode":
        mark_plan_mode(st)
        return True
    if tool == "ExitPlanMode":
        mark_plan_mode(st)
        bump(st, "plan_approved_count")
        st["plan_approved_at"] = now()
        if isinstance(tool_input, dict):
            st["last_plan_title"] = plan_title(tool_input.get("plan"))
        return True
    if tool == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command") or ""
        if not isinstance(command, str):
            return changed
        for action in sorted(backlog_actions(command)):
            bump(st, f"{action}_count")
            changed = True
        if command_runs_git_commit(command):
            bump(st, "commit_count")
            changed = True
        return changed
    if tool in EDIT_TOOLS and is_project_edit(tool_input, cwd):
        bump(st, "project_edit_count")
        st.setdefault("first_project_edit_at", now())
        if not has_plan(st):
            st["edited_before_plan"] = True
        return True
    return changed


def stop_warning(st, cwd):
    if st.get("warned_at") or not st.get("project_edit_count") or has_plan(st):  # ---- 11
        return None
    if not is_git_repo(cwd):
        return None
    return WARNING


class StateLock:
    def __init__(self, session_id):
        self.path = state_path(session_id) + ".lock"
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if fcntl is not None:
            self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX)  # ---- 12
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
        return False


def handle(data):
    session_id = data.get("session_id")
    event = data.get("hook_event_name")
    if event not in ("UserPromptSubmit", "PostToolUse", "Stop"):
        return

    if event == "Stop":
        st = read_state(session_id)
        message = stop_warning(st, data.get("cwd", ""))
        if not message:
            return
        with StateLock(session_id):
            st = read_state(session_id)
            st["warned_at"] = now()
            st["session_id"] = session_id or "unknown"
            st["updated_at"] = now()
            write_state(session_id, st)
        print(message, file=sys.stderr)
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
        return

    # Cheap pre-check before touching the filesystem.
    probe = {}
    if not apply_event(probe, data):  # ---- 13
        return
    with StateLock(session_id):
        st = read_state(session_id)  # ---- 14
        apply_event(st, data)
        st["session_id"] = session_id or "unknown"
        st["updated_at"] = now()
        write_state(session_id, st)


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            handle(data)
    except Exception:  # ---- 15
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 POSIX 잠금 선택 의존
#   설명: fcntl이 없는 플랫폼에서는 잠금 없이 기록만 한다. 훅은 관측 전용이라 잠금이 없어도 동작을 멈추지 않는다.
#   개념: fail-open
# 2 기록 위치 결정
#   설명: 환경변수로 바꿀 수 있고 기본은 ~/.claude/hooks-logs/pipeline이다. 플래그 디렉터리(flags/)와 분리해 Stop에서 서로 같은 파일을 두고 경쟁하지 않게 했다.
#   관련: hooks/context_flags.py, TASK-31
#   개념: 경쟁 조건 회피
# 3 세션 ID 경로 정화
#   설명: 세션 ID가 `../x` 같은 값이어도 basename만 써서 기록 디렉터리 밖에 파일을 만들지 못하게 한다. 비어 있으면 unknown으로 모은다.
#   개념: 경로 탈출 방지
# 4 파싱 실패는 빈 결과
#   설명: 따옴표가 불균형인 명령은 기록에서 조용히 제외한다. 이 훅은 관측 전용이라 오탐으로 세는 것보다 누락이 낫다.
#   개념: fail-open
# 5 backlog 문서는 구현이 아님
#   설명: backlog/ 아래 편집은 계획 없이 한 구현으로 세지 않는다. 카드 작성 자체가 경고를 일으키지 않게 한다.
#   관련: TASK-32
# 6 git 호출 타임아웃
#   설명: Stop 훅이 git 때문에 멈추지 않도록 5초로 제한한다. 시간 초과는 OSError 계열 예외로 처리되어 git 저장소가 아니라고 본다.
#   개념: fail-open
# 7 원자적 쓰기의 시작
#   설명: 같은 디렉터리에 임시 파일을 만들어 쓴 뒤 교체한다. 읽는 쪽이 쓰다 만 JSON을 보는 일이 없게 한다.
#   개념: 원자적 갱신
# 8 교체는 원자적
#   설명: 같은 파일시스템 안의 os.replace는 원자적이다. 예외가 나면 임시 파일을 지우고 다시 던져 찌꺼기를 남기지 않는다.
#   개념: 원자적 갱신
# 9 계획 기록의 정의
#   설명: plan mode를 봤거나 ExitPlanMode 승인이 하나라도 있으면 계획이 있다고 본다. 승인 신호는 증거가 아니라 대리 지표라 기록만 하고 차단에 쓰지 않는다.
#   관련: TASK-32, DRAFT-8
#   개념: 대리 지표
# 10 plan mode 감지
#   설명: permission_mode가 실린 모든 이벤트에서 plan을 본다. PostToolUse가 승인된 ExitPlanMode에서만 발생하므로 이 신호가 plan mode 진입의 유일한 단서일 때가 있다.
#   관련: TASK-32
# 11 경고는 세션당 한 번
#   설명: 이미 경고했거나, 편집이 없거나, 계획이 있으면 경고하지 않는다. 같은 세션에서 Stop마다 반복되는 잡음을 막는다.
# 12 동시 PostToolUse의 카운트 손실 방지
#   설명: 병렬 도구 호출이 같은 상태 파일을 읽고 쓰면 카운트가 덮어써진다. 배타 잠금으로 읽기-수정-쓰기를 직렬화한다.
#   관련: TASK-32
#   개념: flock, 읽기-수정-쓰기
# 13 잠금 전 사전 검사
#   설명: 빈 상태에 이벤트를 적용해 보아 기록할 게 없으면 잠금과 파일 입출력 없이 끝낸다. 대부분의 PostToolUse는 기록 대상이 아니다.
#   개념: 조기 종료
# 14 잠금 안에서 다시 읽기
#   설명: 사전 검사 이후 다른 호출이 상태를 바꿨을 수 있으므로 잠금을 잡은 뒤 최신 상태를 다시 읽는다.
#   개념: 읽기-수정-쓰기
# 15 모든 예외를 삼키는 fail-open
#   설명: 이 훅은 관측 전용이라 어떤 오류도 사용자의 작업을 막아서는 안 된다. 어떤 경우에도 exit 0이다.
#   관련: TASK-32
#   개념: fail-open
