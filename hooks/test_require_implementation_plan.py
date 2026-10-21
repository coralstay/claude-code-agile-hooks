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
    """Three ssh signing keys. The allowed signers file lists `human` and
    `ai` under separate principals (`human`, `ai-claude-code`); `stranger`
    is not listed at all."""
    directory = tmp_path_factory.mktemp("keys")
    human = make_key(directory, "human")
    ai = make_key(directory, "ai")
    stranger = make_key(directory, "stranger")
    allowed = directory / "allowed_signers"
    lines = []
    for principal, name in (("human", "human"), ("ai-claude-code", "ai")):
        pub = (directory / f"{name}.pub").read_text().split()
        lines.append(f"{principal} {pub[0]} {pub[1]}\n")
    allowed.write_text("".join(lines))
    return {"human": human, "ai": ai, "stranger": stranger, "allowed": allowed}


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
    git(root, "config", "user.signingkey", str(keys["human"]))
    config = root / ".claude-code-agile-hooks.json"
    config.write_text(json.dumps({"humanSigners": ["human"]}))
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

        def config(self, data, name=".claude-code-agile-hooks.json"):
            """Replace the project config; `data` None removes it."""
            config.unlink()
            if data is not None:
                (root / name).write_text(
                    data if isinstance(data, str) else json.dumps(data)
                )

        def approve(self, subject="Plan-Approved: TASK-58", sign=True, key="human"):
            """The plan approval: an empty commit, signed with `key` unless
            sign=False."""
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


# --- TASK-58#5: -s "In Progress" needs the plan approval (decision-14) -
# an empty commit with subject exactly `Plan-Approved: <ID>`, reachable from
# HEAD, with a valid signature (`%G?` == G) whose signer principal (`%GS`)
# is listed in the project config's `humanSigners` ---

START = 'backlog task edit TASK-58 -s "In Progress"'
APPROVAL_COMMAND = 'git commit --allow-empty -S -m "Plan-Approved: TASK-58"'


def test_start_denied_without_approval(project, monkeypatch, capsys):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "'Plan-Approved: TASK-58'인 커밋이 없습니다" in err
    assert APPROVAL_COMMAND in err
    assert "Claude는 계획 승인 커밋을 만들지 않습니다" in err
    assert "--plan" not in err


def test_start_allowed_with_human_signed_approval(project, monkeypatch):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.approve()
    assert run_main(monkeypatch, project.path, START) == 0
    # the card's own ID is used, however the command names the task
    assert run_main(monkeypatch, project.path, "backlog task edit 58 -s 'in progress'") == 0


def test_start_denied_with_unsigned_approval(project, monkeypatch, capsys):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.approve(sign=False)
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "서명이 유효하지 않습니다(%G? = N" in err
    assert APPROVAL_COMMAND in err


def test_start_denied_when_signature_is_not_valid(project, monkeypatch, capsys):
    """TASK-58#5: signed by a key the allowed signers file doesn't know."""
    project.task(make_card(**TASK))
    project.approve(key="stranger")
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "서명이 유효하지 않습니다(%G? = " in err and "%G? = G" not in err


def test_start_denied_when_signed_by_ai_key(project, monkeypatch, capsys):
    """TASK-58#5: a valid signature whose principal is not in humanSigners
    (here the AI key's `ai-claude-code`) is not a human approval."""
    project.task(make_card(**TASK))
    project.approve(key="ai")
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "사람이 아닌 서명자" in err
    assert "%GS = ai-claude-code" in err
    assert "humanSigners" in err


def test_signer_listed_in_human_signers_passes(project, monkeypatch):
    """TASK-58#5: any principal in the list counts."""
    project.config({"humanSigners": ["someone-else", "ai-claude-code"]})
    project.task(make_card(**TASK))
    project.approve(key="ai")
    assert run_main(monkeypatch, project.path, START) == 0


def test_signer_not_listed_in_human_signers_is_denied(project, monkeypatch, capsys):
    """TASK-58#5"""
    project.config({"humanSigners": ["someone-else"]})
    project.task(make_card(**TASK))
    project.approve()
    assert run_main(monkeypatch, project.path, START) == 2
    assert "%GS = human" in capsys.readouterr().err


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"humanSigners": []},
        {"humanSigners": None},
        {"humanSigners": "human"},
        {"humanSigners": ["human", 3]},
        {"humanSigners": [""]},
        ["human"],
        "not json",
        None,
    ],
    ids=["missing", "empty", "null", "string", "non-string", "blank", "not-object", "bad-json", "no-file"],
)
def test_start_denied_without_human_signers(project, monkeypatch, capsys, config):
    """TASK-58#5: no usable humanSigners = deny with setup guidance, even
    when a human-signed approval exists."""
    project.config(config)
    project.task(make_card(**TASK))
    project.approve()
    assert run_main(monkeypatch, project.path, START) == 2
    err = capsys.readouterr().err
    assert "humanSigners" in err
    assert "~/.ssh/allowed_signers" in err
    assert "gpg.ssh.allowedSignersFile" in err
    assert APPROVAL_COMMAND in err


