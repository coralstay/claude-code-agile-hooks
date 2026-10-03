"""TASK-46: contract between settings.hooks.json's `if` filters and the
commands each hook is built to act on.

Incident (2026-10-03): pre_git_safety_check.py was registered with
`if: Bash(git *)`, but its gh check is about gh commands - so
`cd <repo> && gh pr merge 46` never started the hook and the PR was merged.
Nothing compared the registration with what the hook inspects.

This test does. CONTRACT lists, per hook, representative commands the hook
acts on - each one is first confirmed by calling the hook's own detection
function, so the table can't drift from the code - and every such command
must pass the hook's `if` filter as Claude Code evaluates it. A hook may
accept specific hidden commands only through an explicit, reasoned entry in
`hidden_ok`.

Claude Code's `if` matching, measured 2026-10-04 in a live session with the
installed settings (pre_push_check.py registered with `if: Bash(git *)`):

- `git push --dry-run nonexistent-remote-x some-branch`      -> hook ran
- `true && git push --dry-run nonexistent-remote-x some-branch` -> hook ran
- `/usr/bin/git push --dry-run nonexistent-remote-x some-branch` -> hook did
  NOT run (the command executed)
- `FOO=1 git push --dry-run nonexistent-remote-x some-branch`  -> hook ran
- `echo x | git push --dry-run nonexistent-remote-x some-branch` -> hook ran

So the rule is matched per subcommand of a compound line (pipes included),
by text prefix after leading env assignments, without normalizing the
executable path. if_filter_matches() simulates exactly that and nothing
more: wrappers (`sudo git push`) are treated as not matching, which was not
measured - the conservative reading for this contract. Re-measure and
update the simulator if Claude Code changes."""

import json
import os
import re
import shlex

import pytest

import backlog_commit_scope
import dedup_drift_guard
import pr_provenance_stamp
import pre_commit_check
import pre_git_safety_check
import pre_push_check
import pre_push_coverage_check
import require_draft_first

SETTINGS = os.path.join(os.path.dirname(__file__), os.pardir, "settings.hooks.json")
SEPARATOR_CHARS = set(";&|()\n")
RULE_RE = re.compile(r"^Bash\((.+)\)$")
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


# --- simulator of Claude Code's `if` matching (measured 2026-10-04) ---


