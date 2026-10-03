#!/usr/bin/env python3
"""PreToolUse (matcher: Bash, if: Bash(git *))
Branch-aware git guardrails + destructive gh CLI protection. Ported from
karanb192/claude-code-hooks' git-safety plugin (MIT license). Owns every
git-specific destructive rule exclusively (including "force push to main",
which duplicated block_dangerous_commands upstream - see plan's "겹침 정리" #1).

Covers: direct push to main/master, deleting a protected branch, and
destructive `gh` operations (pr merge/close, issue close, release/repo delete).

Does its own subcommand/arg detection so `git -C <path> push` (flags before
the subcommand) is still recognized - same technique as pre_push_check.py,
duplicated here on purpose (each hook stays fully self-contained).

TASK-37: git commands are found the way pre_push_check.py (TASK-34) finds
them. Heredoc bodies are dropped, backslash-newline continuations joined,
and the line is tokenized and split into shell segments (`;`, `&&`, `||`,
`|`, `&`, `(`, newline). In each segment, env assignments and simple
wrappers (`env`, `sudo`, `command`, ...) in front are skipped
(`command_head`), and the executable is compared by basename, so
`/usr/bin/git` and `../bin/git` get the same rules as `git` (decision-1).
Text is not a command: a quoted argument (`echo "git push origin main"`,
`git commit -m "... git push origin main"`) is a single token whose basename
isn't `git`, and heredoc bodies never reach the tokenizer.

Conservative choice: within a segment, an *unquoted* `git` word after the
command head is judged too, not only the head itself. Runners such as
`xargs git push ...`, `timeout 60 git push ...` or `find -exec git ...`
really execute it, and telling runners from printers (`echo git push origin
main`) would need a list that can never be complete - so the plain-argument
case may produce a spurious block, never a missed one. The pre-TASK-37 code
already judged every unquoted `git` word on the line.

Parse failure (AC3): if the heredoc-stripped line can't be tokenized (an
unbalanced quote), command position can't be told apart from text. The line
is then blocked when it plausibly holds a guarded git operation - the words
`git` and `push` or `branch` together with `main`/`master` anywhere in it
(`check_unparsable`). The previous code returned "no git command" here
(fail-open), so `git push origin main "x` slipped through. A spurious block
is recoverable (fix the quoting and retry); a missed block on a protected
branch is not.

Known gaps (decision-1): `bash -c "git push origin main"`, `eval`, aliases,
scripts, and backtick/`$(...)` substitution are not seen. The `gh` checks
are unchanged by TASK-37.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

PROTECTED_BRANCHES = {"main", "master"}
FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
PROTECTED_WORD_RE = re.compile(r"\b(?:main|master)\b")


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


def prepare(command):
    """Heredoc bodies dropped and backslash-newline continuations joined,
    the way bash sees the line before it splits words."""
    return strip_heredoc_bodies(command).replace("\\\n", "")


def parse_segments(command):
    """Shell segments of `command`, or None if it can't be tokenized."""
    try:
        tokens = tokenize(prepare(command))
    except ValueError:
        return None
    return split_segments(tokens)


def subcommand_args(segment, git_index, subcommand):
    """Tokens after `subcommand` when the git at `git_index` runs it (git's
    global flags skipped), else None."""
    j = git_index + 1
    while j < len(segment):
        tok = segment[j]
        if tok in FLAGS_WITH_ARG:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        if tok == subcommand:
            return segment[j + 1 :]
        break
    return None


def git_invocations(segments, subcommand):
    """Argument lists of every `git <subcommand>` in `segments`: the git
    executable (by basename) at or after each segment's command head."""
    found = []
    for segment in segments:
        for k in range(command_head(segment), len(segment)):
            if os.path.basename(segment[k]) != "git":
                continue
            args = subcommand_args(segment, k, subcommand)
            if args is not None:
                found.append(args)
    return found


def git_args_after_subcommand(command, subcommand):
    """Return the tokens that come after the first git `subcommand`, or
    None if that subcommand isn't invoked (or the line can't be parsed -
    main() handles that case conservatively via check_unparsable)."""
    segments = parse_segments(command)
    if segments is None:
        return None
    found = git_invocations(segments, subcommand)
    return found[0] if found else None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def check_push(segments, command):
    for args in git_invocations(segments, "push"):
        non_flags = [a for a in args if not a.startswith("-")]
        # `git push origin main` / `git push origin main:main` targets a branch
        # explicitly; a bare `git push` (no refspec) pushes the current branch,
        # which this hook can't determine without running git - only the
        # explicit-refspec form is checked here.
        for arg in non_flags[1:]:
            target = arg.split(":")[-1]
            if target in PROTECTED_BRANCHES:
                deny(
                    f"[git-safety] '{target}' 브랜치로 직접 push하는 것은 금지됩니다: {command}"
                )


def check_branch_delete(segments, command):
    for args in git_invocations(segments, "branch"):
        if not any(a in ("-d", "-D", "--delete") for a in args):
            continue
        for arg in args:
            if arg in PROTECTED_BRANCHES:
                deny(f"[git-safety] 보호된 브랜치 '{arg}' 삭제는 금지됩니다: {command}")


def check_unparsable(command):
    """Conservative judgement for a line that can't be tokenized (see the
    module docstring): block if it plausibly pushes to or deletes a
    protected branch."""
    text = prepare(command)
    if not re.search(r"\bgit\b", text) or not PROTECTED_WORD_RE.search(text):
        return
    if re.search(r"\b(?:push|branch)\b", text):
        deny(
            "[git-safety] 명령을 해석할 수 없어(따옴표 불균형 등) main/master 대상 "
            f"push·브랜치 삭제인지 확인할 수 없으므로 보수적으로 차단합니다: {command}"
        )


def check_gh_destructive(command):
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if "gh" not in tokens:
        return

    gh_idx = tokens.index("gh")
    rest = tokens[gh_idx + 1 :]

    destructive_patterns = [
        ("pr", "merge"),
        ("pr", "close"),
        ("issue", "close"),
        ("release", "delete"),
        ("repo", "delete"),
    ]
    for noun, verb in destructive_patterns:
        if noun in rest and verb in rest:
            deny(f"[git-safety] 'gh {noun} {verb}' 계열 명령은 금지됩니다: {command}")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    segments = parse_segments(command)
    if segments is None:
        check_unparsable(command)
    else:
        check_push(segments, command)
        check_branch_delete(segments, command)
    check_gh_destructive(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
