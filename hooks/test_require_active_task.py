import io
import json

import pytest

import require_active_task as rat


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        rat.main()
    return exc_info.value.code


def test_passes_when_backlog_not_installed(monkeypatch):
    monkeypatch.setattr(rat, "has_command", lambda name: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_passes_when_not_a_backlog_project(monkeypatch):
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_denies_when_no_active_task(monkeypatch, capsys):
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: False)
    code = run_main(monkeypatch, {"cwd": "/x"})
    assert code == 2
    assert "In Progress" in capsys.readouterr().err


def test_denies_when_transcript_missing_task_view(monkeypatch, capsys, tmp_path):
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("some unrelated log line\n")
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: True)
    code = run_main(monkeypatch, {"cwd": "/x", "transcript_path": str(transcript)})
    assert code == 2
    assert "task view" in capsys.readouterr().err


def test_passes_when_transcript_has_task_view(monkeypatch, tmp_path):
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("ran: backlog task view TASK-3 --plain\n")
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: True)
    assert run_main(monkeypatch, {"cwd": "/x", "transcript_path": str(transcript)}) == 0


def test_passes_when_no_transcript_given(monkeypatch):
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: True)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        rat.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin_when_process_cwd_is_a_backlog_project(
    monkeypatch, tmp_path
):
    """Regression test for the 2026-09-19 bug: malformed stdin makes main()
    fall back to cwd="". is_backlog_project("") used to resolve os.path.join
    relative to the *process's actual* OS cwd, so if that happened to be a
    real backlog.md project (like this repo's root), it looked like a valid
    project and main() went on to call subprocess.run(cwd="") in
    has_active_task(), crashing with FileNotFoundError instead of exiting
    cleanly. Setting the test process's own cwd to a fake backlog project
    reproduces that regardless of where pytest happens to be invoked from."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rat, "has_command", lambda name: True)

    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        rat.main()
    assert exc_info.value.code == 0


def test_has_command_true_for_python3():
    assert rat.has_command("python3") is True


def test_has_command_false_for_bogus():
    assert rat.has_command("definitely-not-a-real-command-xyz") is False


def test_is_backlog_project_true(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert rat.is_backlog_project(str(tmp_path)) is True


def test_is_backlog_project_false_without_git(tmp_path):
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert rat.is_backlog_project(str(tmp_path)) is False


def test_is_backlog_project_false(tmp_path):
    assert rat.is_backlog_project(str(tmp_path)) is False


def _fake_backlog_script(tmp_path, body):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "backlog"
    script.write_text(f"#!/bin/bash\n{body}\n")
    script.chmod(0o755)
    return str(bin_dir)


def test_has_active_task_true_when_tasks_exist(tmp_path, monkeypatch):
    import os

    bin_dir = _fake_backlog_script(tmp_path, 'echo "TASK-3 - something"')
    monkeypatch.setenv("PATH", bin_dir + ":" + os.environ.get("PATH", ""))
    assert rat.has_active_task(str(tmp_path)) is True


def test_has_active_task_false_when_no_tasks(tmp_path, monkeypatch):
    import os

    bin_dir = _fake_backlog_script(tmp_path, 'echo "No tasks found."')
    monkeypatch.setenv("PATH", bin_dir + ":" + os.environ.get("PATH", ""))
    assert rat.has_active_task(str(tmp_path)) is False


# --- TASK-27: 프로젝트 밖 경로는 게이트하지 않는다 ---------------------------


def _gate_no_active_task(monkeypatch):
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: False)


def _make_project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


def test_passes_when_file_path_outside_project_without_checking_task(
    monkeypatch, tmp_path
):
    proj = _make_project(tmp_path)
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)

    def boom(cwd):
        raise AssertionError("has_active_task must not be called for outside paths")

    monkeypatch.setattr(rat, "has_active_task", boom)
    outside = tmp_path / "elsewhere" / "plan.md"
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": str(outside)}},
    )
    assert code == 0


def test_passes_when_notebook_path_outside_project(monkeypatch, tmp_path):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    outside = tmp_path / "nb.ipynb"
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"notebook_path": str(outside)}},
    )
    assert code == 0


def test_denies_when_file_path_inside_project(monkeypatch, tmp_path, capsys):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": str(proj / "src" / "a.py")}},
    )
    assert code == 2
    assert "In Progress" in capsys.readouterr().err


def test_denies_when_relative_file_path_resolves_inside_project(
    monkeypatch, tmp_path
):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": "src/a.py"}},
    )
    assert code == 2


def test_denies_when_file_path_is_project_root_itself(monkeypatch, tmp_path):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": str(proj)}},
    )
    assert code == 2


def test_denies_when_dotdot_traversal_leads_back_into_project(
    monkeypatch, tmp_path
):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    sneaky = str(proj) + "/../proj/x.py"
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": sneaky}},
    )
    assert code == 2


def test_passes_when_sibling_dir_shares_project_name_prefix(monkeypatch, tmp_path):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    sibling = tmp_path / "proj-other" / "x.py"
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": str(sibling)}},
    )
    assert code == 0


def test_denies_when_symlink_outside_points_into_project(monkeypatch, tmp_path):
    proj = _make_project(tmp_path)
    (proj / "src").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = outside / "link"
    link.symlink_to(proj / "src", target_is_directory=True)
    _gate_no_active_task(monkeypatch)
    code = run_main(
        monkeypatch,
        {"cwd": str(proj), "tool_input": {"file_path": str(link / "a.py")}},
    )
    assert code == 2


def test_denies_when_tool_input_has_no_file_path(monkeypatch, tmp_path):
    proj = _make_project(tmp_path)
    _gate_no_active_task(monkeypatch)
    code = run_main(monkeypatch, {"cwd": str(proj), "tool_input": {}})
    assert code == 2


def test_is_outside_project_unit(tmp_path):
    proj = _make_project(tmp_path)
    assert rat.is_outside_project(str(tmp_path / "x"), str(proj)) is True
    assert rat.is_outside_project(str(proj / "x"), str(proj)) is False
    assert rat.is_outside_project("x", str(proj)) is False
    assert rat.is_outside_project("", str(proj)) is False


def test_non_dict_tool_input_skips_outside_check_and_still_gates(monkeypatch, capsys):
    monkeypatch.setattr(rat, "has_command", lambda name: True)
    monkeypatch.setattr(rat, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rat, "has_active_task", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": "not-a-dict"}) == 2
    assert "In Progress" in capsys.readouterr().err
