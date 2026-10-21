#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-58: no promotion or start without an implementation plan.

`backlog draft promote <ID>` in command position: the draft card
(backlog/drafts/) must have a non-empty Implementation Plan section
(between `<!-- SECTION:PLAN:BEGIN -->` and `<!-- SECTION:PLAN:END -->`),
else deny and point at `backlog draft edit <ID> --plan`.

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


def segment_gate(segment):
    """("promote", ID) for `backlog draft promote <ID>` in command position,
    else None."""
    i = command_head(segment)
    if i >= len(segment) or os.path.basename(segment[i]) not in BACKLOG_EXECUTABLES:
        return None
    words = [t for t in segment[i + 1 :] if not t.startswith("-")]
    if len(words) >= 3 and words[0] in ("draft", "drafts") and words[1] == "promote":
        return ("promote", words[2])
    return None


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


def check_promote(cwd, token):
    found = find_card(cwd, "drafts", token)
    if found is None:
        return
    card_id, text = found
    plan = plan_text(text)
    if plan is None or not plan.strip():
        deny(
            f"{TAG} {card_id}에 구현 계획(Implementation Plan)이 없어 승격할 수 "
            f"없습니다. 먼저 'backlog draft edit {card_id} --plan \"...\"'로 "
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
        check_promote(cwd, token)
    sys.exit(0)


if __name__ == "__main__":
    main()
