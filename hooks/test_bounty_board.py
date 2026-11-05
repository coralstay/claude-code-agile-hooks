import io
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import bounty_board as bb


@pytest.fixture(autouse=True)
def isolate_board(tmp_path, monkeypatch):
    board_path = str(tmp_path / "bounty-board.json")
    monkeypatch.setattr(bb, "BOARD_PATH", board_path)
    yield {"board": board_path, "tmp": tmp_path}


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        bb.main()
    return exc_info.value.code


def write_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_scan_markers_finds_todo_and_fixme(isolate_board, tmp_path):
    path = write_file(tmp_path, "a.py", "x = 1\n# TODO: fix this later\ndef f():\n    pass  # FIXME broken\n")
    markers = bb.scan_markers(path)
    assert len(markers) == 2


def test_scan_markers_ignores_clean_file(isolate_board, tmp_path):
    path = write_file(tmp_path, "b.py", "x = 1\ny = 2\n")
    assert bb.scan_markers(path) == []


def test_compute_xp_fresh_marker_is_base_xp():
    now_iso = datetime.now(timezone.utc).isoformat()
    assert bb.compute_xp(now_iso) == bb.BASE_XP


def test_compute_xp_caps_at_max():
    old_iso = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    assert bb.compute_xp(old_iso) == bb.MAX_XP


def test_sync_file_markers_registers_new_marker(isolate_board, tmp_path):
    path = write_file(tmp_path, "c.py", "# TODO: write tests\n")
    board = {}
    cleared = bb.sync_file_markers(board, path)
    assert cleared == []
    assert any(k.startswith(f"{path}::") for k in board)


def test_sync_file_markers_detects_cleared_marker(isolate_board, tmp_path):
    path = write_file(tmp_path, "d.py", "# TODO: write tests\n")
    board = {}
    bb.sync_file_markers(board, path)

    write_file(tmp_path, "d.py", "print('done')\n")
    cleared = bb.sync_file_markers(board, path)

    assert len(cleared) == 1
    assert board == {}


def test_top_bounties_sorted_descending():
    board = {
        "f1::TODO a": {"first_seen": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        "f2::TODO b": {"first_seen": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()},
    }
    top = bb.top_bounties(board, limit=2)
    assert top[0][0] == "f2::TODO b"
    assert top[0][1] > top[1][1]


def test_session_start_with_board_emits_additional_context(monkeypatch, isolate_board):
    board = {"f1::TODO a": {"first_seen": datetime.now(timezone.utc).isoformat()}}
    bb.save_board(board)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart"})))
    import contextlib
    import sys as _sys

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.raises(SystemExit):
            bb.main()
    payload = json.loads(buf.getvalue())
    assert "bounty-board" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_with_empty_board_emits_nothing(monkeypatch, capsys):
    code = run_main(monkeypatch, {"hook_event_name": "SessionStart"})
    assert code == 0
    assert capsys.readouterr().out == ""


def test_post_tool_use_registers_marker_from_file(monkeypatch, isolate_board, tmp_path):
    path = write_file(tmp_path, "e.py", "# TODO: refactor\n")
    code = run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUse", "tool_input": {"file_path": path}},
    )
    assert code == 0
    board = bb.load_board()
    assert any(k.startswith(f"{path}::") for k in board)


def test_post_tool_use_reports_cleared_bounty_on_stderr(monkeypatch, isolate_board, tmp_path, capsys):
    path = write_file(tmp_path, "f.py", "# TODO: refactor\n")
    run_main(monkeypatch, {"hook_event_name": "PostToolUse", "tool_input": {"file_path": path}})

    write_file(tmp_path, "f.py", "print('clean')\n")
    run_main(monkeypatch, {"hook_event_name": "PostToolUse", "tool_input": {"file_path": path}})

    assert "현상금 클리어" in capsys.readouterr().err


def test_post_tool_use_missing_file_path_noop(monkeypatch, isolate_board):
    code = run_main(monkeypatch, {"hook_event_name": "PostToolUse", "tool_input": {}})
    assert code == 0
    assert not os.path.isfile(isolate_board["board"])


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        bb.main()
    assert exc_info.value.code == 0


def test_load_board_returns_empty_on_corrupt_file(isolate_board):
    with open(isolate_board["board"], "w") as f:
        f.write("{not json")
    assert bb.load_board() == {}


def test_scan_markers_unreadable_path_returns_empty(tmp_path):
    # A directory can't be opened as a file (OSError) -> treated as having no markers.
    assert bb.scan_markers(str(tmp_path)) == []


def test_sync_file_markers_keeps_surviving_marker_age(isolate_board, tmp_path):
    path = write_file(tmp_path, "g.py", "# TODO: keep me\n# FIXME: drop me\n")
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    board = {
        bb.bounty_key(path, "# TODO: keep me"): {"first_seen": old, "file": path},
        bb.bounty_key(path, "# FIXME: drop me"): {"first_seen": old, "file": path},
    }
    write_file(tmp_path, "g.py", "# TODO: keep me\n")

    cleared = bb.sync_file_markers(board, path)

    assert cleared == [(bb.bounty_key(path, "# FIXME: drop me"), bb.compute_xp(old))]
    # The surviving marker is neither cleared nor re-registered: its first_seen stays.
    assert board == {bb.bounty_key(path, "# TODO: keep me"): {"first_seen": old, "file": path}}


def test_unknown_event_is_ignored(monkeypatch, isolate_board, tmp_path, capsys):
    path = write_file(tmp_path, "h.py", "# TODO: x\n")
    code = run_main(monkeypatch, {"hook_event_name": "Stop", "tool_input": {"file_path": path}})
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not os.path.isfile(isolate_board["board"])
