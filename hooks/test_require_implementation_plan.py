import io
import json
import subprocess

import pytest

import require_implementation_plan as rip

SOAP_PLAN = """### Subjective
유저가 원하는 것.

### Objective
확인한 사실.

### Assessment
고른 접근.

### Plan
1. 구현 순서.
"""


def make_card(
    card_id="DRAFT-8",
    status="Draft",
    plan=SOAP_PLAN,
    acs=("첫 기능",),
    dods=("테스트 통과 로그",),
):
    """Raw card file as backlog.md writes it. `plan` None = no Implementation
    Plan section at all; `acs`/`dods` empty = no items."""
    parts = [
        "---",
        f"id: {card_id}",
        "title: 제목",
        f"status: {status}",
        "labels: []",
        "---",
        "",
        "## Description",
        "",
        "<!-- SECTION:DESCRIPTION:BEGIN -->",
        "설명",
        "<!-- SECTION:DESCRIPTION:END -->",
        "",
        "## Acceptance Criteria",
        "<!-- AC:BEGIN -->",
        *[f"- [ ] #{i} {t}" for i, t in enumerate(acs, start=1)],
        "<!-- AC:END -->",
        "",
        "## Definition of Done",
        "<!-- DOD:BEGIN -->",
        *[f"- [ ] #{i} {t}" for i, t in enumerate(dods, start=1)],
        "<!-- DOD:END -->",
    ]
    if plan is not None:
        parts += [
            "",
            "## Implementation Plan",
            "",
            "<!-- SECTION:PLAN:BEGIN -->",
            plan.rstrip("\n"),
            "<!-- SECTION:PLAN:END -->",
        ]
    return "\n".join(parts) + "\n"


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def make_key(directory, name):
    key = directory / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)],
        check=True,
    )
    return key


@pytest.fixture(scope="session")
def keys(tmp_path_factory):
    """Two ssh signing keys; only `trusted` is in the allowed signers file."""
    directory = tmp_path_factory.mktemp("keys")
    trusted = make_key(directory, "trusted")
    stranger = make_key(directory, "stranger")
    allowed = directory / "allowed_signers"
    pub = (directory / "trusted.pub").read_text().split()
    allowed.write_text(f"tester@example.com {pub[0]} {pub[1]}\n")
    return {"trusted": trusted, "stranger": stranger, "allowed": allowed}


@pytest.fixture
def project(tmp_path, monkeypatch, keys):
    """A real git repo with backlog/config.yml, isolated from the user's git
    config."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Tester")
    git(root, "config", "user.email", "tester@example.com")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "gpg.format", "ssh")
    git(root, "config", "gpg.ssh.allowedSignersFile", str(keys["allowed"]))
    git(root, "config", "user.signingkey", str(keys["trusted"]))
    (root / "backlog" / "drafts").mkdir(parents=True)
    (root / "backlog" / "tasks").mkdir(parents=True)
    (root / "backlog" / "config.yml").write_text("project_name: x\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")

    class Project:
        path = root

        def draft(self, text, name="draft-8 - 제목.md"):
            (root / "backlog" / "drafts" / name).write_text(text)

        def task(self, text, name="task-58 - 제목.md"):
            (root / "backlog" / "tasks" / name).write_text(text)

        def go(self, subject="Go: TASK-58", sign=True, key="trusted"):
            """The human's go: an empty commit, signed unless sign=False."""
            args = ["-c", f"user.signingkey={keys[key]}", "commit", "-q"]
            args += ["--allow-empty", "-S" if sign else "--no-gpg-sign", "-m", subject]
            git(root, *args)

    return Project()


