import io
import json

import pytest

import session_start as ss


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        ss.main()
    return exc_info.value.code


def test_exits_silently_when_backlog_not_installed(monkeypatch, capsys):
    monkeypatch.setattr(ss, "has_command", lambda name: False)
    code = run_main(monkeypatch, {"cwd": "/x"})
    assert code == 0
    assert capsys.readouterr().out == ""


def test_exits_silently_when_not_backlog_project(monkeypatch, capsys):
    monkeypatch.setattr(ss, "has_command", lambda name: True)
    monkeypatch.setattr(ss, "is_backlog_project", lambda cwd: False)
    code = run_main(monkeypatch, {"cwd": "/x"})
    assert code == 0
    assert capsys.readouterr().out == ""


def test_emits_context_json_for_backlog_project(monkeypatch, capsys):
    monkeypatch.setattr(ss, "has_command", lambda name: True)
    monkeypatch.setattr(ss, "is_backlog_project", lambda cwd: True)

    def fake_run(cwd, cmd):
        if cmd[1:3] == ["instructions", "overview"]:
            return "OVERVIEW TEXT"
        if cmd[1] == "doctor":
            return "all good"
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(ss, "run", fake_run)
    code = run_main(monkeypatch, {"cwd": "/x"})
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    assert hso["additionalContext"] == "OVERVIEW TEXT"
    assert "all good" in hso["systemMessage"]


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ss.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin_when_process_cwd_is_a_backlog_project(
    monkeypatch, tmp_path
):
    """Regression test for the 2026-09-19 bug: malformed stdin makes main()
    fall back to cwd="". is_backlog_project("") used to resolve os.path.join
    relative to the *process's actual* OS cwd, so if that happened to be a
    real backlog.md project (like this repo's root), it looked like a valid
    project and main() went on to call subprocess.run(cwd="") in run(),
    crashing with FileNotFoundError instead of exiting cleanly. Setting the
    test process's own cwd to a fake backlog project reproduces that
    regardless of where pytest happens to be invoked from."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ss, "has_command", lambda name: True)

    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ss.main()
    assert exc_info.value.code == 0


def test_has_command_true_for_python3():
    assert ss.has_command("python3") is True


def test_has_command_false_for_bogus():
    assert ss.has_command("definitely-not-a-real-command-xyz") is False


def test_is_backlog_project_true(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert ss.is_backlog_project(str(tmp_path)) is True


def test_is_backlog_project_false_without_git(tmp_path):
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert ss.is_backlog_project(str(tmp_path)) is False


def test_is_backlog_project_false(tmp_path):
    assert ss.is_backlog_project(str(tmp_path)) is False


def test_run_real_subprocess(tmp_path, monkeypatch):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backlog"
    script.write_text('#!/bin/bash\necho "hello $2"\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + os.environ.get("PATH", ""))
    out = ss.run(str(tmp_path), ["backlog", "x", "world"])
    assert out.strip() == "hello world"
