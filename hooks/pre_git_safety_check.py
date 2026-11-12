#!/usr/bin/env python3
# ---
# title: pre_git_safety_check
# description: 브랜치를 보는 git 안전 규칙과 파괴적 gh CLI 명령 차단을 맡는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash, no `if` filter)
TASK-37: registered without `if: Bash(git *)` on purpose - that permission-rule
filter matches the command text, so `/usr/bin/git push origin main` would never
reach this hook and the basename normalization below would be moot.
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

TASK-38: which branch a push writes to is resolved, and a push to
main/master is allowed only as a *first push*.
- Targets: `<src>:<dst>` -> dst, `<src>` -> src (plus any remote.<r>.push
  mapping); `refs/heads/` is stripped, HEAD/@ resolve to the current
  branch, `*` and `:` (matching), --all/--branches/--mirror mean "every
  branch". Without a refspec (`git push`, `git push origin`, `git push -u
  origin`) the target follows git: remote.<r>.mirror, remote.<r>.push,
  then push.default (simple/current -> current branch, upstream ->
  current branch *and* branch.<b>.merge, matching -> every branch,
  nothing -> none). The remote is the explicit one, else
  branch.<b>.pushRemote, remote.pushDefault, branch.<b>.remote, "origin".
  This closes the old gap where presetting an upstream on main and running
  a bare `git push` skipped the check. Long options are matched by prefix
  (`--forc`), as git does.
- First-push exception: `git ls-remote --exit-code --heads <url>
  refs/heads/<b>` exiting 2 (ref absent) on every pushurl (or every url
  when there are several) allows it. Exit 0 blocks as before; anything
  else - unknown remote, network error, 10s timeout, missing git,
  url.*.pushInsteadOf in the config - blocks (fail-closed).
- Force (`-f`, `--force*`, `+refspec`, `--mirror`, a forced
  remote.<r>.push) and delete (`-d`, `--delete`, `:main`) to main/master
  are blocked even on a first push - deliberately conservative: there is
  nothing to overwrite yet, but no reason to force either.
- Where git runs: the hook input's `cwd`, followed through `cd`/`pushd`
  at command position (carried over `;`/`&&`/newline, not `|`/`||`/`&`,
  undone by `)`; a missing directory leaves the cwd), then `git -C`.
  `--git-dir`/`--work-tree` are passed on. Unknowable inputs - `cd -`,
  `cd $VAR`, `popd`, CDPATH, `git -c`/`--config-env`/`--exec-path`,
  `GIT_*=` assignments - block any push that needs a git query: the hook
  won't run user-supplied config before the human approves the command.
- If the current branch can't be read (not a repository, unborn HEAD) a
  push that needs it is blocked; a detached HEAD without a refspec is
  allowed (git refuses to push it).
- Only push commands run git; everything else - and a push whose every
  refspec has an explicit non-protected `:<dst>` - makes no subprocess
  call. `git push origin task/x` costs one local `git config` call.

TASK-45: gh is judged like git. In each segment, every gh executable (by
basename: `/usr/bin/gh`) at or after the command head - unquoted runner
arguments included, the same conservative choice as for git - has its
first two subcommand words read, skipping gh's flags (`-R/--repo` and
`--hostname` take a value; `-R` after the subcommand doesn't matter). Only
an exact (noun, verb) pair from GH_DESTRUCTIVE blocks, so `gh pr list; git
merge --ff-only x` (words spread over segments - the old whole-line scan
blocked it) and `gh pr view merge` pass. `gh api` is checked for the same
operations: a non-GET call to `repos/<o>/<r>/pulls/<n>/merge`, DELETE on
`repos/<o>/<r>` or `.../releases/<id>` (`releases/tags/<t>` too), PATCH on
`.../pulls|issues/<n>` with `state=closed` or an unseen `--input` body,
and GraphQL text naming mergePullRequest/closePullRequest/closeIssue/
deleteRepository. The method defaults as gh's does (POST with fields).
An unparsable line is blocked when it has the word `gh` plus a noun/verb
pair, or `api` plus `/merge`, DELETE, `state=closed` or such a mutation.

Known gaps (decision-1): `bash -c "git push origin main"`, `eval`, aliases,
scripts, and backtick/`$(...)` substitution are not seen. Neither are
refspecs supplied at run time (`... | xargs git push origin`,
`find -exec git push origin {} ;`) or `export GIT_DIR=...` in an earlier
command. For gh: `gh alias`/extensions, an unknown value-taking flag before
the subcommand, GraphQL queries read from a file (`query=@q.graphql`), and
other REST endpoints (e.g. deleting refs) are not covered.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = {"main", "master"}
FLAGS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")
PROTECTED_WORD_RE = re.compile(r"\b(?:main|master)\b")
# TASK-38: git queries made while judging a push (never for other commands)
GIT_TIMEOUT = 10
PUSH_LONG_WITH_ARG = (
    "push-option",
    "receive-pack",
    "exec",
    "repo",
    "recurse-submodules",
)
OPAQUE_GLOBAL_OPTS = ("--config-env", "--exec-path")
TRUE_VALUES = ("true", "yes", "on", "1")
# TASK-45: destructive gh operations
GH_DESTRUCTIVE = {
    ("pr", "merge"),
    ("pr", "close"),
    ("issue", "close"),
    ("release", "delete"),
    ("repo", "delete"),
}
GH_FLAGS_WITH_ARG = {"-R", "--repo", "--hostname"}
GH_API_FLAGS_WITH_ARG = {
    "-X",
    "--method",
    "-f",
    "--raw-field",
    "-F",
    "--field",
    "-H",
    "--header",
    "--input",
    "-q",
    "--jq",
    "-t",
    "--template",
    "-p",
    "--preview",
    "--hostname",
    "--cache",
}
GH_API_HOST_RE = re.compile(r"^https?://[^/]+/(?:api/v3/)?")
_REPO = r"repos/[^/]+/[^/]+"
GH_API_RULES = [
    (_REPO + r"/pulls/[^/]+/merge", {"PUT", "POST", "PATCH", "DELETE"}, "pr merge"),
    (_REPO, {"DELETE"}, "repo delete"),
    (_REPO + r"/releases/(?:tags/)?[^/]+", {"DELETE"}, "release delete"),
]
GH_API_CLOSABLE = _REPO + r"/(?:pulls|issues)/[^/]+"
GH_GRAPHQL_MUTATIONS = {
    "mergePullRequest": "pr merge",
    "closePullRequest": "pr close",
    "closeIssue": "issue close",
    "deleteRepository": "repo delete",
}
GH_API_UNPARSABLE_RE = re.compile(
    r"/merge\b|\bDELETE\b|state=closed|" + "|".join(GH_GRAPHQL_MUTATIONS),
    re.IGNORECASE,
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


def prepare(command):
    """Heredoc bodies dropped and backslash-newline continuations joined,
    the way bash sees the line before it splits words."""
    return strip_heredoc_bodies(command).replace("\\\n", "")  # ---- 1


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
            if os.path.basename(segment[k]) != "git":  # ---- 2
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


# --- TASK-38: push target resolution (see the module docstring) ---


class Unverifiable(Exception):
    """git couldn't tell us what a push targets - the caller blocks."""


def run_git(cwd, global_opts, args):
    """(returncode, stdout) of `git <global_opts> <args>` run in `cwd`, or
    None when git couldn't run at all (unknown cwd, missing git or
    directory, timeout). Never prompts: stdin is closed and terminal
    credential prompts are off. (GIT_PROTOCOL_FROM_USER=0 is not set: it
    would also refuse local-path remotes, whose `file` protocol is
    "user"-only; ext:: is already disabled by git's default policy.)"""
    if cwd is None:
        return None
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # ---- 3
    try:
        result = subprocess.run(
            ["git", *global_opts, *args],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode, result.stdout


def after_cd(segment, cwd):
    """The cwd after `segment` runs: changed only by `cd`/`pushd` at command
    position. None means "unknown" (`cd -`, `$VAR`, `popd`, CDPATH)."""
    head = command_head(segment)
    if head >= len(segment) or segment[head] not in ("cd", "pushd", "popd"):
        return cwd
    if cwd is None or segment[head] == "popd":
        return None
    args = [a for a in segment[head + 1 :] if a == "-" or not a.startswith("-")]
    if not args:
        return os.path.expanduser("~")
    arg = args[0]
    if arg == "-" or "$" in arg or "`" in arg:
        return None
    if os.environ.get("CDPATH") and not arg.startswith(("/", ".", "~")):
        return None
    target = os.path.normpath(os.path.join(cwd, os.path.expanduser(arg)))
    # a failed `cd` leaves the cwd as it was (`cd nowhere; git push`)
    return target if os.path.isdir(target) else cwd


