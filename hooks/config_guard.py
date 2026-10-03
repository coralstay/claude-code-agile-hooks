#!/usr/bin/env python3
"""PreToolUse (matcher: Bash|Edit|Write)
"Who guards the guards": block the agent from tampering with its own
guardrail configuration (~/.claude/settings.json, ~/.claude/hooks/,
.claude/settings*.json, .mcp.json, plugin manifests). Ported from
karanb192/claude-code-hooks' config-guard plugin (MIT license).

Motivated by two real incidents documented upstream: the Aug 2026 CHAINDROP
npm worm hid its payload in .claude/settings.json, and CVE-2026-25725 let a
sandbox escape by injecting hooks into a settings.json that didn't exist yet
- so *creating* a protected file counts as mutation here, not just editing
an existing one. Reads always pass.

Bash commands are parsed into shell segments (command position, redirects,
heredoc bodies, `$(...)`, `bash -c`/`eval` recursion). A protected path
blocks when it is a write target: a `>`/`>>` redirect, an argument of a
mutating verb (cp/mv/rm/ln/install/chmod/tee/sed -i/...), or anywhere near
an opaque interpreter/downloader (node/ruby/perl/curl/wget, python running
a script file). Python code passed via `-c` or a stdin heredoc is parsed
with `ast` (TASK-35): code that merely *reads* a protected path (open(p),
json.load, read_text) passes, but code that mentions one and contains any
write primitive - or that can't be parsed - blocks, because the target of
`open(p, 'w')` can't be resolved statically. When the command can't be
tokenized, the pre-TASK-35 string rules (including "interpreter + protected
path anywhere") apply unchanged. This is string matching, not syscall
enforcement (decision-1): obfuscated paths can still slip through.

CONFIG_GUARD_ALLOW=true bypasses this for one call (deliberate config edits).

Fully self-contained: no imports from any other file in this repo."""

import ast
import json
import os
import re
import shlex
import sys

PROTECTED_PATH_PATTERNS = [
    r"(^|/)\.claude/settings(\.local)?\.json$",
    r"(^|/)\.claude/hooks/",
    r"(^|/)\.mcp\.json$",
    r"(^|/)\.claude-plugin/plugin\.json$",
    r"(^|/)\.claude/settings\.json$",
]

PROTECTED_RE = re.compile("|".join(f"(?:{p})" for p in PROTECTED_PATH_PATTERNS))

# Same patterns without the trailing end-of-string anchor, so a protected
# path is still recognized when it's embedded mid-string rather than being
# a clean standalone token - e.g. inside a `python3 -c "..."` string literal
# or followed by other arguments after a `curl -o <path> <url>`.
_LOOSE_PATTERNS = [p[:-1] if p.endswith("$") else p for p in PROTECTED_PATH_PATTERNS]
PROTECTED_RE_LOOSE = re.compile("|".join(f"(?:{p})" for p in _LOOSE_PATTERNS))

# Mentions inside code/free text that PROTECTED_RE_LOOSE misses: a relative
# path right after a quote (`open('.claude/settings.json')`), the hooks dir
# without a trailing slash, and path components composed piecewise
# (`os.path.join(home, '.claude', 'settings.json')`).
MENTION_RE = re.compile(
    r"(?<![\w-])\.(?:claude/(?:settings(?:\.local)?\.json|hooks\b)"
    r"|mcp\.json|claude-plugin/plugin\.json)"
    r"|['\"](?:\.claude|\.claude-plugin|\.mcp\.json|settings(?:\.local)?\.json)/?['\"]"
)

# A protected *directory* as a target: `cp x ~/.claude/hooks`, `rm -rf ~/.claude`.
PROTECTED_DIR_RE = re.compile(r"(^|/)\.claude(/hooks)?/?$|(^|/)\.claude-plugin/?$")

# --- legacy (pre-TASK-35) string rules: backstop + fallback when unparsable ---

LEGACY_MUTATING_VERBS = {"rm", "mv", "cp", "truncate", "tee", "dd"}

# General-purpose interpreters/downloaders: any of these can write to (or
# fetch into) a protected path without ever appearing as a mutating verb,
# e.g. `python3 -c "open('~/.claude/settings.json', 'w')..."` or
# `curl -o ~/.claude/hooks/x.py <url>` (TASK-3).
INTERPRETER_VERBS = {"python3", "python", "node", "ruby", "perl", "curl", "wget"}

REDIRECT_TARGET_RE = re.compile(r">" + r">?\s*(\S+)")
SUBCOMMAND_SPLIT_RE = re.compile(r"&&|\|\||;|\|")

