"""TASK-59#3: require_stage_committed.py - a backlog stage command
(draft create / draft promote / task edit -s "In Progress" | Done) is denied
while backlog/ has uncommitted changes."""

import io
import json
import subprocess

import pytest

import require_stage_committed as rsc

TASK = "backlog/tasks/task-3 - 기존.md"


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def write(repo, rel, text="x\n"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "backlog/config.yml", "project_name: t\n")
    write(tmp_path, TASK, "---\nid: TASK-3\nstatus: To Do\n---\n")
    write(tmp_path, "src/app.py", "print(1)\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def run_main(monkeypatch, cwd, command):
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rsc.main()
    return exc_info.value.code


STAGE_COMMANDS = [
    'backlog draft create "새 기능"',
    "backlog draft promote DRAFT-3",
    'backlog task edit TASK-3 -s "In Progress"',
    "backlog task edit TASK-3 --status 'in progress'",
    "backlog task edit 3 -s Done",
    "backlog task edit TASK-3 --status=Done",
    'backlog task edit TASK-3 --check-ac 1 --final-summary "끝" -s Done',
    "cd /x && backlog draft create t",
    "FOO=1 /opt/homebrew/bin/backlog draft promote 3",
    "sudo -E backlog.md drafts create t",
    "true; backlog tasks edit TASK-3 -s Done",
    "backlog \\\n  draft create t",
]

NOT_STAGE_COMMANDS = [
    "",
    "ls",
    "backlog",
    "backlog draft",
    "FOO=1 BAR=2",
    "backlog draft edit DRAFT-3 -d x",
    "backlog draft list",
    "backlog task view TASK-3 --plain",
    "backlog task edit TASK-3 --add-ref decision-3",
    "backlog task edit TASK-3 -s 'To Do'",
    "backlog task edit TASK-3 -s",
    "backlog task create x",
    "echo backlog draft create x",
    'git commit -m "backlog draft promote 3"',
    'backlog draft edit DRAFT-3 -d "backlog task edit 3 -s Done; backlog draft create x"',
    "cat <<EOF\nbacklog draft create x\nbacklog task edit 3 -s Done\nEOF",
    "rg 'backlog draft create'",
]


# --- detection (pure) -------------------------------------------------------


@pytest.mark.parametrize("command", STAGE_COMMANDS)
def test_stage_command_in_command_position_is_detected(command):
    """TASK-59#3: stage commands are found in command position."""
    assert rsc.command_runs_stage(command)


@pytest.mark.parametrize("command", NOT_STAGE_COMMANDS)
def test_quoted_heredoc_and_other_commands_are_not_stages(command):
    """TASK-59#3: quoted text, heredoc bodies and other subcommands don't count."""
    assert not rsc.command_runs_stage(command)


@pytest.mark.parametrize(
    "command, expected",
    [
        ("backlog draft create 'unbalanced", True),
        ("x; /usr/bin/backlog task edit 3 --status 'In Progress", True),
        ('backlog task edit 3 -s "Done', True),
        ("echo 'unbalanced", False),
        ("backlog task edit 3 -s 'To Do", False),
    ],
)
def test_untokenizable_line_falls_back_to_text_match(command, expected):
    """TASK-59#3: unbalanced quotes - a conservative text match stands in."""
    assert rsc.command_runs_stage(command) is expected


# --- main against real repos ------------------------------------------------


@pytest.mark.parametrize("command", STAGE_COMMANDS)
def test_stage_command_on_clean_backlog_passes(monkeypatch, repo, command):
    """TASK-59#3: nothing uncommitted under backlog/ - the stage may run."""
    assert run_main(monkeypatch, repo, command) == 0


@pytest.mark.parametrize("command", STAGE_COMMANDS)
def test_stage_command_with_modified_task_denied(monkeypatch, capsys, repo, command):
    """TASK-59#3: an uncommitted backlog/ edit blocks the next stage."""
    write(repo, TASK, "---\nid: TASK-3\nstatus: To Do\nreferences: [decision-3]\n---\n")
    assert run_main(monkeypatch, repo, command) == 2
    err = capsys.readouterr().err
    assert "먼저 커밋" in err
    assert TASK in err


def test_untracked_draft_blocks_next_draft_create(monkeypatch, capsys, repo):
    """TASK-59#3: an uncommitted (untracked) draft blocks the next draft create."""
    write(repo, "backlog/drafts/draft-1 - a.md", "---\nid: DRAFT-1\n---\n")
    assert run_main(monkeypatch, repo, "backlog draft create b") == 2
    assert "backlog/drafts/draft-1 - a.md" in capsys.readouterr().err


def test_staged_but_uncommitted_change_still_denied(monkeypatch, repo):
    """TASK-59#3: staging is not committing."""
    write(repo, TASK, "---\nid: TASK-3\nstatus: In Progress\n---\n")
    git(repo, "add", TASK)
    assert run_main(monkeypatch, repo, "backlog task edit 3 -s Done") == 2


def test_changes_outside_backlog_are_ignored(monkeypatch, repo):
    """TASK-59#3: only backlog/ is checked - other work files don't block."""
    write(repo, "src/app.py", "print(2)\n")
    write(repo, "notes.txt", "memo\n")
    assert run_main(monkeypatch, repo, "backlog task edit 3 -s Done") == 0


def test_non_stage_command_passes_with_dirty_backlog(monkeypatch, repo):
    """TASK-59#3: other backlog commands (task edit --add-ref, ...) still run."""
    write(repo, TASK, "dirty\n")
    command = "backlog task edit 3 --add-ref decision-3"
    assert run_main(monkeypatch, repo, command) == 0


def test_non_backlog_project_passes(monkeypatch, repo):
    """TASK-59#3: not a backlog project -> pass."""
    (repo / "backlog/config.yml").unlink()
    write(repo, TASK, "dirty\n")
    assert run_main(monkeypatch, repo, "backlog draft create t") == 0


def test_passes_when_git_missing(monkeypatch, repo):
    """TASK-59#3: no git on PATH -> can't judge, pass."""
    write(repo, TASK, "dirty\n")
    monkeypatch.setattr(rsc, "has_command", lambda name: False)
    assert run_main(monkeypatch, repo, "backlog draft create t") == 0


def test_passes_when_git_status_fails(monkeypatch, repo):
    """TASK-59#3: unreadable status -> pass (fail open like the other gates)."""
    monkeypatch.setattr(rsc, "uncommitted_backlog_paths", lambda cwd: None)
    assert run_main(monkeypatch, repo, "backlog draft create t") == 0


def test_passes_on_invalid_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("nope"))
    with pytest.raises(SystemExit) as exc_info:
        rsc.main()
    assert exc_info.value.code == 0


# --- helpers ----------------------------------------------------------------


def test_uncommitted_backlog_paths_none_outside_repo(tmp_path):
    assert rsc.uncommitted_backlog_paths(str(tmp_path)) is None


def test_uncommitted_backlog_paths_lists_renames_and_spaces(repo):
    """TASK-59#3: porcelain -z entries, including both sides of a rename."""
    git(repo, "mv", TASK, "backlog/tasks/task-3 - 새 이름.md")
    assert rsc.uncommitted_backlog_paths(str(repo)) == [
        "backlog/tasks/task-3 - 새 이름.md",
        TASK,
    ]


def test_is_backlog_project_false_for_empty_cwd():
    assert rsc.is_backlog_project("") is False


def test_has_command_real():
    assert rsc.has_command("git") is True
    assert rsc.has_command("definitely-not-a-command-xyz") is False


def test_format_paths_truncates_long_lists():
    paths = [f"backlog/tasks/t{i}.md" for i in range(rsc.MAX_LISTED + 2)]
    listed = rsc.format_paths(paths)
    assert "backlog/tasks/t0.md" in listed
    assert f"backlog/tasks/t{rsc.MAX_LISTED}.md" not in listed
    assert "... 외 2개" in listed
