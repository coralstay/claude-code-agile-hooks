"""TASK-43: contract between settings.hooks.json and the hook files as
Claude Code really runs them.

Unit tests call each hook's main() in-process, so they can't see what only
the installed form shows: a registered command pointing at a missing file,
a hook that imports something install.sh doesn't copy (only hooks/*.py
is installed), a crash on an empty or broken stdin, an exit code Claude Code
reads as "block" where the hook meant "pass". This file checks that form:

1. Files: every registered command is `python3 $HOME/.claude/hooks/
   claude-rails/<name>.py` with an existing hooks/<name>.py, every hook has
   a hooks/test_<name>.py, and every hook is registered somewhere (or is
   listed in UNREGISTERED_BY_DESIGN with a reason).
2. Runtime: every (event, tool) registration is run the way Claude Code
   runs it - the hook files copied to $HOME/.claude/hooks/claude-rails as
   install.sh does, the registered command string run through `sh -c` -
   with an empty stdin, malformed JSON and a minimal valid payload for the
   event. No traceback, exit code 0 (EXPECTED_EXIT lists reasoned
   exceptions), stdout that looks like JSON must be JSON.

Isolation: HOME, TMPDIR, XDG_* and the CC_* override directories point
into the test's tmp_path, cwd is a tmp directory that is not a git repo,
and nothing but PATH is inherited (no GIT_*, CLAUDE_* or hook switches from
the session running the tests). Files the hooks create must land under the
tmp HOME's log directories.

The `if` filters are covered by hooks/test_hook_registration_contract.py;
this file doesn't repeat them."""

import json
import os
import re
import shutil
import subprocess

import pytest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS_DIR)
SETTINGS = os.path.join(REPO_ROOT, "settings.hooks.json")
COMMAND_RE = re.compile(
    r"^python3 \$HOME/\.claude/hooks/claude-rails/([a-z0-9_]+)\.py$"
)
INSTALL_SUBDIR = os.path.join(".claude", "hooks", "claude-rails")
RUN_TIMEOUT = 20

# hook files deliberately not registered in settings.hooks.json: name -> reason
UNREGISTERED_BY_DESIGN = {}

# (hook, event, input kind) -> exit code other than 0, with the reason.
# Input kinds: "empty", "malformed", "valid". Empty for now: every hook
# passes a benign payload in a non-repo directory and fails open on bad
# input.
EXPECTED_EXIT = {}

# what each matcher alternative's tool call looks like in a payload
TOOL_INPUTS = {
    "Bash": lambda cwd: {"command": "ls", "description": "list files"},
    "Edit": lambda cwd: {
        "file_path": os.path.join(cwd, "notes.txt"),
        "old_string": "a",
        "new_string": "b",
    },
    "Write": lambda cwd: {
        "file_path": os.path.join(cwd, "notes.txt"),
        "content": "hello\n",
    },
    "Read": lambda cwd: {"file_path": os.path.join(cwd, "notes.txt")},
    "Grep": lambda cwd: {"pattern": "hello", "path": cwd},
    "Glob": lambda cwd: {"pattern": "*.txt", "path": cwd},
}
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"}
DEFAULT_TOOL = "Bash"


def load_settings():
    with open(SETTINGS) as f:
        return json.load(f)