def run_main(monkeypatch, cwd, command):
    payload = {
        "cwd": str(cwd),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rip.main()
    return exc_info.value.code


# --- TASK-58#1: draft promote needs a non-empty Implementation Plan ---


def test_promote_denied_without_plan_section(project, monkeypatch, capsys):
    """TASK-58#1"""
    project.draft(make_card(plan=None))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 2
    err = capsys.readouterr().err
    assert err.startswith("[claude-code-agile-hooks]")
    assert "backlog draft edit DRAFT-8 --plan" in err


def test_promote_denied_with_blank_plan(project, monkeypatch, capsys):
    """TASK-58#1"""
    project.draft(make_card(plan="  \n\n"))
    assert run_main(monkeypatch, project.path, "backlog draft promote draft-8") == 2
    assert "backlog draft edit DRAFT-8 --plan" in capsys.readouterr().err


def test_promote_allowed_with_complete_card(project, monkeypatch):
    """TASK-58#1"""
    project.draft(make_card())
    assert run_main(monkeypatch, project.path, "backlog draft promote 8") == 0


def test_promote_of_unknown_draft_passes(project, monkeypatch):
    """TASK-58#1: no card file -> backlog itself reports the error."""
    project.draft(make_card(plan=None))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-9") == 0


def test_promote_passes_outside_backlog_project(tmp_path, monkeypatch):
    """TASK-58#1"""
    assert run_main(monkeypatch, tmp_path, "backlog draft promote DRAFT-8") == 0


def test_other_commands_pass(project, monkeypatch):
    """TASK-58#1"""
    assert run_main(monkeypatch, project.path, "ls -la") == 0
    assert run_main(monkeypatch, project.path, "backlog draft promote") == 0


def test_invalid_payloads_pass(monkeypatch):
    """TASK-58#1"""
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rip.main()
    assert exc_info.value.code == 0
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": "x"}))
    )
    with pytest.raises(SystemExit) as exc_info:
        rip.main()
    assert exc_info.value.code == 0


# --- TASK-58#2: -s "In Progress" needs a plan (second line of defense for
# cards made through the MCP server / web UI, which skip draft promote) ---

TASK = dict(card_id="TASK-58", status="To Do")


@pytest.mark.parametrize(
    "command",
    [
        'backlog task edit TASK-58 -s "In Progress"',
        "backlog task edit task-58 --status 'In Progress'",
        "backlog task edit 58 --status='in progress'",
        'backlog task edit TASK-58 --plain -s "In Progress"',
    ],
)
def test_start_denied_without_plan(project, monkeypatch, capsys, command):
    """TASK-58#2: a task file written directly (MCP / web UI) has no plan."""
    project.task(make_card(plan=None, **TASK))
    assert run_main(monkeypatch, project.path, command) == 2
    assert "backlog task edit TASK-58 --plan" in capsys.readouterr().err


def test_start_denied_with_blank_plan(project, monkeypatch):
    """TASK-58#2"""
    project.task(make_card(plan="\n \n", **TASK))
    command = 'backlog task edit TASK-58 -s "In Progress"'
    assert run_main(monkeypatch, project.path, command) == 2


def test_other_status_moves_and_edits_pass(project, monkeypatch):
    """TASK-58#2: only the In Progress move is gated."""
    project.task(make_card(plan=None, **TASK))
    for command in [
        "backlog task edit TASK-58 -s Done",
        "backlog task edit TASK-58 --plan x",
        "backlog task edit TASK-58 -s",
        'backlog task edit -s "In Progress"',
        "backlog task view TASK-58 --plain",
    ]:
        assert run_main(monkeypatch, project.path, command) == 0, command


def test_start_of_unknown_task_passes(project, monkeypatch):
    """TASK-58#2"""
    project.task(make_card(plan=None, **TASK))
    command = 'backlog task edit TASK-99 -s "In Progress"'
    assert run_main(monkeypatch, project.path, command) == 0


# --- TASK-58#3: the plan has the four SOAP reserved headings, in order,
# once each, each with a non-blank body ---

S, O, A, P = "### Subjective", "### Objective", "### Assessment", "### Plan"


def plan_of(*blocks):
    return "\n".join(blocks) + "\n"


