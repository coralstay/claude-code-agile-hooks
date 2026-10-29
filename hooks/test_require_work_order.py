"""Tests for require_work_order.py (TASK-60#2): the next stage command
(`backlog draft promote`, `backlog task edit <ID> -s "In Progress"`) is
denied while backlog/work-order.md is missing or doesn't match the current
incomplete task set and dependencies."""

import io
import json
import os
import subprocess
import sys

import pytest

import require_work_order as rwo

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(HOOKS_DIR)
SCRIPT = os.path.join(REPO_DIR, "scripts", "work_order.py")


def run_main(monkeypatch, cwd, command):
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rwo.main()
    return exc_info.value.code


def write_task(root, task_id, status="To Do", deps=()):
    tasks = root / "backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    dep_lines = "".join(f"  - {d}\n" for d in deps)
    (tasks / f"{task_id.lower()} - t.md").write_text(
        f"---\nid: {task_id}\ntitle: t\nstatus: {status}\n"
        + ("dependencies:\n" + dep_lines if deps else "dependencies: []\n")
        + "---\n"
    )


def generate(root):
    """Writes backlog/work-order.md with the real script (the same one the
    deny message points to)."""
    result = subprocess.run(
        [sys.executable, SCRIPT, str(root)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def project(tmp_path):
    os.mkdir(tmp_path / ".git")
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("project_name: x\n")
    (tmp_path / "backlog" / "tasks").mkdir()
    return tmp_path


PROMOTE = "backlog draft promote DRAFT-3"
START = 'backlog task edit TASK-2 -s "In Progress"'


# --- command detection -------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        PROMOTE,
        "backlog drafts promote 3",
        "/opt/homebrew/bin/backlog draft promote DRAFT-1",
        "npx backlog.md draft promote DRAFT-1",
        "cd repo && backlog draft promote DRAFT-1",
        "FOO=1 sudo -E backlog draft promote DRAFT-1",
        START,
        "backlog task edit 2 --status 'In Progress'",
        "backlog task edit TASK-2 --status='in progress'",
        "backlog tasks edit TASK-2 -s 'IN PROGRESS' --dep TASK-1",
        "git status; backlog task edit TASK-2 -s 'In Progress'",
        "cat <<EOF > x\nhi\nEOF\nbacklog draft promote DRAFT-1",
        "backlog draft promote",  # no ID: still the promote subcommand
    ],
)
def test_detects_stage_commands_task_60_2(command):
    """TASK-60#2: promote and the In Progress move in command position."""
    assert rwo.command_starts_stage(command)


@pytest.mark.parametrize(
    "command",
    [
        "",
        "backlog draft create x",
        "backlog task edit TASK-2 -s Done",
        "backlog task edit TASK-2 -s",
        "backlog task edit -s 'In Progress'",
        "backlog task view TASK-2",
        "backlog task",
        "backlog",
        "echo backlog draft promote DRAFT-1",
        'git commit -m "backlog draft promote DRAFT-1"',
        "backlog draft create x -d 'then backlog draft promote it'",
        "cat <<'EOF' > notes.md\nbacklog draft promote DRAFT-1\nEOF",
        "FOO=1",
    ],
)
def test_ignores_other_commands_task_60_2(command):
    assert not rwo.command_starts_stage(command)


def test_untokenizable_line_falls_back_to_text_match_task_60_2():
    """TASK-60#2: unbalanced quotes -> conservative text match (gate)."""
    assert rwo.command_starts_stage('backlog draft promote DRAFT-1 "x')
    assert rwo.command_starts_stage("backlog task edit 2 -s 'In Progress")
    assert not rwo.command_starts_stage('backlog task edit 2 -s Done "x')


# --- recorded hash / script path ---------------------------------------------


def test_recorded_hash_missing_unreadable_or_headerless_task_60_2(project):
    assert rwo.recorded_hash(str(project)) is None
    (project / "backlog" / "work-order.md").write_text("# no header\n")
    assert rwo.recorded_hash(str(project)) is None
    (project / "backlog" / "work-order.md").write_text(
        "<!-- work-order-hash: " + "a" * 64 + " -->\n"
    )
    assert rwo.recorded_hash(str(project)) == "a" * 64


def test_work_order_script_prefers_installed_sibling_task_60_2(monkeypatch, tmp_path):
    """TASK-60#2: install.sh copies work_order.py next to the hooks, so the
    installed hook points there; in this repo it is scripts/work_order.py."""
    assert rwo.work_order_script() == SCRIPT
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    monkeypatch.setattr(rwo, "__file__", str(hooks / "require_work_order.py"))
    expected = str(hooks / "work_order.py")
    assert rwo.work_order_script() == expected  # neither exists: install path
    (hooks / "work_order.py").write_text("")
    assert rwo.work_order_script() == expected


def test_shared_helpers_match_the_script_task_60_2(project):
    """TASK-60#2: the hook's copy of the hash computes what the script writes."""
    write_task(project, "TASK-1", deps=["TASK-9"])
    write_task(project, "TASK-2", status="Done")
    generate(project)
    incomplete = rwo.incomplete_tasks(rwo.read_tasks(str(project)))
    assert list(incomplete) == ["TASK-1"]
    assert rwo.recorded_hash(str(project)) == rwo.input_hash(incomplete)