# --- segment-level rules ---

MUTATING_VERBS = LEGACY_MUTATING_VERBS | {
    "ln",
    "install",
    "chmod",
    "chown",
    "chgrp",
    "chflags",
    "touch",
    "rsync",
    "scp",
    "unlink",
    "rmdir",
    "mkdir",
    "patch",
    "sponge",
    "ditto",
    "shred",
}
IN_PLACE_VERBS = {"sed", "gsed", "yq"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SOURCE_VERBS = {"source", "."}
# Interpreters/downloaders whose code we don't analyze: any protected
# mention in the segment blocks (TASK-3 rule, now per parsed segment).
OPAQUE_INTERPRETERS = INTERPRETER_VERBS - {"python3", "python"}
PYTHON_RE = re.compile(r"^python[0-9.]*$")
SHELL_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "}"}
RUNNERS = {"timeout", "nice", "xargs", "stdbuf", "doas", "caffeinate", "ionice", "uvx"}
RUNNER_FLAGS_WITH_ARG = {
    "nice": {"-n"},
    "ionice": {"-c", "-n"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-s", "-E", "-a"},
}
RUN_SUBCOMMAND_TOOLS = {"uv", "poetry", "pipx", "pdm"}
MAX_DEPTH = 8

# --- command parsing (tokenize/split_segments/command_head are verbatim
# copies registered in dedup_drift_guard.REGISTRY) ---

SEPARATOR_CHARS = set(";&|()\n")
WRAPPERS = {"env", "sudo", "command", "exec", "time", "nohup", "npx", "bunx"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z0-9_.\-]+)\2")

# --- python code analysis ---

PY_WRITE_CALLS = {
    "write_text",
    "write_bytes",
    "copy",
    "copy2",
    "copyfile",
    "copytree",
    "copymode",
    "copystat",
    "move",
    "rename",
    "renames",
    "remove",
    "removedirs",
    "unlink",
    "rmdir",
    "rmtree",
    "mkdir",
    "makedirs",
    "symlink",
    "link",
    "symlink_to",
    "hardlink_to",
    "link_to",
    "touch",
    "chmod",
    "lchmod",
    "chown",
    "lchown",
    "truncate",
    "ftruncate",
    "system",
    "popen",
    "run",
    "call",
    "check_call",
    "check_output",
    "Popen",
    "getoutput",
    "getstatusoutput",
    "urlretrieve",
    "utime",
    "mkfifo",
    "mknod",
    "setxattr",
    "removexattr",
    "connect",
    "ZipFile",
    "TarFile",
    "FileIO",
    "make_archive",
    "unpack_archive",
    "extract",
    "extractall",
    "fdopen",
    "savetxt",
    "save",
    "to_csv",
    "to_json",
    "sendfile",
    "posix_spawn",
    "posix_spawnp",
    "startfile",
}
PY_STREAM_WRITES = {"write", "writelines"}
PY_DYNAMIC = {
    "exec",
    "eval",
    "compile",
    "__import__",
    "getattr",
    "setattr",
    "globals",
    "vars",
    "import_module",
    "__builtins__",
    "__dict__",
}
PY_DANGEROUS_MODULES = {"ctypes", "importlib", "pty", "cffi"}
PY_MODE_ARG1_MODULES = {
    "io",
    "codecs",
    "builtins",
    "gzip",
    "bz2",
    "lzma",
    "tarfile",
    "zipfile",
}
MODE_RE = re.compile(r"^[rwaxbtU+]*$")


def is_protected_path(path):
    if not path:
        return False
    expanded = os.path.expanduser(path).replace("\\", "/")
    return bool(PROTECTED_RE.search(expanded))


def is_protected_target(token):
    """A protected file, or a protected directory a file could be put into."""
    if is_protected_path(token):
        return True
    expanded = os.path.expanduser(token or "").replace("\\", "/")
    return bool(PROTECTED_DIR_RE.search(expanded))


def mentions_protected(text):
    if not text:
        return False
    text = text.replace("\\", "/")
    return bool(PROTECTED_RE_LOOSE.search(text) or MENTION_RE.search(text))