def segments_with_cwd(tokens, cwd):
    """(segment, cwd it runs in) pairs. `cd` carries over `;`, `&&` and
    newlines, not over `|`, `||` or `&`, and is undone by a closing `)`."""
    stack = [cwd]
    pairs = []
    current = []
    for tok in tokens + [";"]:
        if not (tok and set(tok) <= SEPARATOR_CHARS):
            current.append(tok)
            continue
        if current:
            pairs.append((current, stack[-1]))
            if tok.strip("()") not in ("|", "||", "&"):  # ---- 4
                stack[-1] = after_cd(current, stack[-1])
            current = []
        for ch in tok:
            if ch == "(":
                stack.append(stack[-1])
            elif ch == ")" and len(stack) > 1:
                stack.pop()
    return pairs


def push_invocations(segment):
    """(tokens before git, git's global options, push args) for every
    `git push` in `segment` (same command-position rules as
    git_invocations)."""
    found = []
    for k in range(command_head(segment), len(segment)):
        if os.path.basename(segment[k]) != "git":
            continue
        args = subcommand_args(segment, k, "push")
        if args is not None:
            found.append(
                (segment[:k], segment[k + 1 : len(segment) - len(args) - 1], args)
            )
    return found


def long_option_is(name, option):
    """git accepts any unambiguous prefix of a long option (`--forc`)."""
    return bool(name) and option.startswith(name)


