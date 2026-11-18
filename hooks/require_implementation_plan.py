#!/usr/bin/env python3
# ---
# title: require_implementation_plan
# description: 구현 계획이 없는 draft의 승격과 태스크 착수를 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-18'
# ---
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

Command position follows require_draft_first.py: heredoc bodies are
dropped, `\\`-newline continuations joined, the line split into segments
on `;`, `&`, `|`, `(`, `)` and newlines, env assignments and wrappers
(`env`, `sudo`, `npx`, ...) skipped, `backlog` compared by basename. So
`echo "backlog draft promote 8"` or a commit message quoting the command is
not gated. Unbalanced quotes: a text match at the start of a line or after
a separator stands in (gate). Known gaps (decision-1): indirection such as
`bash -c`, `eval`, scripts, and the backlog MCP server / web UI are not
seen; the `-s "In Progress"` check on the task card covers cards that
skipped `draft promote`, but a status change made through MCP or the web UI
itself is not seen. Each command is judged on the card as it is on disk
before the line runs, so `edit --plan ... && draft promote` in one line is
denied - run the edit first. In `task edit`, the first word that isn't an
option is taken as the task ID (as in require_test_first.py).

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

`-s "In Progress"` also passes the approval gate (decision-14, which
replaces decision-13): plan -> review -> plan approval. After a human
reviewed the plan they record the plan approval as an empty commit signed
with their own key: `git commit --allow-empty -S -m "Plan-Approved: <ID>"`.
The hook searches the commits reachable from HEAD (`git log HEAD`; other
branches don't count, so an approval on an unmerged branch is not seen
until it is merged) for a subject that is exactly `Plan-Approved: <ID>`
with the card's own ID, and needs at least one of them to be signed by a
human key (TASK-72): `%G?` = `G` (valid signature) and the signing key's
fingerprint `%GK` (`SHA256:<base64>`, the second field of
`ssh-keygen -lf <key>.pub`) listed in the pinned human key list
`human-signers`. That file lives next to this hook file and only there
(the directory of `realpath(__file__)`; once installed that is the hook
directory config_guard.py protects); no environment variable or project
setting moves it. One fingerprint per line, blank lines and `#` comment
lines allowed. A missing, unreadable or empty file, or any other line,
denies with setup guidance (fail-closed) - so until the user creates it,
every `-s "In Progress"` in every project is denied.

The signer principal `%GS` and the project config's `humanSigners` are not
used for the verdict any more: ~/.ssh/allowed_signers and the project
config are agent-writable, so an AI key could be listed as `human` or the
AI principal added to `humanSigners`. A config that still has
`humanSigners` only gets a note that it is no longer used. Every git call
that reads signatures passes
`-c gpg.ssh.allowedSignersFile=$HOME/.ssh/allowed_signers`, so repo-local,
global or environment-variable git config can't point verification at
another file, and pins the verification programs
(`-c gpg.ssh.program=ssh-keygen -c gpg.program=gpg -c gpg.x509.program=gpgsm`,
found on the hook's PATH), so a fake program set in config can't fabricate
a good signature by a pinned fingerprint. The deny tells apart: no approval commit, signature not valid
(`%G?` other than G), and a valid signature by a key that is not pinned
(its `%GK` shown). The emptiness of the commit is not checked, and the
hook never creates an approval commit.

An ID with no card file passes - backlog itself reports the error.

TASK-75: cards and approval commits are read in the project the command
targets, not the session cwd - the cwd moved by earlier `cd <dir>` on the
same line, or `BACKLOG_CWD=<dir>`, taken at its git top-level. A target that
isn't a backlog project passes; one that can't be known statically
(`cd "$X"`, `BACKLOG_CWD=$Y`) is denied.

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
FALLBACK_HEAD = r"(?:^|[;&|(])\s*(?:\S*/)?backlog(?:\.md)?\s+"  # ---- 1
PROMOTE_FALLBACK_RE = re.compile(
    FALLBACK_HEAD + r"drafts?\s+promote\s+([^\s'\"]+)", re.MULTILINE
)
START_FALLBACK_RE = re.compile(
    FALLBACK_HEAD + r"tasks?\s+edit\s+([^\s'\"-][^\s'\"]*)[^\n;&|]*?"
    r"\s(?:-s|--status)(?:=|\s+)['\"]?in\s+progress\b",
    re.MULTILINE | re.IGNORECASE,
)
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
HUMAN_SIGNERS_FILE = "human-signers"  # ---- 2
# `ssh-keygen -lf` and git's %GK: "SHA256:" + 32 bytes as unpadded base64
FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


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
    for name in (".claude-code-agile-hooks.json", ".claude-rails.json"):
        path = os.path.join(cwd, name)
        if os.path.isfile(path):
            return path
    return None


def has_legacy_human_signers(cwd):
    """True if the project config still has a `humanSigners` key (TASK-72:
    no longer used for the verdict, only mentioned in deny messages)."""
    path = project_config_path(cwd)
    if path is None:
        return False
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and "humanSigners" in config


def fingerprint_path():
    """TASK-72: the pinned human key list sits next to this hook file
    (symlinks resolved), never anywhere else."""
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)), HUMAN_SIGNERS_FILE  # ---- 3
    )