def legacy_rules(command, interpreters=True):
    """The pre-TASK-35 rules on raw `;`/`&&`/`|`-separated subcommands: a
    redirect target or a mutating verb's own arguments must point at a
    protected path; with `interpreters`, an interpreter verb plus a
    protected path anywhere in the subcommand also blocks."""
    for sub in SUBCOMMAND_SPLIT_RE.split(command):
        sub = sub.strip()
        if not sub:
            continue

        for target in REDIRECT_TARGET_RE.findall(sub):
            if is_protected_path(target):
                return True

        tokens = re.split(r"\s+", sub)
        verb = os.path.basename(tokens[0]) if tokens else ""

        if (
            interpreters
            and verb in INTERPRETER_VERBS
            and PROTECTED_RE_LOOSE.search(sub)
        ):
            return True

        if verb == "sed" and "-i" not in tokens:
            continue
        if verb not in LEGACY_MUTATING_VERBS and verb != "sed":
            continue
        if any(is_protected_path(token) for token in tokens[1:]):
            return True

    return False


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


def extract_heredocs(command):
    """Splits `command` into the shell text without heredoc bodies and the
    list of bodies, in operator order, as (text, delimiter_was_quoted)."""
    kept = []
    bodies = []
    pending = []  # [delimiter, quoted, lines] whose bodies are still open
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0][0]:
                delim, quoted, lines = pending.pop(0)
                bodies.append(("\n".join(lines), quoted))
            else:
                pending[0][2].append(line)
            continue
        kept.append(line)
        pending.extend(
            [m.group(3), bool(m.group(2)), []] for m in HEREDOC_RE.finditer(line)
        )
    bodies.extend(("\n".join(lines), quoted) for _, quoted, lines in pending)
    return "\n".join(kept), bodies


def shell_segments(tokens):
    """split_segments, plus a split at process substitution `<(` / `>(`."""
    out = []
    for seg in split_segments(tokens):
        cur = []
        for tok in seg:
            if tok.endswith("(") and set(tok) <= set("<>("):
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(tok)
        if cur:
            out.append(cur)
    return out


def is_redirect_op(tok):
    return bool(tok) and set(tok) <= set("<>&|") and ("<" in tok or ">" in tok)


def substitution_text(word):
    """The command inside a `$(...)` / backtick substitution that survived
    tokenizing inside a quoted word (e.g. `echo "$(rm x)"`)."""
    idx = word.find("$(")
    if idx >= 0:
        return word[idx + 2 :]
    if "`" in word:
        return word.split("`", 1)[1].replace("`", " ")
    return None


def effective_head(words):
    """(index of the real command, whether it runs under xargs): skips
    assignments/wrappers (command_head), shell keywords and runners like
    `timeout 5`, `nice -n 5`, `xargs -I{}`, `uv run`."""
    i = 0
    under_xargs = False
    while i < len(words):
        j = i + command_head(words[i:])
        if j >= len(words):
            return j, under_xargs
        name = os.path.basename(words[j].lstrip("`"))
        if name in SHELL_KEYWORDS:
            i = j + 1
            continue
        if (
            name in RUN_SUBCOMMAND_TOOLS
            and j + 1 < len(words)
            and words[j + 1] == "run"
        ):
            k = j + 2
            while k < len(words) and words[k].startswith("-"):
                k += 1
            i = k
            continue
        if name in RUNNERS:
            under_xargs = under_xargs or name == "xargs"
            flags_with_arg = RUNNER_FLAGS_WITH_ARG.get(name, set())
            k = j + 1
            while k < len(words) and words[k].startswith("-"):
                k += 2 if words[k] in flags_with_arg else 1
            if name == "timeout" and k < len(words):
                k += 1
            i = k
            continue
        return j, under_xargs
    return len(words), under_xargs


def _is_std_stream(node):
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
        and node.attr in ("stdout", "stderr")
    )


def _is_read_mode(node):
    if node is None:
        return True
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(MODE_RE.match(node.value))
        and not set("wax+") & set(node.value)
    )


def _open_call_writes(call):
    func = call.func
    mode_index = 1
    if isinstance(func, ast.Attribute):
        recv = func.value.id if isinstance(func.value, ast.Name) else None
        if recv in ("os", "posix", "shelve", "dbm"):
            return True
        if recv not in PY_MODE_ARG1_MODULES:
            mode_index = 0  # Path(...).open(mode)
    if any(isinstance(a, ast.Starred) for a in call.args):
        return True
    mode = None
    for kw in call.keywords:
        if kw.arg is None:
            return True
        if kw.arg in ("mode", "flag"):
            mode = kw.value
    if mode is None and len(call.args) > mode_index:
        mode = call.args[mode_index]
    return not _is_read_mode(mode)


