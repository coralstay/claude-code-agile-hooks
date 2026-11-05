import io
import json
import subprocess

import pytest

import auto_stage as astg


def run_main(monkeypatch, tool_name, tool_input):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": tool_name, "tool_input": tool_input}))
    )
    with pytest.raises(SystemExit) as exc_info:
        astg.main()
    return exc_info.value.code


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def _staged_files(repo):
    result = subprocess.run(["git", "-C", repo, "diff", "--cached", "--name-only"], capture_output=True, text=True)
    return result.stdout.splitlines()


def test_stages_edited_file(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    f = tmp_path / "main.py"
    f.write_text("print(1)")
    code = run_main(monkeypatch, "Edit", {"file_path": str(f)})
    assert code == 0
    assert "main.py" in _staged_files(str(tmp_path))


def test_stages_written_file(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    f = tmp_path / "new.py"
    f.write_text("x = 1")
    run_main(monkeypatch, "Write", {"file_path": str(f)})
    assert "new.py" in _staged_files(str(tmp_path))


def test_no_op_outside_git_repo(monkeypatch, tmp_path):
    f = tmp_path / "lone.py"
    f.write_text("x = 1")
    assert run_main(monkeypatch, "Edit", {"file_path": str(f)}) == 0


def test_no_op_for_other_tools(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    f = tmp_path / "main.py"
    f.write_text("x")
    code = run_main(monkeypatch, "Read", {"file_path": str(f)})
    assert code == 0
    assert _staged_files(str(tmp_path)) == []


def test_no_op_when_file_does_not_exist(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    assert run_main(monkeypatch, "Edit", {"file_path": str(tmp_path / "ghost.py")}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        astg.main()
    assert exc_info.value.code == 0


def test_git_toplevel_returns_none_outside_repo(tmp_path):
    assert astg.git_toplevel(str(tmp_path)) is None


def test_stage_file_returns_false_outside_repo(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("x")
    assert astg.stage_file(str(f)) is False