def registered_commands():
    """(event, matcher, command string) for every hook in settings.hooks.json."""
    out = []
    for event, groups in load_settings()["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                out.append((event, group.get("matcher"), hook["command"]))
    return out


def hook_name(command):
    m = COMMAND_RE.match(command)
    return m.group(1) if m else None


def hook_files():
    return sorted(
        f.removesuffix(".py")
        for f in os.listdir(HOOKS_DIR)
        if f.endswith(".py") and not f.startswith("test_")
    )


def tools_for(event, matcher):
    """The tool names a registration is run with: each alternative of a
    tool matcher, Bash for a tool event without a matcher, none otherwise
    (ConfigChange's matcher is a config source, not a tool)."""
    if event not in TOOL_EVENTS:
        return [None]
    if matcher is None:
        return [DEFAULT_TOOL]
    return matcher.split("|")


def runtime_cases():
    cases = set()
    for event, matcher, command in registered_commands():
        for tool in tools_for(event, matcher):
            cases.add((hook_name(command), event, tool, command))
    return sorted(cases, key=lambda c: (c[0], c[1], c[2] or ""))


# --- 1. files ---


@pytest.mark.parametrize("event, matcher, command", registered_commands())
def test_registered_command_points_to_an_existing_hook(event, matcher, command):
    name = hook_name(command)
    assert name, (
        f"{event} command {command!r} is not `python3 $HOME/.claude/hooks/"
        "claude-rails/<name>.py` - install.sh only installs that layout"
    )
    assert os.path.isfile(os.path.join(HOOKS_DIR, f"{name}.py")), (
        f"{event} registers {name}.py, which is not in hooks/"
    )


def test_registered_tool_matchers_are_known_tools():
    unknown = sorted(
        {
            tool
            for event, matcher, _ in registered_commands()
            if event in TOOL_EVENTS and matcher
            for tool in matcher.split("|")
        }
        - set(TOOL_INPUTS)
    )
    assert not unknown, f"add a payload for these tools to TOOL_INPUTS: {unknown}"


@pytest.mark.parametrize("name", hook_files())
def test_every_hook_has_a_test_file(name):
    assert os.path.isfile(os.path.join(HOOKS_DIR, f"test_{name}.py"))


def test_every_hook_is_registered_or_unregistered_by_design():
    registered = {hook_name(c) for _, _, c in registered_commands()}
    unregistered = sorted(set(hook_files()) - registered - set(UNREGISTERED_BY_DESIGN))
    assert not unregistered, (
        f"hooks/ files not in settings.hooks.json: {unregistered} - register "
        "them or list them in UNREGISTERED_BY_DESIGN with the reason"
    )
    for name, reason in UNREGISTERED_BY_DESIGN.items():
        assert reason.strip() and name in hook_files() and name not in registered


def test_expected_exit_exceptions_are_for_real_cases():
    known = {(name, event) for name, event, _, _ in runtime_cases()}
    for (name, event, kind), (code, reason) in EXPECTED_EXIT.items():
        assert (name, event) in known and kind in KINDS
        assert code != 0 and reason.strip()


# --- 2. runtime ---

KINDS = ("empty", "malformed", "valid")


def payload(event, tool, cwd, transcript):
    data = {
        "session_id": "contract-test-session",
        "transcript_path": transcript,
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": event,
    }
    if tool is not None:
        data["tool_name"] = tool
        data["tool_input"] = TOOL_INPUTS[tool](cwd)
        data["tool_use_id"] = "toolu_contract"
    if event == "PostToolUse":
        data["tool_response"] = {"success": True}
    if event == "PostToolUseFailure":
        data["error"] = "contract test failure"
    if event == "UserPromptSubmit":
        data["prompt"] = "hello"
    if event == "SessionStart":
        data["source"] = "startup"
    if event == "SessionEnd":
        data["reason"] = "other"
    if event == "Stop":
        data["stop_hook_active"] = False
    if event == "PreCompact":
        data["trigger"] = "manual"
        data["custom_instructions"] = ""
    if event == "ConfigChange":
        data["source"] = "user_settings"
        data["file_path"] = os.path.join(cwd, "settings.json")
    if event == "InstructionsLoaded":
        data["file_path"] = os.path.join(cwd, "CLAUDE.md")
        data["memory_type"] = "Project"
        data["load_reason"] = "session_start"
    return data


def stdin_for(kind, event, tool, cwd, transcript):
    if kind == "empty":
        return ""
    if kind == "malformed":
        return '{"hook_event_name": "' + event + '", "tool_input": {'
    return json.dumps(payload(event, tool, cwd, transcript))


@pytest.fixture
def sandbox(tmp_path):
    """A tmp HOME with the hooks installed the way install.sh lays them
    out, a non-repo working directory with a transcript, and an
    environment that inherits nothing but PATH."""
    home = tmp_path / "home"
    install_dir = home / INSTALL_SUBDIR
    install_dir.mkdir(parents=True)
    for f in os.listdir(HOOKS_DIR):
        if f.endswith(".py"):
            shutil.copy2(os.path.join(HOOKS_DIR, f), install_dir / f)
    work = tmp_path / "work"
    work.mkdir()
    (work / "notes.txt").write_text("hello\n")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}})
        + "\n"
    )
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "CC_HOOK_FLAGS_DIR": str(tmp_path / "flags"),
        "CC_PIPELINE_DIR": str(tmp_path / "pipeline"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return {
        "root": tmp_path,
        "home": home,
        "install_dir": install_dir,
        "work": work,
        "transcript": str(transcript),
        "env": env,
    }


def run_registered(sandbox, command, stdin):
    return subprocess.run(
        ["sh", "-c", command],
        input=stdin,
        cwd=sandbox["work"],
        env=sandbox["env"],
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )


def files_under(path):
    return {
        os.path.join(dirpath, f) for dirpath, _, files in os.walk(path) for f in files
    }


@pytest.mark.parametrize(
    "name, event, tool, command",
    runtime_cases(),
    ids=[f"{n}-{e}-{t}" if t else f"{n}-{e}" for n, e, t, _ in runtime_cases()],
)
def test_registered_hook_runs_cleanly_as_a_subprocess(
    sandbox, name, event, tool, command
):
    before = files_under(sandbox["root"])
    for kind in KINDS:
        stdin = stdin_for(
            kind, event, tool, str(sandbox["work"]), sandbox["transcript"]
        )
        result = run_registered(sandbox, command, stdin)
        where = f"{name} on {event}/{tool} with {kind} stdin"
        assert "Traceback" not in result.stderr, f"{where} crashed:\n{result.stderr}"
        expected, _ = EXPECTED_EXIT.get((name, event, kind), (0, ""))
        assert result.returncode == expected, (
            f"{where} exited {result.returncode} (expected {expected}):\n"
            f"stdout: {result.stdout[-800:]}\nstderr: {result.stderr[-800:]}"
        )
        out = result.stdout.strip()
        if out.startswith("{"):
            json.loads(out)  # Claude Code parses a JSON-looking stdout
    # the hooks may only write into the tmp HOME's log/state directories
    # (and the CC_* overrides): never into the working directory
    allowed = (
        os.path.join(str(sandbox["home"]), ".claude", "hooks-logs") + os.sep,
        sandbox["env"]["CC_HOOK_FLAGS_DIR"] + os.sep,
        sandbox["env"]["CC_PIPELINE_DIR"] + os.sep,
        sandbox["env"]["TMPDIR"] + os.sep,
    )
    created = sorted(
        p
        for p in files_under(sandbox["root"]) - before
        if not p.startswith(allowed) and "__pycache__" not in p
    )
    assert not created, f"{name} wrote outside its log directories: {created}"


def test_sandbox_redirects_the_default_log_paths(sandbox):
    """The isolation is real: a hook that logs under ~/.claude/hooks-logs
    writes into the tmp HOME (if HOME were ignored this would land in the
    real one)."""
    command = "python3 $HOME/.claude/hooks/claude-rails/session_logger.py"
    stdin = stdin_for(
        "valid", "UserPromptSubmit", None, str(sandbox["work"]), sandbox["transcript"]
    )
    result = run_registered(sandbox, command, stdin)
    assert result.returncode == 0, result.stderr
    logs = sandbox["home"] / ".claude" / "hooks-logs" / "sessions"
    assert (logs / "contract-test-session.jsonl").is_file()


def test_sandbox_inherits_nothing_but_path(sandbox, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/nonexistent")
    result = subprocess.run(
        ["sh", "-c", "env"],
        cwd=sandbox["work"],
        env=sandbox["env"],
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    names = {
        line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line
    }
    assert not {n for n in names if n.startswith(("GIT_DIR", "CLAUDE_"))}
    assert f"HOME={sandbox['home']}" in result.stdout.splitlines()
