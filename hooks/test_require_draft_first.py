import io
import json
import os

import pytest

import require_draft_first as rdf


def run_main(monkeypatch, cwd, command):
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rdf.main()
    return exc_info.value.code


@pytest.fixture
def backlog_repo(tmp_path):
    os.mkdir(tmp_path / ".git")
    os.mkdir(tmp_path / "backlog")
    (tmp_path / "backlog" / "config.yml").write_text("project_name: x\n")
    return tmp_path


# --- command_invokes_backlog_task_create ---------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "backlog task create 'x'",
        "backlog tasks create x",
        "backlog task create",
        "/opt/homebrew/bin/backlog task create x",
        "./node_modules/.bin/backlog task create x",
        "backlog task --plain create x",
        "cd repo && backlog task create x",
        "git status; backlog task create x",
        "true || backlog task create x",
        "echo hi | backlog task create x",
        "FOO=1 backlog task create x",
        "env FOO=1 backlog task create x",
        "sudo backlog task create x",
        "npx backlog.md task create x",
        "bunx backlog.md task create x",
        "(backlog task create x)",
        "echo a\nbacklog task create x",
        "git status;backlog task create x",
    ],
)
def test_detects_task_create(command):
    assert rdf.command_invokes_backlog_task_create(command)


@pytest.mark.parametrize(
    "command",
    [
        "backlog draft create x",
        'backlog draft create x -d "먼저 backlog task create를 쓰지 말 것"',
        "backlog draft create x -d 'backlog task create'",
        "backlog task list --plain",
        "backlog task edit TASK-1 -s Done",
        "backlog task view TASK-29 --plain",
        "backlog draft promote DRAFT-3",
        "echo backlog task create",
        "grep -rn 'backlog task create' .",
        'git commit -m "backlog task create 금지 훅"',
        "cat <<'EOF' > notes.md\nbacklog task create\nEOF",
        "cat <<EOF\nbacklog task create x\nEOF\necho done",
        "backlog search create",
        "",
    ],
)
def test_ignores_non_invocations(command):
    assert not rdf.command_invokes_backlog_task_create(command)


def test_heredoc_body_skipped_but_command_after_it_still_detected():
    command = "cat <<EOF > a.md\nhello\nEOF\nbacklog task create x"
    assert rdf.command_invokes_backlog_task_create(command)


def test_unbalanced_quotes_fall_back_to_line_start_match():
    assert rdf.command_invokes_backlog_task_create('backlog task create "x')
    assert not rdf.command_invokes_backlog_task_create(
        'backlog draft create "x backlog task create'
    )


# --- main --------------------------------------------------------------


def test_denies_task_create_in_backlog_project(monkeypatch, capsys, backlog_repo):
    code = run_main(monkeypatch, backlog_repo, "backlog task create 'new thing'")
    assert code == 2
    err = capsys.readouterr().err
    assert "backlog draft create" in err
    assert "promote" in err


def test_allows_draft_create_with_task_create_text_in_description(
    monkeypatch, backlog_repo
):
    command = 'backlog draft create "x" -d "backlog task create 대신 드래프트"'
    assert run_main(monkeypatch, backlog_repo, command) == 0


def test_allows_other_commands(monkeypatch, backlog_repo):
    assert run_main(monkeypatch, backlog_repo, "ls -la") == 0


def test_passes_in_non_backlog_project(monkeypatch, tmp_path):
    os.mkdir(tmp_path / ".git")
    assert run_main(monkeypatch, tmp_path, "backlog task create x") == 0


def test_passes_without_cwd(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"tool_input": {"command": "backlog task create x"}})),
    )
    with pytest.raises(SystemExit) as exc_info:
        rdf.main()
    assert exc_info.value.code == 0


def test_passes_on_invalid_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rdf.main()
    assert exc_info.value.code == 0


def test_wrapper_flags_before_backlog_are_skipped(monkeypatch, backlog_repo, capsys):
    assert rdf.command_invokes_backlog_task_create("sudo -E -n backlog task create x")
    assert run_main(monkeypatch, backlog_repo, "sudo -E backlog task create x") == 2
    assert capsys.readouterr().err


def test_segment_of_only_assignments_is_not_task_create():
    assert rdf.command_invokes_backlog_task_create("FOO=1 BAR=2") is False
    assert rdf.command_invokes_backlog_task_create("FOO=1; backlog task create x") is True
