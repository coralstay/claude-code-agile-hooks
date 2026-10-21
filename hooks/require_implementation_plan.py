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
The plan must hold the SOAP reserved headings `### Subjective`,
`### Objective`, `### Assessment`, `### Plan` - exactly these lines (case,
spacing and heading level are not normalized; trailing whitespace is
ignored), in this order, once each, each followed by a non-blank body up
to the next reserved heading. Otherwise deny listing the missing, repeated,
out-of-order and empty headings. Text before the first heading is allowed.

The card must also have at least one acceptance criterion and one
Definition of Done item (`- [ ] #n` / `- [x] #n` lines inside the
`<!-- AC:... -->` / `<!-- DOD:... -->` blocks). All problems of a card are
reported in one deny, each with the `edit --plan/--ac/--dod` to fix it.

`-s "In Progress"` also needs Plan-Review-Go (decision-13): after a human
reviewed the plan they record the go as an empty signed commit
`git commit --allow-empty -S -m "Go: <ID>"`. The hook searches the commits
reachable from HEAD (`git log HEAD`; other branches don't count, so a go
on an unmerged branch is not seen until it is merged) for a subject that is
exactly `Go: <ID>` with the card's own ID, and requires
`git log --format=%G?` to be `G` (valid signature) for at least one of
them. The signer's identity is not checked, and neither is the emptiness
of the commit. The hook never creates a go commit. For SSH signing, `G`
needs `gpg.ssh.allowedSignersFile` to list the key.

An ID with no card file passes - backlog itself reports the error.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys

TAG = "[claude-code-agile-hooks]"
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
BACKLOG_EXECUTABLES = {"backlog", "backlog.md"}
ID_RE = re.compile(r"^id:\s*['\"]?([^'\"\s]+)['\"]?\s*$", re.MULTILINE)
SOAP_HEADINGS = ("### Subjective", "### Objective", "### Assessment", "### Plan")
SOAP_TEMPLATE = (
    "형식:\n"
    "### Subjective\n<요청 · 배경>\n\n"
    "### Objective\n<확인한 사실>\n\n"
    "### Assessment\n<판단 · 고른 접근>\n\n"
    "### Plan\n<구현 순서>"
)
ITEM_RE = re.compile(r"^- \[[ xX]\] #\d+", re.MULTILINE)
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


def has_items(text, marker):
    """True if the card's `<!-- <marker>:BEGIN -->` block (AC or DOD) holds
    at least one `- [ ] #n` / `- [x] #n` item."""
    m = re.search(
        rf"<!-- {marker}:BEGIN -->(.*?)<!-- {marker}:END -->", text, re.DOTALL
    )
    return bool(m and ITEM_RE.search(m.group(1)))