def parse_push_args(args):
    """Split `git push` arguments into remote, refspecs and the flags that
    change what gets pushed."""
    info = {
        "remote": None,
        "refspecs": [],
        "force": False,
        "delete": False,
        "all": False,
        "mirror": False,
        "tags": False,
    }
    repo_opt = None
    positionals = []
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            positionals.extend(args[i:])
            break
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if not eq and any(long_option_is(name, o) for o in PUSH_LONG_WITH_ARG):  # ---- 5
                value = args[i] if i < len(args) else ""
                i += 1
            if name.startswith("no-"):
                continue
            if long_option_is(name, "repo"):
                repo_opt = value
            info["force"] |= long_option_is(name, "force") or name.startswith("force")
            info["mirror"] |= long_option_is(name, "mirror")
            info["delete"] |= long_option_is(name, "delete")
            info["all"] |= long_option_is(name, "all") or long_option_is(
                name, "branches"
            )
            info["tags"] |= long_option_is(name, "tags")
            continue
        if arg.startswith("-") and arg != "-":
            for pos, ch in enumerate(arg[1:], start=2):
                if ch == "o":  # -o<option> / -o <option>
                    if pos == len(arg):
                        i += 1
                    break
                info["force"] |= ch == "f"
                info["delete"] |= ch == "d"
            continue
        positionals.append(arg)
    info["remote"] = positionals[0] if positionals else repo_opt
    info["refspecs"] = positionals[1:]
    info["force"] |= info["mirror"]
    return info


