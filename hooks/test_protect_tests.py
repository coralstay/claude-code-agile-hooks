import io
import json

import pytest

import protect_tests as pt


def run_main(monkeypatch, tool_name, tool_input):
    stdin_data = {"tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        pt.main()
    return exc_info.value.code


def test_blocks_rm_test_file(monkeypatch, capsys):
    code = run_main(monkeypatch, "Bash", {"command": "rm test_foo.py"})
    assert code == 2
    assert "삭제" in capsys.readouterr().err


def test_blocks_rm_underscore_test_suffix(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "rm foo_test.py"}) == 2


def test_blocks_rename_test_file_away(monkeypatch, capsys):
    code = run_main(monkeypatch, "Bash", {"command": "mv test_foo.py foo.py.bak"})
    assert code == 2
    assert "이름 변경" in capsys.readouterr().err


def test_allows_rm_non_test_file(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "rm scratch.txt"}) == 0


def test_allows_unrelated_bash(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "ls -la"}) == 0


def test_blocks_write_adding_skip_decorator(monkeypatch, capsys):
    code = run_main(
        monkeypatch,
        "Write",
        {
            "file_path": "test_foo.py",
            "content": "@pytest.mark.skip\ndef test_x(): pass",
        },
    )
    assert code == 2
    assert "skip" in capsys.readouterr().err


def test_blocks_edit_adding_xfail(monkeypatch):
    code = run_main(
        monkeypatch,
        "Edit",
        {
            "file_path": "test_foo.py",
            "old_string": "def test_x(): pass",
            "new_string": "@pytest.mark.xfail\ndef test_x(): pass",
        },
    )
    assert code == 2


def test_allows_normal_test_edit(monkeypatch):
    code = run_main(
        monkeypatch,
        "Edit",
        {
            "file_path": "test_foo.py",
            "old_string": "assert 1 == 1",
            "new_string": "assert 2 == 2",
        },
    )
    assert code == 0


def test_allows_skip_word_in_non_test_file(monkeypatch):
    code = run_main(
        monkeypatch,
        "Write",
        {"file_path": "main.py", "content": "@pytest.mark.skip"},
    )
    assert code == 0


def test_no_op_for_other_tools(monkeypatch):
    assert run_main(monkeypatch, "Read", {"file_path": "test_foo.py"}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        pt.main()
    assert exc_info.value.code == 0


def test_is_test_file_variants():
    assert pt.is_test_file("test_foo.py") is True
    assert pt.is_test_file("foo_test.py") is True
    assert pt.is_test_file("foo.test.ts") is True
    assert pt.is_test_file("foo.spec.js") is True
    assert pt.is_test_file("foo.py") is False
    assert pt.is_test_file("") is False


def test_check_bash_no_op_when_command_empty():
    pt.check_bash("")  # should not raise/exit


def test_blocks_absolute_path_rm_bypass(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "/bin/rm test_foo.py"}) == 2


def test_blocks_relative_path_rm_bypass(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "./rm test_foo.py"}) == 2


def test_blocks_absolute_path_mv_bypass(monkeypatch):
    assert (
        run_main(monkeypatch, "Bash", {"command": "/bin/mv test_foo.py foo.py.bak"})
        == 2
    )


def test_allows_path_looking_argument_outside_verb_position(monkeypatch):
    # "/bin/rm" appearing only as an argument to another command (with no
    # target following it) must not be treated as an rm invocation.
    assert run_main(monkeypatch, "Bash", {"command": "echo /bin/rm"}) == 0


def test_blocks_rm_test_file_even_when_line_is_unparseable(monkeypatch, capsys):
    # shlex fails on the unterminated quote; the whitespace-split fallback still
    # sees rm and the test file, so the deletion stays blocked.
    assert run_main(monkeypatch, "Bash", {"command": "rm test_foo.py 'oops"}) == 2
    assert "삭제" in capsys.readouterr().err