def human_fingerprints():
    """(set of pinned fingerprints, None), or (None, why the file is not
    usable). Fail-closed: a missing, unreadable or empty file or any
    malformed line gives no set."""
    try:
        with open(fingerprint_path(), errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return None, "이(가) 없습니다"
    except OSError:
        return None, "을(를) 읽을 수 없습니다"
    found = set()
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not FINGERPRINT_RE.fullmatch(line):  # ---- 4
            return None, (
                f"의 {number}번째 줄 형식이 틀렸습니다: '{line}' "
                "(한 줄에 SHA256:<base64> 지문 하나)"
            )
        found.add(line)
    if not found:
        return None, "이(가) 비어 있습니다(지문 줄이 없음)"
    return found, None


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
    if target is None or status is None or not is_in_progress(status):  # ---- 5
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


def fallback_gates(text):
    """Text match for a line shlex can't split (unbalanced quotes): a
    gated command at the start of a line or after a separator still gates."""
    found = [(m.start(), "promote", m.group(1)) for m in PROMOTE_FALLBACK_RE.finditer(text)]
    found += [(m.start(), "start", m.group(1)) for m in START_FALLBACK_RE.finditer(text)]
    return [(kind, token) for _, kind, token in sorted(found)]


def gated_commands(command):
    """(kind, ID) for every gated backlog command in command position."""
    if not command:
        return []
    stripped = strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 6
    try:
        tokens = tokenize(stripped)
    except ValueError:
        return fallback_gates(stripped)
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
        m = ID_RE.search(text.split("\n---", 1)[0])  # ---- 7
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
        if line.rstrip() in SOAP_HEADINGS:  # ---- 8
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
    """stdout of `git log` in `cwd` (signature lines off), None on failure.
    TASK-72: signatures are always verified against
    $HOME/.ssh/allowed_signers with the real verification programs,
    whatever repo, global or env config says (command-line -c wins over all
    of them, GIT_CONFIG_COUNT and GIT_CONFIG_PARAMETERS included)."""
    allowed = os.path.join(os.path.expanduser("~"), ".ssh", "allowed_signers")  # ---- 9
    result = subprocess.run(
        [
            "git",
            "-c",
            "log.showSignature=false",
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed}",
            # TASK-72 B6: a fake verifier set in config can print "good
            # signature by <human fingerprint>" for any commit. git picks
            # the verifier by the signature's armor, not gpg.format, so all
            # three are pinned (gpg.program also overrides its alias
            # gpg.openpgp.program). The names are bare and found on PATH on
            # purpose: the hook process's PATH comes from the Claude Code
            # environment, which repo config can't change. A missing gpg or
            # gpgsm makes verification fail (not G), so it fails closed.
            "-c",
            "gpg.ssh.program=ssh-keygen",  # ---- 10
            "-c",
            "gpg.program=gpg",
            "-c",
            "gpg.x509.program=gpgsm",
            "-C",
            cwd,
            "log",
            *args,
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def approval_status(cwd, card_id, fingerprints):
    """(kind, detail) of the plan approval for `card_id` among the commits
    reachable from HEAD whose subject is exactly `Plan-Approved: <card_id>`:
    ("approved", %GK) if any has `%G?` = G and a `%GK` in `fingerprints`;
    otherwise the newest one's problem - ("invalid", %G?) or
    ("not_human", %GK) - or ("missing", None) when there is none."""
    subject = f"Plan-Approved: {card_id}"
    out = git_log(cwd, "--format=%H %s", "HEAD")
    if out is None:
        return ("missing", None)
    problems = []
    for line in out.splitlines():
        commit, _, rest = line.partition(" ")
        if rest != subject:
            continue
        info = git_log(cwd, "-1", "--format=%G?%x00%GK", commit) or ""
        status, _, key = info.strip("\n").partition("\0")
        if status != "G":  # ---- 11
            problems.append(("invalid", status))
        elif key in fingerprints:  # ---- 12
            return ("approved", key)
        else:
            problems.append(("not_human", key))
    return problems[0] if problems else ("missing", None)


def approval_problem(cwd, card_id):
    """Message block when the approval gate does not pass, else None."""
    command = f'  git commit --allow-empty -S -m "Plan-Approved: {card_id}"\n'
    ask = "  Claude는 계획 승인 커밋을 만들지 않습니다 - 유저에게 리뷰와 계획 승인을 요청하세요."
    path = fingerprint_path()
    legacy = (
        "  프로젝트 설정의 humanSigners는 더 이상 판정에 쓰지 않습니다 - "
        f"사람 키 지문은 {path}에 고정합니다.\n"
        if has_legacy_human_signers(cwd)
        else ""
    )
    fingerprints, why = human_fingerprints()
    if fingerprints is None:
        return (
            f"승인 게이트를 확인할 수 없습니다: 사람 키 지문 목록 {path}{why}. "
            "이 파일을 만들기 전까지는 모든 프로젝트에서 -s \"In Progress\"가 막힙니다. "
            "사람이 직접 만들어야 합니다(훅 디렉터리라 Claude는 쓸 수 없습니다):\n"
            "  1. ssh-keygen -lf <사람 공개키 .pub>로 지문을 본다 - 두 번째 칸 SHA256:...이 지문이다.\n"
            f"  2. 그 SHA256:... 값을 {path}에 한 줄에 하나씩 적는다(빈 줄 · # 주석 허용).\n"
            "  3. 사람 공개키를 ~/.ssh/allowed_signers에 올린다 - 훅은 서명을 이 파일로만 검증한다.\n"
            + legacy
            + "그 뒤 사람이 계획을 리뷰하고 자기 키로 계획 승인 커밋을 남깁니다:\n"
            + command
            + ask
        )
    kind, detail = approval_status(cwd, card_id, fingerprints)
    if kind == "approved":
        return None
    if kind == "missing":
        found = (
            "HEAD에서 닿는 커밋 중 제목이 정확히 "
            f"'Plan-Approved: {card_id}'인 커밋이 없습니다."
        )
    elif kind == "invalid":
        found = (
            f"'Plan-Approved: {card_id}' 커밋의 서명이 유효하지 않습니다"
            f"(%G? = {detail}, G여야 함 - 서명 키가 ~/.ssh/allowed_signers에 없으면 U)."
        )
    else:
        found = (
            f"'Plan-Approved: {card_id}' 커밋이 사람 키가 아닌 키의 서명입니다"
            f"(%GK = {detail}, 사람 키 지문 목록: {path})."
        )
    return (
        f"계획 승인이 없습니다. {found} 구현 계획을 사람이 리뷰하고 승인했다면, "
        "사람이 자기 키로 직접 서명 커밋을 남겨야 합니다:\n" + command + legacy + ask
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
    if found is None:  # ---- 13
        return
    card_id, text = found
    blocks = card_problems(card_id, text, edit)
    if kind == "start":  # ---- 14
        approval = approval_problem(cwd, card_id)
        if approval is not None:
            blocks.append(approval)
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
    command = tool_input.get("command") or ""
    gates = gated_commands(command)
    if not gates:
        sys.exit(0)
    for root, found in target_roots(command, cwd, segment_gate, gates):  # ---- 15
        for kind, token in found:
            check_card(root, kind, token)
    sys.exit(0)


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 폴백 정규식의 명령 위치 접두
#   설명: 텍스트 폴백도 줄 시작이나 구분자 뒤의 backlog만 잡는다. `echo "backlog draft promote 8"` 같은 인용 문구를 게이트하지 않으려는 장치다.
#   개념: 명령 위치
# 2 사람 키 지문 목록 파일명
#   설명: 승인 서명을 낸 키가 사람 키인지는 이 파일의 SHA256 지문으로만 판정한다. 프로젝트 설정이나 ~/.ssh/allowed_signers는 에이전트가 쓸 수 있어 신뢰하지 않는다.
#   관련: decision-14, TASK-72
#   개념: 핀된 지문(pinning)
# 3 지문 파일 위치는 훅 디렉터리로 고정
#   설명: 환경변수나 프로젝트 설정으로 옮길 수 없고 realpath(__file__)의 디렉터리에만 둔다. 설치되면 config_guard.py가 지키는 훅 디렉터리라 에이전트가 지문을 바꿔치기할 수 없다.
#   관련: hooks/config_guard.py
#   개념: 신뢰 경계
# 4 지문 목록은 한 줄이라도 틀리면 fail-closed
#   설명: 형식이 틀린 줄이 하나라도 있으면 집합 전체를 버리고 안내와 함께 거부한다. 일부만 읽어 통과시키면 오타가 조용히 보안 구멍이 된다.
#   관련: TASK-72
#   개념: fail-closed
# 5 In Progress 판정
#   설명: 공백을 정규화하고 대소문자를 무시해 `-s "In  Progress"`처럼 변형해도 같은 상태로 본다. 인자 순서와 무관하게 첫 비옵션 단어를 task ID로 잡는 규칙은 require_test_first.py와 같다.
#   관련: hooks/require_test_first.py
# 6 백슬래시 줄바꿈 접합
#   설명: bash는 단어 파싱 전에 `\`+개행을 이어 붙이므로 같은 순서로 처리한다. heredoc 본문에 적힌 예시 명령이 게이트되지 않도록 본문을 먼저 지운다.
#   개념: heredoc
# 7 frontmatter에서만 id를 읽음
#   설명: `\n---` 앞(프론트매터)만 검색해 본문에 인용된 `id:` 줄에 속지 않는다. 카드를 backlog CLI 없이 파일에서 직접 읽는 이유는 CLI 의존 없이 훅을 자립시키기 위해서다.
#   개념: frontmatter
# 8 SOAP 예약 제목 판정
#   설명: 줄 전체가 예약 제목과 정확히 같아야 한다(끝 공백만 무시). 대소문자나 제목 레벨을 정규화하지 않아 형식 흉내만 낸 계획이 통과하지 못한다.
#   관련: TASK-58
#   개념: SOAP
# 9 서명 검증 파일 고정
#   설명: 검증은 항상 $HOME/.ssh/allowed_signers로만 한다. `git -c`로 넘긴 값은 repo · 전역 · 환경변수 설정보다 우선하므로 설정으로 검증 파일을 바꿔치는 공격을 막는다.
#   관련: TASK-72
#   개념: 명령행 -c 우선순위
# 10 검증 프로그램 고정
#   설명: 설정에 가짜 검증기를 심으면 어떤 커밋에도 사람 지문의 정상 서명을 위조해 출력할 수 있다. ssh · gpg · gpgsm 세 프로그램을 모두 이름으로 고정하고, PATH는 Claude Code 환경에서 오므로 repo 설정이 못 바꾼다고 본다. gpg가 없으면 G가 아니어서 fail-closed다.
#   관련: TASK-72 B6
#   개념: 검증기 핀
# 11 서명 유효성은 %G? == G만 인정
#   설명: U(알 수 없는 서명자), B, E 등은 전부 무효로 취급한다. 서명이 없거나 allowed_signers에 없는 키의 커밋은 승인으로 보지 않는다.
#   관련: TASK-72
#   개념: 서명 상태 코드
# 12 유효 서명 + 사람 지문 둘 다 필요
#   설명: 서명이 유효해도 키 지문이 핀된 목록에 없으면 승인이 아니다. AI 키로 서명한 Plan-Approved 커밋이 통과하지 못하게 하는 마지막 관문이다.
#   관련: decision-14
#   개념: 사람 승인
# 13 카드 파일이 없으면 통과
#   설명: ID에 해당하는 카드가 없으면 backlog 자신이 오류를 내므로 훅은 끼어들지 않는다. 존재하지 않는 ID로 게이트가 오탐하는 것을 피한다.
#   개념: fail-open
# 14 승인 게이트는 착수에만 적용
#   설명: draft promote는 계획만 요구하고, In Progress 전환에서만 사람 서명 승인을 추가로 요구한다. 계획 → 리뷰 → 계획 승인 순서를 강제하는 지점이다.
#   관련: decision-14
# 15 카드는 명령이 겨누는 프로젝트에서 읽는다
#   설명: 같은 줄의 앞선 cd와 BACKLOG_CWD로 promote · In Progress가 겨누는 디렉터리를 정하고, 그 git top-level의 카드 · 승인 커밋으로 판정한다. 세션 프로젝트의 같은 ID 카드를 읽어 `cd <scratch> && backlog draft promote DRAFT-1`을 잘못 거부하던 문제(2026-11-17)와, 비프로젝트 세션에서 `cd <프로젝트> && ...`가 검사 없이 통과하던 우회를 함께 막는다. 대상을 정적으로 알 수 없으면 target_roots가 거부한다.
#   관련: TASK-75 (B3 · B4 · B6 · B7), hooks/dedup_drift_guard.py (command_target_dir · target_roots)
#   개념: 대상 저장소, fail-closed