class PushContext:
    """Lazy, cached git queries for one push invocation."""

    def __init__(self, cwd, global_opts, opaque):
        self.cwd = cwd
        self.global_opts = global_opts
        self.opaque = opaque
        self._branch = None
        self._config = None

    def git(self, args):
        if self.opaque:
            raise Unverifiable("git -c/--exec-path/GIT_* 환경변수가 붙은 push")  # ---- 6
        result = run_git(self.cwd, self.global_opts, args)
        if result is None:
            raise Unverifiable("git 실행 실패/시간 초과")
        return result

    def branch(self):
        """Current branch name, or "" on a detached HEAD."""
        if self._branch is None:
            code, out = self.git(["rev-parse", "--abbrev-ref", "HEAD"])
            if code != 0:
                raise Unverifiable("현재 브랜치 확인 실패")
            name = out.strip()
            self._branch = "" if name == "HEAD" else name
        return self._branch

    def config(self):
        """`git config --list` as {key: [values]} (keys as git prints them)."""
        if self._config is None:
            code, out = self.git(["config", "--list", "-z"])
            if code != 0:
                raise Unverifiable("git config 확인 실패")
            config = {}
            for entry in out.split("\0"):
                key, _, value = entry.partition("\n")
                if key:
                    config.setdefault(key, []).append(value)
            self._config = config
        return self._config

    def get(self, key, default=None):
        values = self.config().get(key)
        return values[-1] if values else default


def branch_name(ref, ctx):
    """Branch a refspec side names: `refs/heads/` stripped, HEAD/@ resolved
    to the current branch (\"\" when detached), a `*` meaning every branch."""
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/") :]
    if ref in ("HEAD", "@"):
        return {ctx.branch()} - {""}
    if "*" in ref:
        return set(PROTECTED_BRANCHES)  # ---- 7
    return {ref}


def refspec_targets(spec, ctx):
    """(branch names, forced, deleted) a refspec writes to."""
    forced = spec.startswith("+")
    spec = spec.lstrip("+")
    if spec == ":":  # "matching": every branch both sides have
        return set(PROTECTED_BRANCHES), forced, False
    src, colon, dst = spec.partition(":")
    if colon and not src:
        return branch_name(dst, ctx), forced, True
    return branch_name(dst or src, ctx), forced, False


def configured_push_targets(ctx, remote):
    """Targets of remote.<remote>.push refspecs, plus whether any is forced."""
    targets, forced = set(), False
    for spec in ctx.config().get(f"remote.{remote}.push", []):
        if spec.startswith("^"):  # negative refspec only excludes
            continue
        names, spec_forced, _ = refspec_targets(spec, ctx)
        targets |= names
        forced |= spec_forced
    return targets, forced


def bare_push_targets(ctx, remote):
    """What `git push [<remote>]` without refspecs pushes, conservatively."""
    if ctx.get(f"remote.{remote}.mirror", "false").lower() in TRUE_VALUES:  # ---- 8
        return set(PROTECTED_BRANCHES), True
    targets, forced = configured_push_targets(ctx, remote)
    if targets:  # remote.<remote>.push replaces push.default
        return targets, forced
    mode = ctx.get("push.default", "simple").lower()
    if mode == "nothing":
        return set(), False
    if mode == "matching":
        return set(PROTECTED_BRANCHES), False
    branch = ctx.branch()
    if not branch:  # detached HEAD: git refuses to push
        return set(), False
    if mode in ("current", "simple"):
        return {branch}, False
    merge = ctx.get(f"branch.{branch}.merge", "")
    upstream = (
        {merge[len("refs/heads/") :]} if merge.startswith("refs/heads/") else set()
    )
    return {branch} | upstream, False  # ---- 9