def test_human_signers_read_from_legacy_config(project, monkeypatch):
    """TASK-58#5: legacy .claude-rails.json is read like the other hooks."""
    project.config({"humanSigners": ["human"]}, name=".claude-rails.json")
    project.task(make_card(**TASK))
    project.approve()
    assert run_main(monkeypatch, project.path, START) == 0


def test_any_human_approval_among_several_counts(project, monkeypatch):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.approve(sign=False)
    project.approve(key="ai")
    project.approve()
    project.approve(key="ai")
    assert run_main(monkeypatch, project.path, START) == 0


@pytest.mark.parametrize(
    "subject",
    [
        "plan-approved: TASK-58",
        "Plan-Approved: TASK-5",
        "Plan-Approved: TASK-580",
        "Plan-Approved: TASK-58 승인",
        "Plan-Approved:TASK-58",
        "Plan-Approved: 58",
        "Go: TASK-58",
    ],
)
def test_subject_must_be_exact(project, monkeypatch, subject):
    """TASK-58#5"""
    project.task(make_card(**TASK))
    project.approve(subject=subject)
    assert run_main(monkeypatch, project.path, START) == 2


def test_approval_on_unmerged_branch_does_not_count(project, monkeypatch):
    """TASK-58#5: only commits reachable from HEAD are searched."""
    project.task(make_card(**TASK))
    git(project.path, "switch", "-q", "-c", "elsewhere")
    project.approve()
    git(project.path, "switch", "-q", "main")
    assert run_main(monkeypatch, project.path, START) == 2
    git(project.path, "merge", "-q", "--ff-only", "elsewhere")
    assert run_main(monkeypatch, project.path, START) == 0


def test_show_signature_config_does_not_break_parsing(project, monkeypatch):
    """TASK-58#5"""
    git(project.path, "config", "log.showSignature", "true")
    project.task(make_card(**TASK))
    project.approve()
    assert run_main(monkeypatch, project.path, START) == 0


def test_unborn_head_has_no_approval(tmp_path, monkeypatch):
    """TASK-58#5: a repo without commits can't hold a plan approval."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "none"))
    git(tmp_path, "init", "-q")
    assert rip.approval_status(str(tmp_path), "TASK-58", ["human"]) == ("missing", None)


def test_promote_does_not_need_approval(project, monkeypatch):
    """TASK-58#5: the approval gate guards only the start of work."""
    project.config(None)
    project.draft(make_card())
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 0


def test_hook_never_creates_an_approval(project, monkeypatch):
    """TASK-58#5: a denied start leaves the history untouched."""
    project.task(make_card(**TASK))
    before = git(project.path, "rev-parse", "HEAD")
    assert run_main(monkeypatch, project.path, START) == 2
    assert git(project.path, "rev-parse", "HEAD") == before


# --- TASK-58#6: command position parsing follows require_draft_first.py;
# text inside quotes and heredoc bodies passes ---


@pytest.mark.parametrize(
    "command, expected",
    [
        ("backlog draft promote DRAFT-8", [("promote", "DRAFT-8")]),
        ("backlog drafts promote 8", [("promote", "8")]),
        ("/opt/homebrew/bin/backlog draft promote 8", [("promote", "8")]),
        ("npx backlog.md draft promote 8", [("promote", "8")]),
        ("cd repo && backlog draft promote 8", [("promote", "8")]),
        ("git status;backlog draft promote 8", [("promote", "8")]),
        ("FOO=1 sudo -E backlog draft promote 8", [("promote", "8")]),
        ("(backlog draft promote 8)", [("promote", "8")]),
        ("echo a\nbacklog draft promote 8", [("promote", "8")]),
        ("backlog task edit 1 \\\n  -s 'In Progress'", [("start", "1")]),
        ("backlog tasks edit 1 -s In\\ Progress", [("start", "1")]),
        ('env backlog task edit 1 --status "In  Progress"', [("start", "1")]),
        (
            "backlog draft promote 8 && backlog task edit TASK-1 -s 'In Progress'",
            [("promote", "8"), ("start", "TASK-1")],
        ),
        ('echo "backlog draft promote 8"', []),
        ("echo backlog draft promote 8", []),
        ("grep -rn 'backlog draft promote' .", []),
        ('git commit -m "backlog task edit 1 -s \'In Progress\'"', []),
        ('backlog draft create x -d "그 뒤 backlog draft promote 8"', []),
        ("cat <<'EOF' > notes.md\nbacklog draft promote 8\nEOF", []),
        ('cat <<EOF\nbacklog task edit 1 -s "In Progress"\nEOF\necho done', []),
        ("backlog draft view 8", []),
        ("backlog task edit 1 -s 'In Progress later'", []),
        ("", []),
    ],
)
def test_gated_commands(command, expected):
    """TASK-58#6"""
    assert rip.gated_commands(command) == expected