def soap_problems(plan):
    """What is wrong with the SOAP structure of `plan`, as message lines
    (empty list = well formed). A heading is a line that is exactly one of
    SOAP_HEADINGS (trailing whitespace ignored); its body runs to the next
    such line. Text before the first heading is allowed."""
    found = []  # (heading, body lines)
    for line in plan.split("\n"):
        if line.rstrip() in SOAP_HEADINGS:
            found.append((line.rstrip(), []))
        elif found:
            found[-1][1].append(line)
    names = [h for h, _ in found]
    problems = []
    missing = [h for h in SOAP_HEADINGS if h not in names]
    if missing:
        problems.append("빠진 제목: " + ", ".join(missing))
    repeated = [h for h in SOAP_HEADINGS if names.count(h) > 1]
    if repeated:
        problems.append("두 번 이상 나온 제목: " + ", ".join(repeated))
    first = list(dict.fromkeys(names))
    if first != [h for h in SOAP_HEADINGS if h in first]:
        problems.append("순서가 다릅니다: " + " → ".join(names))
    empty = []
    for heading, body in found:
        if not "".join(body).strip() and heading not in empty:
            empty.append(heading)
    if empty:
        problems.append("본문이 빈 제목: " + ", ".join(empty))
    return problems


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def git_log(cwd, *args):
    """stdout of `git log` in `cwd` (signature lines off), None on failure."""
    result = subprocess.run(
        ["git", "-c", "log.showSignature=false", "-C", cwd, "log", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def go_status(cwd, card_id):
    """Signature status (`%G?`) of the go for `card_id`: "G" if any commit
    reachable from HEAD with subject exactly `Go: <card_id>` has a valid
    signature, else the status of the newest such commit, None if there is
    none. The signer's identity is not checked (decision-13)."""
    subject = f"Go: {card_id}"
    out = git_log(cwd, "--format=%H %s", "HEAD")
    if out is None:
        return None
    statuses = []
    for line in out.splitlines():
        commit, _, rest = line.partition(" ")
        if rest != subject:
            continue
        status = (git_log(cwd, "-1", "--format=%G?", commit) or "").strip()
        if status == "G":
            return "G"
        statuses.append(status)
    return statuses[0] if statuses else None


def go_problem(cwd, card_id):
    """Message block when the go is missing or not validly signed."""
    status = go_status(cwd, card_id)
    if status == "G":
        return None
    found = (
        "HEAD에서 닿는 커밋 중 제목이 정확히 "
        f"'Go: {card_id}'인 커밋이 없습니다."
        if status is None
        else f"'Go: {card_id}' 커밋의 서명이 유효하지 않습니다(%G? = {status}, G여야 함)."
    )
    return (
        f"Plan-Review-Go 승인(go)이 없습니다. {found} 구현 계획을 사람이 "
        "리뷰하고 승인했다면, 사람이 직접 서명 커밋으로 go를 남겨야 합니다:\n"
        f'  git commit --allow-empty -S -m "Go: {card_id}"\n'
        "  Claude는 go 커밋을 만들지 않습니다 - 유저에게 리뷰와 go를 요청하세요."
    )


def card_problems(card_id, text, edit):
    """Message blocks for everything the card lacks (empty = complete)."""
    blocks = []
    plan = plan_text(text)
    if plan is None or not plan.strip():
        blocks.append(
            "구현 계획(Implementation Plan)이 없습니다. "
            f"'backlog {edit} edit {card_id} --plan \"...\"'로 계획을 적으세요.\n"
            + SOAP_TEMPLATE
        )
    else:
        problems = soap_problems(plan)
        if problems:
            blocks.append(
                "구현 계획이 SOAP 형식이 아닙니다. 예약 제목 네 개를 이 순서로 "
                "한 번씩, 철자 그대로 쓰고 각 절에 본문을 채우세요.\n"
                + "\n".join(f"  - {p}" for p in problems)
                + f"\n'backlog {edit} edit {card_id} --plan \"...\"'로 고치세요.\n"
                + SOAP_TEMPLATE
            )
    if not has_items(text, "AC"):
        blocks.append(
            "인수 조건(AC)이 없습니다. "
            f"'backlog {edit} edit {card_id} --ac \"...\"'로 추가하세요."
        )
    if not has_items(text, "DOD"):
        blocks.append(
            "완료 조건(DoD)이 없습니다. "
            f"'backlog {edit} edit {card_id} --dod \"...\"'로 추가하세요."
        )
    return blocks


def check_card(cwd, kind, token):
    folder, edit = ("drafts", "draft") if kind == "promote" else ("tasks", "task")
    found = find_card(cwd, folder, token)
    if found is None:
        return
    card_id, text = found
    blocks = card_problems(card_id, text, edit)
    if kind == "start":
        go = go_problem(cwd, card_id)
        if go is not None:
            blocks.append(go)
    if blocks:
        action = "승격할" if kind == "promote" else "In Progress로 옮길"
        deny(
            f"{TAG} {card_id}을(를) {action} 수 없습니다 "
            "(구현 계획 = SOAP + AC + DoD).\n"
            + "\n".join(f"- {b}" for b in blocks)
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
