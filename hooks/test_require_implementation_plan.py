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


@pytest.fixture
def project(tmp_path, monkeypatch):
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