def push_remote(info, ctx):
    """The remote a push goes to: explicit, else the branch's push remote,
    remote.pushDefault, the branch's remote, then "origin"."""
    if info["remote"]:
        return info["remote"]
    branch = ctx.branch()
    keys = ["remote.pushdefault"]
    if branch:
        keys = [f"branch.{branch}.pushremote", *keys, f"branch.{branch}.remote"]
    for key in keys:
        value = ctx.get(key)
        if value:
            return value
    return "origin"


def push_targets(info, ctx, remote):
    """(protected target branches, forced, deleted) of one push."""
    targets, forced, deleted = set(), info["force"], info["delete"]
    if info["all"] or info["mirror"]:
        targets |= PROTECTED_BRANCHES
    for spec in info["refspecs"]:
        names, spec_forced, spec_deleted = refspec_targets(spec, ctx)
        targets |= names
        forced |= spec_forced
        deleted |= spec_deleted
        if ":" not in spec and not info["delete"]:
            # without `:<dst>`, remote.<remote>.push may map it elsewhere
            mapped, mapped_forced = configured_push_targets(ctx, remote)
            targets |= mapped
            forced |= mapped_forced
    if not info["refspecs"] and not (info["all"] or info["mirror"] or info["tags"]):
        bare, bare_forced = bare_push_targets(ctx, remote)
        targets |= bare
        forced |= bare_forced
    return targets & PROTECTED_BRANCHES, forced, deleted


def remote_urls(ctx, remote):
    """What to ls-remote so it sees where the push really goes: pushurls
    when set, every url when there are several, else the remote itself."""
    config = ctx.config()
    if any(key.endswith(".pushinsteadof") for key in config):  # ---- 10
        raise Unverifiable(
            "url.*.pushInsteadOf 설정이 있어 push 대상 URL을 확정할 수 없음"
        )
    push_urls = config.get(f"remote.{remote}.pushurl", [])
    urls = config.get(f"remote.{remote}.url", [])
    return push_urls or (urls if len(urls) > 1 else [remote])


def remote_lacks_branches(ctx, remote, branches):
    """True only when ls-remote proves none of `branches` exists remotely
    (exit code 2); False when one exists; Unverifiable otherwise."""
    patterns = [f"refs/heads/{b}" for b in sorted(branches)]
    for url in remote_urls(ctx, remote):
        if url.startswith("-"):  # ---- 11
            raise Unverifiable("옵션처럼 보이는 원격 이름")
        code, _ = ctx.git(["ls-remote", "--exit-code", "--heads", url, *patterns])
        if code == 0:
            return False
        if code != 2:  # ---- 12
            raise Unverifiable(f"git ls-remote 실패(exit {code})")
    return True


def judge_push(prefix, global_opts, args, cwd):
    """None when the push may run, else the reason it is blocked."""
    passthrough = []
    opaque = any(ASSIGNMENT_RE.match(t) and t.startswith("GIT_") for t in prefix)
    i = 0
    while i < len(global_opts):
        opt = global_opts[i]
        value = global_opts[i + 1] if i + 1 < len(global_opts) else ""
        if opt == "-C":
            cwd = os.path.join(cwd, os.path.expanduser(value)) if cwd and value else cwd
            i += 2
            continue
        if opt == "-c" or opt.startswith(OPAQUE_GLOBAL_OPTS):
            opaque = True
        passthrough.append(opt)
        if opt in FLAGS_WITH_ARG:
            passthrough.append(value)
            i += 1
        i += 1

    info = parse_push_args(args)
    ctx = PushContext(cwd, passthrough, opaque)
    try:
        remote = push_remote(info, ctx)
        targets, forced, deleted = push_targets(info, ctx, remote)
        if not targets:
            return None
        names = "/".join(sorted(targets))
        if forced or deleted:
            return f"'{names}' 브랜치로 직접 push하는 것은 금지됩니다 (force·삭제는 최초 push여도 금지)"
        if remote_lacks_branches(ctx, remote, targets):  # ---- 13
            return None  # first push: nothing on the remote to protect yet
        return f"'{names}' 브랜치로 직접 push하는 것은 금지됩니다 (원격에 이미 존재)"
    except Unverifiable as exc:  # ---- 14
        return (
            f"push 대상이 main/master인지, 원격에 아직 없는지 확인할 수 없어({exc}) "
            "보수적으로 차단합니다"
        )