def _call_writes(call):
    func = call.func
    if isinstance(func, ast.Name):
        name = func.id
        if name == "open":
            return _open_call_writes(call)
        if name == "print":
            return any(
                kw.arg == "file" and not _is_std_stream(kw.value)
                for kw in call.keywords
            )
    elif isinstance(func, ast.Attribute):
        name = func.attr
        if name == "open":
            return _open_call_writes(call)
        if name in PY_STREAM_WRITES:
            return not _is_std_stream(func.value)
        if name == "dump":
            return not (len(call.args) >= 2 and _is_std_stream(call.args[1]))
        if name == "replace":
            # str.replace(old, new) takes 2+ args; Path.replace(target) 1;
            # os.replace(src, dst) is named explicitly.
            recv_os = isinstance(func.value, ast.Name) and func.value.id == "os"
            return recv_os or len(call.args) + len(call.keywords) == 1
    else:
        return True  # f()() / (lambda: ...)() etc. - can't tell
    return (
        name in PY_WRITE_CALLS
        or name in PY_DYNAMIC
        or name.startswith(("exec", "spawn"))
    )


def _is_write_name(name):
    return (
        name in PY_WRITE_CALLS
        or name in PY_STREAM_WRITES
        or name in PY_DYNAMIC
        or name in ("open", "replace", "dump", "*")
        or name.startswith(("exec", "spawn"))
    )


def python_code_writes(code):
    """True if python `code` contains any primitive that could write a file
    (or run something that could), or if it can't be parsed. Conservative:
    the caller only asks when the code also mentions a protected path."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return True

    call_funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_funcs.add(id(node.func))
            if _call_writes(node):
                return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in PY_DANGEROUS_MODULES for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in PY_DANGEROUS_MODULES:
                return True
            if any(_is_write_name(a.name) for a in node.names):
                return True
        elif id(node) in call_funcs:
            continue
        elif isinstance(node, ast.Name) and (
            node.id in PY_DYNAMIC or node.id == "open"
        ):
            return True  # aliasing: `f = open`, `map(eval, ...)`
        elif isinstance(node, ast.Attribute) and _is_write_name(node.attr):
            return True  # aliasing: `w = shutil.copy`
    return False


def parse_shell_args(args):
    """('code', code, rest) for -c, ('stdin', None, rest) for -s/none,
    ('script', path, rest) otherwise."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a.startswith("--"):
            i += 2 if a in ("--rcfile", "--init-file") else 1
            continue
        if a[:1] in ("-", "+") and len(a) > 1:
            letters = a[1:]
            if "c" in letters:
                code = args[i + 1] if i + 1 < len(args) else ""
                return "code", code, args[i + 2 :]
            if "s" in letters:
                return "stdin", None, args[i + 1 :]
            i += 2 if ("o" in letters or "O" in letters) else 1
            continue
        if a == "-":
            i += 1
            continue
        break
    if i < len(args):
        return "script", args[i], args[i + 1 :]
    return "stdin", None, []


