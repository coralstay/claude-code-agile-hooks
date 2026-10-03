import io
import json
import os
import subprocess

import pytest

import block_stop_if_dirty as bsd


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        bsd.main()
    return exc_info.value.code


def test_passes_when_backlog_not_installed(monkeypatch):
    monkeypatch.setattr(bsd, "has_command", lambda name: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_passes_when_not_backlog_project(monkeypatch):
    monkeypatch.setattr(bsd, "has_command", lambda name: True)
    monkeypatch.setattr(bsd, "is_backlog_project", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_passes_when_no_active_task(monkeypatch):
    monkeypatch.setattr(bsd, "has_command", lambda name: True)
    monkeypatch.setattr(bsd, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(bsd, "has_active_task", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_denies_when_dirty(monkeypatch, capsys):
    monkeypatch.setattr(bsd, "has_command", lambda name: True)
    monkeypatch.setattr(bsd, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(bsd, "has_active_task", lambda cwd: True)
    monkeypatch.setattr(bsd, "is_dirty", lambda cwd: True)
    code = run_main(monkeypatch, {"cwd": "/x"})
    assert code == 2
    assert "커밋하지" in capsys.readouterr().err


def test_passes_when_clean(monkeypatch):
    monkeypatch.setattr(bsd, "has_command", lambda name: True)
    monkeypatch.setattr(bsd, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(bsd, "has_active_task", lambda cwd: True)
    monkeypatch.setattr(bsd, "is_dirty", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x"}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        bsd.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin_when_process_cwd_is_a_backlog_project(
    monkeypatch, tmp_path
):
    """Regression test for the 2026-09-19 bug: malformed stdin makes main()
    fall back to cwd="". is_backlog_project("") used to resolve os.path.join
    relative to the *process's actual* OS cwd, so if that happened to be a
    real backlog.md project (like this repo's root), it looked like a valid
    project and main() went on to call subprocess.run(cwd="") in
    has_active_task()/is_dirty(), crashing with FileNotFoundError instead of
    exiting cleanly. Setting the test process's own cwd to a fake backlog
    project reproduces that regardless of where pytest happens to be
    invoked from."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bsd, "has_command", lambda name: True)

    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        bsd.main()
    assert exc_info.value.code == 0


def test_has_command_true_for_python3():
    assert bsd.has_command("python3") is True


def test_has_command_false_for_bogus():
    assert bsd.has_command("definitely-not-a-real-command-xyz") is False


def test_is_backlog_project_true(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert bsd.is_backlog_project(str(tmp_path)) is True


def test_is_backlog_project_false_without_git(tmp_path):
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert bsd.is_backlog_project(str(tmp_path)) is False


def test_is_backlog_project_false(tmp_path):
    assert bsd.is_backlog_project(str(tmp_path)) is False


def test_has_active_task_real(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backlog"
    script.write_text('#!/bin/bash\necho "No tasks found."\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + os.environ.get("PATH", ""))
    assert bsd.has_active_task(str(tmp_path)) is False


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_is_dirty_real_git_clean(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f.txt").write_text("hi")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "init")
    assert bsd.is_dirty(str(tmp_path)) is False


def test_is_dirty_real_git_dirty(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f.txt").write_text("hi")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "f.txt").write_text("changed")
    assert bsd.is_dirty(str(tmp_path)) is True


def _dirty_project(monkeypatch):
    monkeypatch.setattr(bsd, "has_command", lambda name: True)
    monkeypatch.setattr(bsd, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(bsd, "has_active_task", lambda cwd: True)
    monkeypatch.setattr(bsd, "is_dirty", lambda cwd: True)


def test_passes_when_background_tasks_running(monkeypatch, capsys):
    """TASK-31 재현 시나리오: 백그라운드 서브에이전트가 같은 작업 트리를
    수정 중일 때 메인 세션의 Stop을 막으면, 메인은 서브에이전트가 끝날
    때까지 busy-wait만 할 수 있다(실제로 3회 연속 차단됨). 그 변경은 실행
    중인 백그라운드 작업 몫일 수 있으므로 통과시킨다."""
    _dirty_project(monkeypatch)
    code = run_main(
        monkeypatch,
        {"cwd": "/x", "background_tasks": [{"id": "a1", "type": "agent"}]},
    )
    assert code == 0
    assert "커밋하지" not in capsys.readouterr().err


def test_still_denies_when_background_tasks_empty(monkeypatch):
    _dirty_project(monkeypatch)
    assert run_main(monkeypatch, {"cwd": "/x", "background_tasks": []}) == 2


def test_still_denies_when_background_tasks_null(monkeypatch):
    _dirty_project(monkeypatch)
    assert run_main(monkeypatch, {"cwd": "/x", "background_tasks": None}) == 2


def test_passes_when_stop_hook_active(monkeypatch):
    """한 번 차단해서 Claude가 계속 진행 중인 상태(stop_hook_active=true)
    에서는 또 막지 않는다 — 차단-재시도 무한 루프 방지."""
    _dirty_project(monkeypatch)
    assert run_main(monkeypatch, {"cwd": "/x", "stop_hook_active": True}) == 0


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        ([], False),
        ({}, False),
        ("", False),
        (0, False),
        (["task-1"], True),
        ([{"id": "x"}], True),
        ({"x": {"status": "running"}}, True),
        ("not-a-container", False),
    ],
)
def test_background_tasks_running_shapes(value, expected):
    assert bsd.background_tasks_running({"background_tasks": value}) is expected


def test_background_tasks_running_missing_key():
    assert bsd.background_tasks_running({}) is False
