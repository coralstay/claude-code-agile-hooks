import io
import json

import pytest

import case_insensitive_guard as cig


def run_main(monkeypatch, command, cwd="."):
    stdin_data = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        cig.main()
    return exc_info.value.code


def test_blocks_when_case_colliding_sibling_exists(monkeypatch, capsys, tmp_path):
    (tmp_path / "Content").mkdir()
    code = run_main(monkeypatch, "rm -rf content", cwd=str(tmp_path))
    assert code == 2
    assert "Content" in capsys.readouterr().err


def test_allows_when_no_collision(monkeypatch, tmp_path):
    (tmp_path / "content").mkdir()
    assert run_main(monkeypatch, "rm -rf content", cwd=str(tmp_path)) == 0


def test_allows_when_target_does_not_exist_at_all(monkeypatch, tmp_path):
    assert run_main(monkeypatch, "rm -rf nonexistent", cwd=str(tmp_path)) == 0


def test_allows_non_rm_command(monkeypatch, tmp_path):
    (tmp_path / "Content").mkdir()
    assert run_main(monkeypatch, "ls content", cwd=str(tmp_path)) == 0


def test_allows_rm_with_no_targets(monkeypatch, tmp_path):
    assert run_main(monkeypatch, "rm -rf", cwd=str(tmp_path)) == 0


def test_no_op_when_command_missing(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}}))
    )
    with pytest.raises(SystemExit) as exc_info:
        cig.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        cig.main()
    assert exc_info.value.code == 0


def test_find_case_collision_direct(tmp_path):
    (tmp_path / "Foo").mkdir()
    assert cig.find_case_collision("foo", str(tmp_path)) == "Foo"
    assert cig.find_case_collision("Foo", str(tmp_path)) is None


def test_find_case_collision_nested_path(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "Bar").mkdir()
    assert cig.find_case_collision("sub/bar", str(tmp_path)) == "Bar"


def test_find_case_collision_missing_directory(tmp_path):
    assert cig.find_case_collision("nosuchdir/foo", str(tmp_path)) is None


def test_find_case_collision_none_for_flag_or_empty():
    assert cig.find_case_collision("", "/tmp") is None
    assert cig.find_case_collision("-rf", "/tmp") is None


def test_blocks_absolute_path_rm_bypass(monkeypatch, capsys, tmp_path):
    (tmp_path / "Content").mkdir()
    code = run_main(monkeypatch, "/bin/rm -rf content", cwd=str(tmp_path))
    assert code == 2
    assert "Content" in capsys.readouterr().err


def test_blocks_relative_path_rm_bypass(monkeypatch, capsys, tmp_path):
    (tmp_path / "Content").mkdir()
    code = run_main(monkeypatch, "./rm -rf content", cwd=str(tmp_path))
    assert code == 2
    assert "Content" in capsys.readouterr().err


def test_allows_path_looking_argument_outside_verb_position(monkeypatch, tmp_path):
    # "/bin/rm" appearing only as an argument to another command (not as
    # the invoked verb, and with nothing following it) must not be treated
    # as an rm invocation.
    (tmp_path / "Content").mkdir()
    assert run_main(monkeypatch, "echo /bin/rm", cwd=str(tmp_path)) == 0


def test_fails_open_on_unparseable_command(monkeypatch, tmp_path):
    # shlex can't split an unterminated quote; the shell would reject it too, so allow.
    (tmp_path / "Content").mkdir()
    assert run_main(monkeypatch, "rm -rf 'content", cwd=str(tmp_path)) == 0


def test_allows_when_rm_word_is_not_a_command_token(monkeypatch, tmp_path):
    # RM_RE matches "rm" inside "notes.rm", but no token is the rm binary -> not a deletion.
    (tmp_path / "Notes.rm").mkdir()
    assert run_main(monkeypatch, "cat notes.rm", cwd=str(tmp_path)) == 0
