#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-58: no promotion or start without an implementation plan.

`backlog draft promote <ID>` in command position: the draft card
(backlog/drafts/) must have a non-empty Implementation Plan section
(between `<!-- SECTION:PLAN:BEGIN -->` and `<!-- SECTION:PLAN:END -->`),
else deny and point at `backlog draft edit <ID> --plan`.

`backlog task edit <ID> ... -s "In Progress"` (`--status`, `--status=`,
any case) in command position: the task card (backlog/tasks/) gets the
same check. This is the second line of defense for cards made through the
backlog MCP server or web UI, which never pass `draft promote`.

Cards are read straight from the files (frontmatter `id:`), so the
backlog CLI is not needed; `TASK-58`, `task-58` and `58` all name TASK-58.
An ID with no card file passes - backlog itself reports the error.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

TAG = "[claude-code-agile-hooks]"
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ID_RE = re.compile(r"^id:\s*['\"]?([^'\"\s]+)['\"]?\s*$", re.MULTILINE)
PLAN_RE = re.compile(
    r"<!-- SECTION:PLAN:BEGIN -->\n?(.*?)<!-- SECTION:PLAN:END -->", re.DOTALL
)


def is_backlog_project(cwd):
    if not cwd:
        return False
    return os.path.isdir(os.path.join(cwd, ".git")) and os.path.isfile(
        os.path.join(cwd, "backlog", "config.yml")
    )


# --- command parsing (strip_heredoc_bodies/tokenize/split_segments/
# command_head are registered in dedup_drift_guard.REGISTRY) ---


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


def start_target(rest):
    """The task argument of `task edit <ID> ... -s "In Progress"` (`rest`
    starts at `task`), else None."""
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
    if target is None or status is None or not is_in_progress(status):
        return None
    return target


def is_in_progress(status):
    return " ".join(status.split()).lower() == "in progress"


def segment_gate(segment):
    """("promote", ID) for `backlog draft promote <ID>` and ("start", ID)
    for `backlog task edit <ID> ... -s "In Progress"` in command position,
    else None."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
        return None
    rest = segment[i + 1 :]
    words = [t for t in rest if not t.startswith("-")]
    if len(words) >= 3 and words[0] in ("draft", "drafts") and words[1] == "promote":
        return ("promote", words[2])
    target = start_target(rest)
    return ("start", target) if target is not None else None


def gated_commands(command):
    """(kind, ID) for every gated backlog command in command position."""
    if not command:
        return []
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")
    tokens = tokenize(stripped)
    gates = [segment_gate(s) for s in split_segments(tokens)]
    return [g for g in gates if g is not None]


# --- card files ---


def same_id(token, card_id):
    """`DRAFT-8`, `draft-8` and `8` all name DRAFT-8."""
    if token.upper() == card_id.upper():
        return True
    return token.isdigit() and card_id.rsplit("-", 1)[-1] == token


def find_card(cwd, folder, token):
    """(card id, text) of the card in backlog/<folder>/ named by `token`,
    or None."""
    directory = os.path.join(cwd, "backlog", folder)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".md"):
            continue
        try:
            with open(os.path.join(directory, name), errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        m = ID_RE.search(text.split("\n---", 1)[0])
        if m and same_id(token, m.group(1)):
            return m.group(1), text
    return None


def plan_text(text):
    """Body of the Implementation Plan section, or None when absent."""
    m = PLAN_RE.search(text)
    return m.group(1) if m else None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def check_card(cwd, kind, token):
    folder, edit = ("drafts", "draft") if kind == "promote" else ("tasks", "task")
    found = find_card(cwd, folder, token)
    if found is None:
        return
    card_id, text = found
    action = "승격할" if kind == "promote" else "In Progress로 옮길"
    plan = plan_text(text)
    if plan is None or not plan.strip():
        deny(
            f"{TAG} {card_id}에 구현 계획(Implementation Plan)이 없어 {action} 수 "
            f"없습니다. 먼저 'backlog {edit} edit {card_id} --plan \"...\"'로 "
            "계획을 적으세요."
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "")
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)
    gates = gated_commands(tool_input.get("command") or "")
    if not gates or not is_backlog_project(cwd):
        sys.exit(0)
    for kind, token in gates:
        check_card(cwd, kind, token)
    sys.exit(0)


if __name__ == "__main__":
    main()