def test_heredoc_body_skipped_but_command_after_it_still_gated():
    """TASK-58#6"""
    command = "cat <<EOF > a.md\nbacklog draft promote 1\nEOF\nbacklog draft promote 8"
    assert rip.gated_commands(command) == [("promote", "8")]


@pytest.mark.parametrize(
    "command, expected",
    [
        ('backlog draft promote DRAFT-8 "x', [("promote", "DRAFT-8")]),
        ("backlog task edit 1 -s 'In Progress", [("start", "1")]),
        ('cd x && backlog task edit TASK-1 --status="in progress', [("start", "TASK-1")]),
        ('echo "x backlog draft promote 8', []),
        ("backlog task edit 1 -s Done 'x", []),
    ],
)
def test_unbalanced_quotes_fall_back_to_text_match(command, expected):
    """TASK-58#6: a line shlex can't split is matched by text (gate)."""
    assert rip.gated_commands(command) == expected


def test_quoted_mention_passes_main(project, monkeypatch):
    """TASK-58#6"""
    project.draft(make_card(plan=None))
    command = 'git commit -m "backlog draft promote DRAFT-8 막는 훅"'
    assert run_main(monkeypatch, project.path, command) == 0


def test_unbalanced_quote_promote_still_denied(project, monkeypatch):
    """TASK-58#6"""
    project.draft(make_card(plan=None))
    assert run_main(monkeypatch, project.path, 'backlog draft promote DRAFT-8 "x') == 2


def test_card_is_judged_before_the_line_runs(project, monkeypatch):
    """TASK-58#6: the plan written earlier on the same line isn't on disk
    yet, so the promote is still denied."""
    project.draft(make_card(plan=None))
    command = 'backlog draft edit DRAFT-8 --plan "### Subjective" && backlog draft promote DRAFT-8'
    assert run_main(monkeypatch, project.path, command) == 2


def test_segment_of_only_assignments_is_not_gated():
    """TASK-58#6"""
    assert rip.gated_commands("FOO=1 BAR=2") == []
    assert rip.gated_commands("FOO=1; backlog draft promote 8") == [("promote", "8")]


def test_card_lookup_skips_odd_entries(project, monkeypatch):
    """TASK-58#1: non-markdown files, unreadable entries and a missing
    folder are skipped."""
    drafts = project.path / "backlog" / "drafts"
    (drafts / "a-notes.txt").write_text("---\nid: DRAFT-8\n---\n")
    (drafts / "broken.md").mkdir()
    project.draft(make_card(plan=None))
    assert run_main(monkeypatch, project.path, "backlog draft promote DRAFT-8") == 2
    assert rip.find_card(str(project.path), "nowhere", "DRAFT-8") is None


def test_payload_without_cwd_passes(monkeypatch):
    """TASK-58#1"""
    payload = {"tool_name": "Bash", "tool_input": {"command": "backlog draft promote 8"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rip.main()
    assert exc_info.value.code == 0


# --- TASK-58#7: registration, drift registry and docs ---

REPO = rip.os.path.dirname(rip.os.path.dirname(rip.os.path.abspath(rip.__file__)))


def read_repo(name):
    with open(rip.os.path.join(REPO, name)) as f:
        return f.read()


def test_registered_for_pretooluse_bash_without_filter():
    """TASK-58#7"""
    settings = json.loads(read_repo("settings.hooks.json"))
    hits = [
        (group.get("matcher"), hook.get("if"))
        for group in settings["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if hook["command"].endswith("/require_implementation_plan.py")
    ]
    assert hits == [("Bash", None)]


def test_copied_helpers_are_in_dedup_registry():
    """TASK-58#7"""
    import dedup_drift_guard

    for name in (
        "is_backlog_project",
        "strip_heredoc_bodies",
        "tokenize",
        "split_segments",
        "command_head",
        "project_config_path",
    ):
        assert "require_implementation_plan.py" in dedup_drift_guard.REGISTRY[name], name


@pytest.mark.parametrize("name", ["README.md", "CLAUDE.md.snippet"])
def test_docs_carry_soap_template_and_approval_command(name):
    """TASK-58#7 TASK-58#5"""
    text = read_repo(name)
    positions = [text.index(h) for h in rip.SOAP_HEADINGS]
    assert positions == sorted(positions)
    assert 'git commit --allow-empty -S -m "Plan-Approved: <ID>"' in text
    assert "계획 → 리뷰 → 계획 승인" in text
    assert "humanSigners" in text
    assert "Plan-Review-Go" not in text and '"Go: <ID>"' not in text