def check_push(tokens, command, cwd):
    for segment, segment_cwd in segments_with_cwd(tokens, cwd):
        for prefix, global_opts, args in push_invocations(segment):
            reason = judge_push(prefix, global_opts, args, segment_cwd)
            if reason:
                deny(f"[git-safety] {reason}: {command}")


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


# --- TASK-45: destructive gh operations (see the module docstring) ---


def gh_invocations(segments):
    """Argument lists of every gh executable (by basename) at or after each
    segment's command head - same command-position rules as git."""
    found = []
    for segment in segments:
        for k in range(command_head(segment), len(segment)):
            if os.path.basename(segment[k]) == "gh":
                found.append(segment[k + 1 :])
    return found


def gh_command_words(args):
    """(gh's first two subcommand words like `pr`, `merge`, the arguments
    after the first word), skipping gh's own flags; `-R/--repo` and
    `--hostname` take a value."""
    words, rest = [], []
    i = 0
    while i < len(args) and len(words) < 2:
        tok = args[i]
        i += 1
        if tok in GH_FLAGS_WITH_ARG:
            i += 1
        elif not tok.startswith("-"):
            words.append(tok)
            if len(words) == 1:
                rest = args[i:]
    return tuple(words), rest


def gh_api_request(args):
    """(method, endpoint, field values, uses --input) of `gh api <args>`.
    The method defaults the way gh's does: POST once a field or --input is
    given, else GET."""
    method, fields, has_input, positionals = None, [], False, []
    i = 0
    while i < len(args):
        tok = args[i]
        i += 1
        name, value = tok, None
        if tok.startswith("--") and "=" in tok:
            name, _, value = tok.partition("=")
        elif (
            not tok.startswith("--")
            and tok[:2] in GH_API_FLAGS_WITH_ARG
            and len(tok) > 2
        ):
            name, value = tok[:2], tok[2:].removeprefix("=")  # -XPUT, -X=PUT
        if name in GH_API_FLAGS_WITH_ARG:
            if value is None:
                value = args[i] if i < len(args) else ""
                i += 1
            if name in ("-X", "--method"):
                method = value
            elif name in ("-f", "-F", "--field", "--raw-field"):
                fields.append(value)
            has_input |= name == "--input"
        elif not tok.startswith("-"):
            positionals.append(tok)
    if method is None:
        method = "POST" if fields or has_input else "GET"
    endpoint = positionals[0] if positionals else ""
    endpoint = GH_API_HOST_RE.sub("", endpoint).strip("/")
    return method.upper(), endpoint, fields, has_input


def gh_api_reason(args):
    """What a `gh api` call does that `gh pr merge` & co. would be blocked
    for, or None. Only the endpoints below are recognized."""
    method, endpoint, fields, has_input = gh_api_request(args)
    if endpoint == "graphql":
        text = " ".join(args)
        for mutation, label in GH_GRAPHQL_MUTATIONS.items():
            if mutation in text:
                return f"GraphQL {mutation}({label})"
        return None
    if method == "GET":
        return None
    for pattern, methods, label in GH_API_RULES:
        if method in methods and re.fullmatch(pattern, endpoint):
            return f"{method} {endpoint}({label})"
    if method == "PATCH" and re.fullmatch(GH_API_CLOSABLE, endpoint):
        if has_input or "state=closed" in fields:
            return f"PATCH {endpoint} state=closed(pr/issue close)"
    return None


