#!/usr/bin/env python3
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

Known gaps (decision-1): `bash -c "git push origin main"`, `eval`, aliases,
scripts, and backtick/`$(...)` substitution are not seen. The `gh` checks
are unchanged by TASK-37.

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
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
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
            if tok.strip("()") not in ("|", "||", "&"):
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
            if not eq and any(long_option_is(name, o) for o in PUSH_LONG_WITH_ARG):
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
            raise Unverifiable("git -c/--exec-path/GIT_* 환경변수가 붙은 push")
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
        return set(PROTECTED_BRANCHES)
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
    if ctx.get(f"remote.{remote}.mirror", "false").lower() in TRUE_VALUES:
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
    # upstream/tracking push to the upstream; the branch itself is judged
    # too so any mode git might add later stays covered
    return {branch} | upstream, False


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
    if any(key.endswith(".pushinsteadof") for key in config):
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
        if url.startswith("-"):
            raise Unverifiable("옵션처럼 보이는 원격 이름")
        code, _ = ctx.git(["ls-remote", "--exit-code", "--heads", url, *patterns])
        if code == 0:
            return False
        if code != 2:
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
        if remote_lacks_branches(ctx, remote, targets):
            return None  # first push: nothing on the remote to protect yet
        return f"'{names}' 브랜치로 직접 push하는 것은 금지됩니다 (원격에 이미 존재)"
    except Unverifiable as exc:
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

    try:
        tokens = tokenize(prepare(command))
    except ValueError:
        check_unparsable(command)
    else:
        check_push(tokens, command, data.get("cwd") or os.getcwd())
        check_branch_delete(split_segments(tokens), command)
    check_gh_destructive(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