@pytest.mark.parametrize(
    "plan, expected",
    [
        (SOAP_PLAN, []),
        # trailing whitespace on a heading line is invisible: still the heading
        (plan_of(S + "  ", "a", O, "b", A, "c", P + "\r", "d"), []),
        # text before the first heading is allowed
        (plan_of("머리말", S, "a", O, "b", A, "c", P, "d"), []),
        # sub-headings and blank lines inside a body are body
        (plan_of(S, "", "#### 세부", "a", O, "b", A, "c", P, "d"), []),
        (plan_of(S, "a", O, "b", A, "c"), ["빠진 제목: ### Plan"]),
        (plan_of("본문만"), ["빠진 제목: ### Subjective, ### Objective, ### Assessment, ### Plan"]),
        (plan_of(S, "a", O, "  ", A, "c", P, "d"), ["본문이 빈 제목: ### Objective"]),
        (plan_of(S, "a", O, "b", A, "c", P), ["본문이 빈 제목: ### Plan"]),
        (
            plan_of(S, "a", O, "b", A, "c", P, "d", O, "e"),
            ["두 번 이상 나온 제목: ### Objective"],
        ),
        (
            plan_of(O, "b", S, "a", A, "c", P, "d"),
            ["순서가 다릅니다: ### Objective → ### Subjective → ### Assessment → ### Plan"],
        ),
        # case / spacing / level variants are not the reserved heading
        (
            plan_of("### subjective", "a", "###  Objective", "b", "## Assessment", "c", "#### Plan", "d"),
            ["빠진 제목: ### Subjective, ### Objective, ### Assessment, ### Plan"],
        ),
        (
            plan_of(" ### Subjective", "a", O, "b", A, "c", P, "d"),
            ["빠진 제목: ### Subjective"],
        ),
    ],
)
def test_soap_problems(plan, expected):
    """TASK-58#3"""
    assert rip.soap_problems(plan) == expected


def test_soap_problems_reports_missing_and_empty_together():
    """TASK-58#3"""
    assert rip.soap_problems(plan_of(S, "", A, "c", P, "d")) == [
        "빠진 제목: ### Objective",
        "본문이 빈 제목: ### Subjective",
    ]


BAD_PLAN = plan_of(S, "a", O, "", A, "c")


def test_promote_denied_on_bad_soap(project, monkeypatch, capsys):
    """TASK-58#3"""
    project.draft(make_card(plan=BAD_PLAN))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 2
    err = capsys.readouterr().err
    assert "빠진 제목: ### Plan" in err
    assert "본문이 빈 제목: ### Objective" in err
    assert "backlog draft edit DRAFT-8 --plan" in err


def test_start_denied_on_bad_soap(project, monkeypatch, capsys):
    """TASK-58#3"""
    project.task(make_card(plan=BAD_PLAN, **TASK))
    command = 'backlog task edit TASK-58 -s "In Progress"'
    assert run_main(monkeypatch, project.path, command) == 2
    err = capsys.readouterr().err
    assert "빠진 제목: ### Plan" in err
    assert "backlog task edit TASK-58 --plan" in err


# --- TASK-58#4: the card needs at least one AC and one DoD item ---


@pytest.mark.parametrize(
    "acs, dods, says",
    [
        ((), ("d",), ["AC"]),
        (("a",), (), ["DoD"]),
        ((), (), ["AC", "DoD"]),
    ],
)
def test_promote_denied_without_ac_or_dod(project, monkeypatch, capsys, acs, dods, says):
    """TASK-58#4"""
    project.draft(make_card(acs=acs, dods=dods))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 2
    err = capsys.readouterr().err
    for word in says:
        assert f"--{'ac' if word == 'AC' else 'dod'}" in err
    if says == ["AC"]:
        assert "--dod" not in err


def test_start_denied_without_dod(project, monkeypatch, capsys):
    """TASK-58#4"""
    project.task(make_card(dods=(), **TASK))
    command = 'backlog task edit TASK-58 -s "In Progress"'
    assert run_main(monkeypatch, project.path, command) == 2
    assert "backlog task edit TASK-58 --dod" in capsys.readouterr().err