def check_gh_destructive(segments, command):
    for args in gh_invocations(segments):
        words, rest = gh_command_words(args)
        if words in GH_DESTRUCTIVE:  # ---- 15
            noun, verb = words
            deny(f"[git-safety] 'gh {noun} {verb}' 계열 명령은 금지됩니다: {command}")
        if words[:1] == ("api",):
            reason = gh_api_reason(rest)
            if reason:
                deny(
                    f"[git-safety] 'gh api'로 {reason}을 하는 것은 금지됩니다 "
                    f"(gh pr merge 등과 같은 작업): {command}"
                )


def check_gh_unparsable(command):
    """Conservative judgement for a line that can't be tokenized: block if
    the words of a destructive gh operation appear anywhere in it."""
    text = prepare(command)
    if not re.search(r"\bgh\b", text):
        return
    words = set(re.findall(r"[A-Za-z]+", text))
    risky = any(noun in words and verb in words for noun, verb in GH_DESTRUCTIVE)
    if "api" in words and GH_API_UNPARSABLE_RE.search(text):
        risky = True
    if risky:
        deny(
            "[git-safety] 명령을 해석할 수 없어(따옴표 불균형 등) 파괴적 gh 작업인지 "
            f"확인할 수 없으므로 보수적으로 차단합니다: {command}"
        )


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    try:
        tokens = tokenize(prepare(command))  # ---- 16
    except ValueError:
        check_unparsable(command)
        check_gh_unparsable(command)
    else:
        segments = split_segments(tokens)
        check_gh_destructive(segments, command)  # no subprocess: judged first
        check_push(tokens, command, data.get("cwd") or os.getcwd())
        check_branch_delete(segments, command)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 bash가 단어를 나누기 전의 줄 모양으로 맞춤