def subcommands(command):
    """The subcommands of a Bash line, split on ; && || | & ( ) and
    newlines, each re-joined as plain text."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments = [[]]
    for tok in lexer:
        if tok and set(tok) <= SEPARATOR_CHARS:
            segments.append([])
        else:
            segments[-1].append(tok)
    # measured: leading env assignments don't hide the command from the rule
    stripped = []
    for s in segments:
        while s and ASSIGNMENT_RE.match(s[0]):
            s = s[1:]
        stripped.append(s)
    return [" ".join(s) for s in stripped if s]


def rule_matches(pattern, text):
    """`git *` -> `git` alone or followed by a space; `gh pr create*` ->
    plain text prefix; anything else -> exact text."""
    if pattern.endswith(" *"):
        word = pattern[:-2]
        return text == word or text.startswith(word + " ")
    if pattern.endswith("*"):
        return text.startswith(pattern[:-1])
    return text == pattern


def if_filter_matches(rule, command):
    """True if Claude Code would start a hook registered with `if: rule`
    for this Bash command. `rule` None means no filter: always runs."""
    if rule is None:
        return True
    m = RULE_RE.match(rule)
    assert m, f"unsupported if rule (extend the simulator): {rule}"
    return any(rule_matches(m.group(1), sub) for sub in subcommands(command))


# --- detection functions: does the hook act on this command? ---


def git_safety_blocks(command):
    """pre_git_safety_check's subprocess-free checks (gh destructive ops,
    protected branch deletion)."""
    segments = pre_git_safety_check.parse_segments(command)
    try:
        pre_git_safety_check.check_gh_destructive(segments, command)
        pre_git_safety_check.check_branch_delete(segments, command)
    except SystemExit as exc:
        return exc.code == 2
    return False


def stamps_pr(command):
    return bool(
        pr_provenance_stamp.GH_PR_CREATE_RE.search(command)
        and pr_provenance_stamp.stamp_command(command, "R") is not None
    )


PUSHES = [
    "git push origin x",
    "/usr/bin/git push origin x",
    "cd y && git push",
    "git -C repo push origin x",
    "FOO=1 git push origin x",
]
COMMITS = [
    "git commit -m x",
    "/usr/bin/git commit -m x",
    "cd y && git commit -m x",
    "git -C repo commit -m x",
    "FOO=1 git commit -m x",
]

# hook script name -> detection function, commands it must act on, and
# commands its filter may hide (each with the reason the gap is accepted).
CONTRACT = {
    # gates and security hooks: registered without `if`
    "pre_git_safety_check": {
        "detects": git_safety_blocks,
        "acts_on": [
            "cd x && gh pr merge 1",  # the TASK-46 incident line
            "/usr/bin/gh pr merge 1",
            "gh pr view 5 && gh pr merge 5",
            "git branch -D main",
            "/usr/bin/git branch -D main",
        ],
    },
    "pre_commit_check": {
        "detects": lambda c: pre_commit_check.command_runs_git(c, "commit"),
        "acts_on": COMMITS,
    },
    "backlog_commit_scope": {
        "detects": lambda c: backlog_commit_scope.command_runs_git(c, "commit"),
        "acts_on": COMMITS,
    },
    "pre_push_check": {
        "detects": pre_push_check.command_invokes_git_push,
        "acts_on": PUSHES,
    },
    # TASK-46: denies the push when the opted-in coverage command fails,
    # so it is registered like the other gates (no `if`)
    "pre_push_coverage_check": {
        "detects": lambda c: pre_push_coverage_check.command_runs_git(c, "push"),
        "acts_on": PUSHES,
    },
    "require_draft_first": {
        "detects": require_draft_first.command_invokes_backlog_task_create,
        "acts_on": [
            "backlog task create x",
            "cd y && backlog task create x",
            "/usr/local/bin/backlog task create x",
        ],
    },
    # filtered on purpose: the gaps below are accepted
    "dedup_drift_guard": {
        "detects": lambda c: dedup_drift_guard.command_invokes_git_subcommand(
            c, "commit"
        ),
        "acts_on": COMMITS,
        "hidden_ok": {
            "/usr/bin/git commit -m x": (
                "drift detector for this repo, not a security control - "
                "hooks/test_dedup_registry.py catches the same drift in the "
                "test suite, so a path-qualified commit only skips the "
                "early warning"
            ),
        },
    },
    "pr_provenance_stamp": {
        "detects": stamps_pr,
        "acts_on": [
            "gh pr create --title t --body b",
            "cd y && gh pr create --title t --body b",
            "/usr/bin/gh pr create --title t --body b",
        ],
        "hidden_ok": {
            "/usr/bin/gh pr create --title t --body b": (
                "cosmetic receipt in the PR body - a missing stamp blocks "
                "nothing, and the hook already prefers a missing stamp to a "
                "broken command"
            ),
        },
    },
}

# Bash hooks that act on no particular command family (every line can
# matter), so any `if` would hide something: they must stay unfiltered.
UNFILTERED_BY_DESIGN = {
    "block_dangerous_commands": "any command may be dangerous",
    "case_insensitive_guard": "any deleting command, under any name",
    "protect_secrets": "any command may read a secret",
    "protect_tests": "any command may edit a test",
    "config_guard": "any command may edit settings",
    "instructions_audit": "audits every tool call",
}


def registrations():
    """(event, matcher, hook name, if rule or None) for every hook in
    settings.hooks.json."""
    with open(SETTINGS) as f:
        settings = json.load(f)
    out = []
    for event, groups in settings["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                script = hook["command"].split()[-1]
                name = os.path.basename(script).removesuffix(".py")
                out.append((event, group.get("matcher"), name, hook.get("if")))
    return out


def if_rules():
    return {name: rule for _, _, name, rule in registrations() if rule is not None}


def bash_hooks():
    """Hooks registered for PreToolUse on a matcher that covers Bash."""
    return {
        name
        for event, matcher, name, _ in registrations()
        if event == "PreToolUse" and (matcher is None or "Bash" in matcher.split("|"))
    }


# --- the simulator itself, pinned to the measured results ---


@pytest.mark.parametrize(
    "command, expected",
    [
        ("git push --dry-run nonexistent-remote-x some-branch", True),
        ("true && git push --dry-run nonexistent-remote-x some-branch", True),
        ("/usr/bin/git push --dry-run nonexistent-remote-x some-branch", False),
        ("FOO=1 git push --dry-run nonexistent-remote-x some-branch", True),
        ("echo x | git push --dry-run nonexistent-remote-x some-branch", True),
        # the incident: no git subcommand at all
        ("cd x && gh pr merge 1", False),
        ("git", True),
        ("gitk", False),
    ],
)
def test_simulator_reproduces_measured_git_rule(command, expected):
    assert if_filter_matches("Bash(git *)", command) is expected


def test_simulator_prefix_rule_and_no_filter():
    assert if_filter_matches("Bash(gh pr create*)", "x; gh pr create --fill")
    assert not if_filter_matches("Bash(gh pr create*)", "gh pr list")
    assert if_filter_matches("Bash(ls)", "ls")
    assert not if_filter_matches("Bash(ls)", "ls -la")
    assert if_filter_matches(None, "anything at all")


def test_simulator_rejects_unknown_rule_form():
    with pytest.raises(AssertionError):
        if_filter_matches("Edit(*.py)", "x")


# --- the contract ---


def test_every_filtered_hook_has_a_contract():
    missing = sorted(set(if_rules()) - set(CONTRACT))
    assert not missing, (
        f"hooks with an `if` filter but no CONTRACT entry: {missing} - list "
        "the commands they act on so the filter can be checked"
    )


def test_contract_entries_are_registered():
    registered = {name for _, _, name, _ in registrations()}
    stale = sorted((set(CONTRACT) | set(UNFILTERED_BY_DESIGN)) - registered)
    assert not stale


def test_bash_hooks_are_all_classified():
    unclassified = sorted(bash_hooks() - set(CONTRACT) - set(UNFILTERED_BY_DESIGN))
    assert not unclassified, (
        f"PreToolUse Bash hooks in neither CONTRACT nor UNFILTERED_BY_DESIGN: "
        f"{unclassified}"
    )


@pytest.mark.parametrize("name", sorted(UNFILTERED_BY_DESIGN))
def test_hooks_without_a_command_family_have_no_filter(name):
    assert name not in if_rules()


def test_pre_git_safety_check_has_no_filter():
    """TASK-46 regression: the gh check must see `cd x && gh pr merge 1`.
    (main()-level block: test_pre_git_safety_check.py
    test_blocks_gh_destructive_in_any_command_form.)"""
    assert "pre_git_safety_check" not in if_rules()
    assert git_safety_blocks("cd x && gh pr merge 1")


ALL_CASES = [
    (name, command)
    for name, spec in sorted(CONTRACT.items())
    for command in spec["acts_on"]
]
EXEMPT_CASES = [
    (name, command)
    for name, spec in sorted(CONTRACT.items())
    for command in spec.get("hidden_ok", {})
]
CHECKED_CASES = [case for case in ALL_CASES if case not in EXEMPT_CASES]


@pytest.mark.parametrize("name, command", ALL_CASES)
def test_hook_acts_on_listed_command(name, command):
    assert CONTRACT[name]["detects"](command), (
        f"{name} no longer acts on {command!r} - update CONTRACT"
    )


@pytest.mark.parametrize("name, command", CHECKED_CASES)
def test_if_filter_does_not_hide_what_the_hook_acts_on(name, command):
    rule = if_rules().get(name)
    assert if_filter_matches(rule, command), (
        f"{name} acts on {command!r} but its `if: {rule}` filter keeps the "
        "hook from starting - remove the filter or add a reasoned hidden_ok"
    )


@pytest.mark.parametrize("name, command", EXEMPT_CASES)
def test_accepted_gaps_are_real(name, command):
    """No stale exemption: each hidden_ok command is listed in acts_on,
    carries a reason, and really is hidden by the current filter."""
    assert command in CONTRACT[name]["acts_on"]
    assert CONTRACT[name]["hidden_ok"][command].strip()
    assert not if_filter_matches(if_rules().get(name), command)