def test_checked_items_count_and_marker_less_text_does_not(project, monkeypatch):
    """TASK-58#4: `- [x] #1` counts; a card without AC/DoD markers has none."""
    text = make_card().replace("- [ ] #1 첫 기능", "- [x] #1 첫 기능")
    assert rip.has_items(text, "AC") and rip.has_items(text, "DOD")
    assert not rip.has_items("- [ ] #1 x\n", "AC")


def test_missing_plan_and_items_reported_together(project, monkeypatch, capsys):
    """TASK-58#4"""
    project.draft(make_card(plan=None, acs=()))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 2
    err = capsys.readouterr().err
    assert "--plan" in err and "--ac" in err


# --- TASK-58#5: -s "In Progress" needs the human's go - an empty commit
# with subject exactly `Go: <ID>`, reachable from HEAD, with a valid
# signature (`git log --format=%G?` == G, decision-13) ---

START = 'backlog task edit TASK-58 -s "In Progress"'
GO_COMMAND = 'git commit --allow-empty -S -m "Go: TASK-58"'


def test_start_denied_without_go(project, monkeypatch, capsys):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert GO_COMMAND in err
    assert "--plan" not in err


def test_start_allowed_with_signed_go(project, monkeypatch):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.go()
    assert run_main(monkeypatch, project.path, START) == 0
    # the card's own ID is used, however the command names the task
    assert run_main(monkeypatch, project.path, "backlog task edit 58 -s 'in progress'") == 0


def test_start_denied_with_unsigned_go(project, monkeypatch, capsys):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.go(sign=False)
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "%G? = N" in err
    assert GO_COMMAND in err


def test_start_denied_when_signature_is_not_valid(project, monkeypatch, capsys):
    """TASK-58#5: signed by a key the allowed signers file doesn't know."""
    project.task(make_card(**TASK))
    project.go(key="stranger")
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "%G? = " in err and "%G? = G" not in err


def test_any_valid_go_among_several_counts(project, monkeypatch):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.go(sign=False)
    project.go()
    project.go(sign=False)
    assert run_main(monkeypatch, project.path, START) == 0


@pytest.mark.parametrize(
    "subject",
    ["go: TASK-58", "Go: TASK-5", "Go: TASK-580", "Go: TASK-58 승인", "Go:TASK-58", "Go: 58"],
)
def test_subject_must_be_exact(project, monkeypatch, subject):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.go(subject=subject)
    assert run_main(monkeypatch, project.path, START) == 2


def test_go_on_unmerged_branch_does_not_count(project, monkeypatch):
    """TASK-58#5: only commits reachable from HEAD are searched."""
    project.task(make_card(**TASK))
    git(project.path, "switch", "-q", "-c", "elsewhere")
    project.go()
    git(project.path, "switch", "-q", "main")
    assert run_main(monkeypatch, project.path, START) == 2
    git(project.path, "merge", "-q", "--ff-only", "elsewhere")
    assert run_main(monkeypatch, project.path, START) == 0


def test_show_signature_config_does_not_break_parsing(project, monkeypatch):
    """TASK-58#5"""
    git(project.path, "config", "log.showSignature", "true")
    project.task(make_card(**TASK))
    project.go()
    assert run_main(monkeypatch, project.path, START) == 0


def test_unborn_head_has_no_go(tmp_path, monkeypatch):
    """TASK-58#5: a repo without commits can't hold a go."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "none"))
    git(tmp_path, "init", "-q")
    assert rip.go_status(str(tmp_path), "TASK-58") is None


def test_promote_does_not_need_go(project, monkeypatch):
    """TASK-58#5: go gates only the start of work."""
    project.draft(make_card())
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 0


def test_hook_never_creates_a_go(project, monkeypatch):
    """TASK-58#5: a denied start leaves the history untouched."""
    project.task(make_card(**TASK))
    before = git(project.path, "rev-parse", "HEAD")
    assert run_main(monkeypatch, project.path, START) == 2
    assert git(project.path, "rev-parse", "HEAD") == before