#   설명: 히어독 본문은 명령이 아니라 텍스트이므로 버리고, 백슬래시-개행은 bash처럼 먼저 이어 붙인다. 이 전처리를 빼면 줄 이은 git push origin main 이 토큰으로 갈라져 우회된다.
#   관련: hooks/pre_push_check.py (TASK-34), hooks/dedup_drift_guard.py
#   개념: 히어독, 라인 컨티뉴에이션
# 2 명령 머리 이후의 인용 안 된 git 단어도 판정
#   설명: xargs git push, timeout 60 git push, find -exec git ... 는 실제로 git을 실행한다. 실행기와 출력기(echo git push origin main)를 가르려면 끝이 없는 목록이 필요하므로, 일반 인자 경우는 오탐 차단이 나도 놓치지는 않게 한다. basename 비교라 /usr/bin/git 도 같은 규칙을 받는다.
#   관련: TASK-37, decision-1
#   개념: 보수적 판정
# 3 push 판정용 git 질의는 프롬프트를 띄우지 않는다
#   설명: 훅이 사용자 입력을 기다리며 멈추면 안 된다. 터미널 자격 증명 프롬프트를 끄고 stdin도 닫는다. GIT_PROTOCOL_FROM_USER=0 은 일부러 설정하지 않았다: file 프로토콜이 user 전용이라 로컬 경로 원격까지 막히기 때문이다(ext:: 는 git 기본 정책으로 이미 꺼져 있다).
#   관련: TASK-38
# 4 cd의 효과는 일부 구분자 너머로만 이어진다
#   설명: cd 는 ; && 개행 너머로 이어지지만 | || & 너머로는 이어지지 않는다(서브셸·백그라운드). 닫는 괄호는 스택으로 되돌린다. 이 규칙이 틀리면 push가 실행될 디렉터리를 잘못 짚어 보호 브랜치 판정이 어긋난다.
#   관련: TASK-38
#   개념: 서브셸
# 5 긴 옵션은 접두사로도 인식
#   설명: git은 모호하지 않은 접두사를 긴 옵션으로 받는다(--forc 는 --force). 정확 일치만 보면 접두사 우회로 force 판정을 피할 수 있다.
#   관련: TASK-38
# 6 git 설정을 바꾸는 push는 질의하지 않고 차단
#   설명: git -c, --config-env, --exec-path, GIT_* 환경 지정이 붙으면 사용자 제공 설정이 질의 과정에서 실행될 수 있다. 사람이 명령을 승인하기 전에는 그 설정을 돌리지 않겠다는 결정이며, 호출 쪽이 Unverifiable을 차단으로 바꾼다.
#   관련: TASK-38
#   개념: fail-closed
# 7 와일드카드 refspec은 보호 브랜치 전부로 간주
#   설명: refspec의 * 는 어느 브랜치에 닿을지 풀어 보지 않고 보수적으로 main/master에 닿는 것으로 본다.
# 8 remote.<r>.mirror 가 켜져 있으면 모든 브랜치
#   설명: 미러 push는 refspec 없이도 모든 ref를 덮어쓴다. force 로도 취급해(True) 최초 push 예외가 적용되지 않게 한다.
#   관련: TASK-38
# 9 upstream 모드와 미래 모드까지 덮는다
#   설명: upstream/tracking 은 업스트림으로 push 하지만, 브랜치 자신도 함께 판정해 git이 나중에 추가할 수 있는 모드까지 덮는다.
#   관련: TASK-38
# 10 pushInsteadOf 가 있으면 대상 URL을 확정할 수 없다
#   설명: url.*.pushInsteadOf 는 push URL을 바꿔 쓰므로 ls-remote 로 보는 곳과 실제 push 대상이 달라질 수 있다. 확정할 수 없으니 차단한다.
#   관련: TASK-38
#   개념: fail-closed
# 11 옵션처럼 보이는 원격 이름 거부
#   설명: -로 시작하는 원격 이름이 ls-remote 의 옵션으로 해석돼 의도하지 않은 동작을 할 수 있다(옵션 주입). 질의 전에 거부해 차단 쪽으로 보낸다.
#   개념: 옵션 주입
# 12 exit 2 만 '원격에 ref 없음'으로 인정
#   설명: ls-remote --exit-code 의 2 는 ref 부재 증명이다. 0 은 이미 존재, 그 외(네트워크 오류, 알 수 없는 원격, 타임아웃)는 모두 확인 불가로 보고 차단한다. 최초 push 예외가 열리는 유일한 조건이다.
#   관련: TASK-38
#   개념: fail-closed, 최초 push 예외
# 13 최초 push만 main/master 허용
#   설명: 원격에 보호 브랜치가 아직 없을 때만 직접 push를 허용한다. force·삭제는 덮어쓸 것이 없어도 이유가 없으므로 최초 push여도 위에서 이미 차단했다.
#   관련: TASK-38
# 14 확인할 수 없으면 차단
#   설명: 현재 브랜치를 못 읽거나 git 질의가 실패하면 push 대상이 보호 브랜치인지 알 수 없다. 사유를 담아 보수적으로 차단하며, 사용자는 명시적 refspec으로 다시 시도할 수 있다.
#   관련: TASK-38
#   개념: fail-closed
# 15 (명사, 동사) 정확한 짝만 차단
#   설명: gh pr list; git merge --ff-only x 처럼 세그먼트에 흩어진 단어와 gh pr view merge 는 통과시킨다. 옛 줄 전체 스캔이 이를 오차단했다. gh api 는 같은 작업을 REST·GraphQL 로 하는 경우를 따로 본다.
#   관련: TASK-45
# 16 해석 실패 시 보수적 폴백
#   설명: 따옴표 불균형 등으로 토큰화가 실패하면 명령 위치와 텍스트를 구분할 수 없다. 이전 코드는 이 경우 git 명령 없음으로 보고 통과(fail-open)해서 git push origin main "x 가 새어 나갔다. 이제 git+push/branch+main/master 단어가 함께 있으면 차단하고, gh도 같은 방식으로 본다. 오차단은 따옴표를 고쳐 재시도하면 되지만 보호 브랜치로의 누락은 복구할 수 없다.
#   관련: TASK-37 (AC3), TASK-45
#   개념: fail-closed
