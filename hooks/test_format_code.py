import io
import json

import pytest

import format_code as fc


def run_main(monkeypatch, tool_name, tool_input):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": tool_name, "tool_input": tool_input}))
    )
    with pytest.raises(SystemExit) as exc_info:
        fc.main()
    return exc_info.value.code


def test_python_file_runs_format_then_check(monkeypatch, tmp_path, capsys):
    f = tmp_path / "main.py"
    f.write_text("x=1")

    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        if cmd[:2] == ["ruff", "check"]:
            return 1, "E501 line too long"
        return 0, ""

    monkeypatch.setattr(fc, "run", fake_run)
    monkeypatch.setattr(fc.shutil, "which", lambda name: "/usr/bin/ruff" if name == "ruff" else None)

    code = run_main(monkeypatch, "Edit", {"file_path": str(f)})
    assert code == 0
    assert calls[0][:2] == ["ruff", "format"]
    assert calls[1][:2] == ["ruff", "check"]
    assert "E501" in capsys.readouterr().err


def test_python_file_silent_when_lint_clean(monkeypatch, tmp_path, capsys):
    f = tmp_path / "main.py"
    f.write_text("x = 1\n")

    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: (0, ""))
    monkeypatch.setattr(fc.shutil, "which", lambda name: "/usr/bin/ruff" if name == "ruff" else None)

    code = run_main(monkeypatch, "Edit", {"file_path": str(f)})
    assert code == 0
    assert capsys.readouterr().err == ""


def test_python_file_no_op_when_ruff_missing(monkeypatch, tmp_path):
    f = tmp_path / "main.py"
    f.write_text("x=1")

    calls = []
    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(fc.shutil, "which", lambda name: None)

    run_main(monkeypatch, "Edit", {"file_path": str(f)})
    assert calls == []


def test_typescript_file_runs_prettier_and_tsc(monkeypatch, tmp_path, capsys):
    f = tmp_path / "main.ts"
    f.write_text("const x: number = 1")

    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        if cmd[0] == "tsc":
            return 1, "type error"
        return 0, ""

    monkeypatch.setattr(fc, "run", fake_run)
    monkeypatch.setattr(fc.shutil, "which", lambda name: f"/usr/bin/{name}")

    code = run_main(monkeypatch, "Write", {"file_path": str(f)})
    assert code == 0
    assert any(c[0] == "prettier" for c in calls)
    assert any(c[0] == "tsc" for c in calls)
    assert "type error" in capsys.readouterr().err


def test_js_file_does_not_run_tsc(monkeypatch, tmp_path):
    f = tmp_path / "main.js"
    f.write_text("const x = 1")

    calls = []
    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(fc.shutil, "which", lambda name: f"/usr/bin/{name}")

    run_main(monkeypatch, "Write", {"file_path": str(f)})
    assert not any(c[0] == "tsc" for c in calls)


def test_unsupported_extension_no_op(monkeypatch, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hi")
    calls = []
    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: calls.append(cmd) or (0, ""))
    run_main(monkeypatch, "Edit", {"file_path": str(f)})
    assert calls == []


def test_no_op_for_other_tools(monkeypatch, tmp_path):
    f = tmp_path / "main.py"
    f.write_text("x")
    assert run_main(monkeypatch, "Read", {"file_path": str(f)}) == 0


def test_no_op_when_file_missing(monkeypatch, tmp_path):
    assert run_main(monkeypatch, "Edit", {"file_path": str(tmp_path / "ghost.py")}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        fc.main()
    assert exc_info.value.code == 0


def test_run_real_subprocess():
    code, output = fc.run(["echo", "hi"])
    assert code == 0
    assert "hi" in output


def test_typescript_file_no_op_when_no_tools(monkeypatch, tmp_path, capsys):
    f = tmp_path / "main.ts"
    f.write_text("const x: number = 1")
    calls = []
    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(fc.shutil, "which", lambda name: None)

    assert run_main(monkeypatch, "Write", {"file_path": str(f)}) == 0
    assert calls == []
    assert capsys.readouterr().err == ""


def test_typescript_file_uses_npx_prettier_and_is_silent_when_tsc_clean(monkeypatch, tmp_path, capsys):
    f = tmp_path / "main.ts"
    f.write_text("const x: number = 1")
    calls = []
    monkeypatch.setattr(fc, "run", lambda cmd, cwd=None: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(fc.shutil, "which", lambda name: None if name == "prettier" else f"/usr/bin/{name}")

    assert run_main(monkeypatch, "Write", {"file_path": str(f)}) == 0
    assert calls == [["npx", "--yes", "prettier", "--write", str(f)], ["tsc", "--noEmit", str(f)]]
    assert capsys.readouterr().err == ""