def parse_python_args(args):
    """('code', code, rest) for -c, ('stdin', None, rest) for `-`/none,
    ('opaque', None, rest) for a script file or -m module."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-":
            return "stdin", None, args[i + 1 :]
        if a.startswith("--"):
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            letters = a[1:]
            skip = 1
            for j, ch in enumerate(letters):
                attached = letters[j + 1 :]
                if ch == "c":
                    if attached:
                        return "code", attached, args[i + 1 :]
                    code = args[i + 1] if i + 1 < len(args) else ""
                    return "code", code, args[i + 2 :]
                if ch == "m":
                    return "opaque", None, args[i:]
                if ch in "WX":
                    skip = 1 if attached else 2
                    break
            i += skip
            continue
        return "opaque", None, args[i:]
    return "stdin", None, []


def segment_targets_protected(words, redirs, docs, command, depth):
    recurse = lambda text: bash_targets_protected_config(text, depth + 1)  # noqa: E731

    for op, operand in redirs:
        if ">" in op and is_protected_target(operand):
            return True

    for word in words + [operand for _, operand in redirs]:
        inner = substitution_text(word)
        if inner and recurse(inner):
            return True

    h, under_xargs = effective_head(words)
    if h >= len(words):
        return any(recurse(text) for text, _ in docs)

    verb = os.path.basename(words[h].lstrip("`"))
    args = words[h + 1 :]
    pre = words[:h]

    def any_mention():
        return any(mentions_protected(w) for w in words) or any(
            mentions_protected(text) for text, _ in docs
        )

    def stdin_code_targets(rest, analyze):
        """Code read from stdin: the heredoc/here-string bodies if any,
        otherwise it arrives through a pipe/redirect - opaque."""
        if not docs:
            return mentions_protected(command)
        if any(mentions_protected(w) for w in pre + rest):
            return True
        return any(analyze(text, quoted) for text, quoted in docs)

    is_code_runner = (
        verb in SHELLS
        or verb in SOURCE_VERBS
        or verb == "eval"
        or verb in OPAQUE_INTERPRETERS
        or PYTHON_RE.match(verb)
    )
    if under_xargs and (
        verb in MUTATING_VERBS or verb in IN_PLACE_VERBS or is_code_runner
    ):
        # arguments come from stdin, i.e. from elsewhere in the command
        if mentions_protected(command) or any_mention():
            return True

    if verb in MUTATING_VERBS:
        return any(is_protected_target(a) for a in args)

    if verb in IN_PLACE_VERBS:
        in_place = any(
            a in ("--in-place", "--inplace")
            or a.startswith("--in-place=")
            or (a.startswith("-") and not a.startswith("--") and "i" in a[1:])
            for a in args
        )
        return in_place and any(is_protected_target(a) for a in args)

    if verb in SHELLS:
        kind, code, rest = parse_shell_args(args)
        if kind == "code":
            return recurse(code) or any(mentions_protected(w) for w in pre + rest)
        if kind == "script":
            return any_mention()
        return stdin_code_targets(rest, lambda text, quoted: recurse(text))

    if verb in SOURCE_VERBS:
        if args and args[0] in ("/dev/stdin", "-") and docs:
            return any(recurse(text) for text, _ in docs)
        return any_mention()

    if verb == "eval":
        return recurse(" ".join(args))

    if PYTHON_RE.match(verb):
        kind, code, rest = parse_python_args(args)
        if kind == "opaque":
            return any_mention()
        if kind == "code":
            if any(mentions_protected(w) for w in pre + rest):
                return True
            return mentions_protected(code) and python_code_writes(code)

        def analyze(text, quoted):
            if (
                not quoted
                and ("$(" in text or "`" in text)
                and mentions_protected(text)
            ):
                return True  # unquoted heredoc: the shell runs substitutions first
            return mentions_protected(text) and python_code_writes(text)

        return stdin_code_targets(rest, analyze)

    if verb in OPAQUE_INTERPRETERS:
        return any_mention()

    # Any other command: a heredoc body is stdin data, but it may still end
    # up executed (piped to a shell, saved and run) - scan it as shell.
    return any(recurse(text) for text, _ in docs)


def bash_targets_protected_config(command, _depth=0):
    """True if `command` looks like it writes a protected path. Reads of
    protected paths (cat/cmp/jq/grep, python that only reads) pass."""
    if not command:
        return False
    if _depth > MAX_DEPTH:
        return mentions_protected(command)

    stripped, bodies = extract_heredocs(command)
    # bash joins backslash-newline continuations before parsing words
    stripped = stripped.replace("\\\n", "")

    if legacy_rules(stripped, interpreters=False):
        return True

    try:
        tokens = tokenize(stripped)
    except ValueError:
        return legacy_rules(command)

    parsed = []
    k = 0
    for seg in shell_segments(tokens):
        words, redirs, docs = [], [], []
        i = 0
        while i < len(seg):
            tok = seg[i]
            if is_redirect_op(tok):
                operand = seg[i + 1] if i + 1 < len(seg) else ""
                if tok == "<<":
                    if k >= len(bodies):
                        return legacy_rules(command)
                    docs.append(bodies[k])
                    k += 1
                elif tok == "<<<":
                    docs.append((operand, False))
                redirs.append((tok, operand))
                i += 2
                continue
            words.append(tok)
            i += 1
        parsed.append((words, redirs, docs))

    if k != len(bodies):
        # a `<<` the tokenizer didn't see (e.g. inside "$(cat <<'EOF' ...)"):
        # bodies can't be attributed to commands - use the legacy rules.
        return legacy_rules(command)

    return any(
        segment_targets_protected(words, redirs, docs, command, _depth)
        for words, redirs, docs in parsed
    )


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    if os.environ.get("CONFIG_GUARD_ALLOW") == "true":
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}

    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        if is_protected_path(path):
            deny(f"[config-guard] 자기 자신의 훅/설정 파일 수정은 금지됩니다: {path}")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if bash_targets_protected_config(command):
            deny(
                f"[config-guard] 훅/설정 파일을 변경하는 명령으로 보여 차단되었습니다: {command}"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
