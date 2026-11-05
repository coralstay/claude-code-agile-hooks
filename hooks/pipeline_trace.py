#!/usr/bin/env python3
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
    import fcntl
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
    return os.environ.get("CC_PIPELINE_DIR") or os.path.expanduser(
        "~/.claude/hooks-logs/pipeline"
    )


def state_path(session_id):
    name = os.path.basename(str(session_id or "")) or "unknown"
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
        return []


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
    return not rel.startswith(EXCLUDED_PREFIXES)


def is_git_repo(cwd):
    if not cwd or not os.path.isdir(cwd):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
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
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def has_plan(st):
    return bool(st.get("plan_mode_seen") or st.get("plan_approved_count"))


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
    if data.get("permission_mode") == "plan" and not st.get("plan_mode_seen"):
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
    if st.get("warned_at") or not st.get("project_edit_count") or has_plan(st):
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
            fcntl.flock(self.fd, fcntl.LOCK_EX)
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
    if not apply_event(probe, data):
        return
    with StateLock(session_id):
        st = read_state(session_id)
        apply_event(st, data)
        st["session_id"] = session_id or "unknown"
        st["updated_at"] = now()
        write_state(session_id, st)


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            handle(data)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