def test_shared_helper_edge_cases_task_60_2(tmp_path):
    assert rwo.read_tasks(str(tmp_path)) == {}
    assert rwo.parse_frontmatter("") == {}
    assert rwo.parse_frontmatter("---\nid: X\n") == {"id": "X"}
    fm = rwo.parse_frontmatter(
        "---\n  stray\ntitle: >-\n  a\n  b\nl: [x, 'y''s']\ne: []\nd:\n  - >-\n    z\n-\n---\n"
    )
    assert fm == {"title": "a b", "l": ["x", "y's"], "e": [], "d": [">-", ""]}
    assert rwo.parse_frontmatter('---\nq: "dq"\n---\n') == {"q": "dq"}
    assert rwo.parse_task("---\ntitle: x\n---\n") is None
    assert rwo.parse_task("---\nid: t-1\ndependencies: t-0\n---\n")["deps"] == ["T-0"]
    assert sorted(["T-10", "T-2"], key=rwo.natural_key) == ["T-2", "T-10"]
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "x.txt").write_text("")
    (tasks_dir / "y.md").write_text("no frontmatter")
    assert rwo.read_tasks(str(tmp_path)) == {}


# --- main -------------------------------------------------------------------------


def test_denies_promote_without_work_order_task_60_2(monkeypatch, capsys, project):
    write_task(project, "TASK-1")
    assert run_main(monkeypatch, project, PROMOTE) == 2
    err = capsys.readouterr().err
    assert "backlog/work-order.md" in err
    assert "없습니다" in err
    assert f"python3 {rwo.work_order_script()}" in err


def test_allows_promote_with_current_work_order_task_60_2(monkeypatch, project):
    write_task(project, "TASK-1")
    write_task(project, "TASK-2", deps=["TASK-1"])
    generate(project)
    assert run_main(monkeypatch, project, PROMOTE) == 0
    assert run_main(monkeypatch, project, START) == 0


def test_denies_in_progress_after_promote_until_regenerated_task_60_2(
    monkeypatch, capsys, project
):
    """TASK-60#2: the promote itself passes on the pre-promote state; the new
    task makes the file stale, so the next stage command waits for
    regeneration - which no hook blocks, so there is no deadlock."""
    write_task(project, "TASK-1")
    generate(project)
    assert run_main(monkeypatch, project, PROMOTE) == 0
    write_task(project, "TASK-2")  # what the promote created
    assert run_main(monkeypatch, project, START) == 2
    err = capsys.readouterr().err
    assert "맞지 않습니다" in err
    assert "--dep" in err
    generate(project)
    assert run_main(monkeypatch, project, START) == 0


def test_dependency_change_makes_work_order_stale_task_60_2(monkeypatch, project):
    write_task(project, "TASK-1")
    write_task(project, "TASK-2")
    generate(project)
    write_task(project, "TASK-2", deps=["TASK-1"])
    assert run_main(monkeypatch, project, PROMOTE) == 2


def test_title_or_status_change_keeps_work_order_current_task_60_2(
    monkeypatch, project
):
    write_task(project, "TASK-1")
    generate(project)
    write_task(project, "TASK-1", status="In Progress")
    assert run_main(monkeypatch, project, PROMOTE) == 0


def test_task_done_changes_the_set_task_60_2(monkeypatch, project):
    write_task(project, "TASK-1")
    write_task(project, "TASK-2")
    generate(project)
    write_task(project, "TASK-1", status="Done")
    assert run_main(monkeypatch, project, START) == 2


def test_first_promote_in_project_without_tasks_passes_task_60_2(
    monkeypatch, project
):
    """TASK-60#2: no incomplete tasks and no file yet (fresh project, or
    everything Done) -> nothing to order, the first promote passes."""
    assert run_main(monkeypatch, project, PROMOTE) == 0
    write_task(project, "TASK-1", status="Done")
    assert run_main(monkeypatch, project, PROMOTE) == 0


def test_stale_file_with_zero_incomplete_tasks_is_denied_task_60_2(
    monkeypatch, project
):
    write_task(project, "TASK-1")
    generate(project)
    write_task(project, "TASK-1", status="Done")
    assert run_main(monkeypatch, project, PROMOTE) == 2


def test_passes_other_commands_task_60_2(monkeypatch, project):
    write_task(project, "TASK-1")
    assert run_main(monkeypatch, project, "backlog task edit TASK-1 -s Done") == 0


def test_passes_in_non_backlog_project_task_60_2(monkeypatch, tmp_path):
    os.mkdir(tmp_path / ".git")
    assert run_main(monkeypatch, tmp_path, PROMOTE) == 0


def test_passes_without_cwd_or_on_invalid_json_task_60_2(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_input": {"command": PROMOTE}}))
    )
    with pytest.raises(SystemExit) as exc_info:
        rwo.main()
    assert exc_info.value.code == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rwo.main()
    assert exc_info.value.code == 0
