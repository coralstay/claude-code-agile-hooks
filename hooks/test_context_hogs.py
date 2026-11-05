import io
import json

import pytest

import context_hogs as ch


@pytest.fixture(autouse=True)
def isolate_log(tmp_path, monkeypatch):
    path = str(tmp_path / "context-hogs.jsonl")
    monkeypatch.setattr(ch, "LOG_PATH", path)
    yield path


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        ch.main()
    return exc_info.value.code


def read_records(path):
    return [json.loads(line) for line in open(path).read().splitlines()]


def test_read_tool_attributes_cost_to_file(monkeypatch, isolate_log):
    code = run_main(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "tool_name": "Read",
            "tool_input": {"file_path": "/x/big.py"},
            "tool_response": "a" * 400,
        },
    )
    assert code == 0
    record = read_records(isolate_log)[0]
    assert record["file_path"] == "/x/big.py"
    assert record["tokens"] == 100


def test_grep_attributes_cost_to_searched_path(monkeypatch, isolate_log):
    run_main(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s2",
            "tool_name": "Grep",
            "tool_input": {"path": "/x/dir"},
            "tool_response": "match\n" * 20,
        },
    )
    record = read_records(isolate_log)[0]
    assert record["file_path"] == "/x/dir"


def test_bash_and_glob_produce_no_records(monkeypatch, isolate_log):
    import os

    run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUse", "session_id": "s3", "tool_name": "Bash", "tool_response": "output" * 50},
    )
    run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUse", "session_id": "s3", "tool_name": "Glob", "tool_response": "a\nb\nc"},
    )
    assert not os.path.exists(isolate_log)


def test_empty_response_produces_no_record(monkeypatch, isolate_log):
    import os

    run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUse", "session_id": "s4", "tool_name": "Read", "tool_input": {"file_path": "/x"}, "tool_response": ""},
    )
    assert not os.path.exists(isolate_log)


def test_non_posttooluse_event_ignored(monkeypatch, isolate_log):
    import os

    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s5"})
    assert not os.path.exists(isolate_log)


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        ch.main()
    assert exc_info.value.code == 0


def test_estimate_tokens():
    assert ch.estimate_tokens("") == 0
    assert ch.estimate_tokens("ab") == 1
    assert ch.estimate_tokens("a" * 40) == 10


def test_response_text_variants():
    assert ch.response_text("plain string") == "plain string"
    assert ch.response_text({"content": "x"}) == "x"
    assert ch.response_text({"stdout": "y"}) == "y"
    assert ch.response_text({"other": "z"}) == json.dumps({"other": "z"})
    assert ch.response_text(None) == ""


def test_files_for_tool():
    assert ch.files_for_tool("Read", {"file_path": "/x"}) == ["/x"]
    assert ch.files_for_tool("Read", {}) == []
    assert ch.files_for_tool("Glob", {"pattern": "*.py"}) == []
    assert ch.files_for_tool("Bash", {"command": "ls"}) == []
    assert ch.files_for_tool("Unknown", {}) == []


def test_leaderboard_aggregates_and_sorts(isolate_log):
    ch.append_log({"event": "cost", "file_path": "/a", "tokens": 10})
    ch.append_log({"event": "cost", "file_path": "/b", "tokens": 50})
    ch.append_log({"event": "cost", "file_path": "/a", "tokens": 5})
    board = ch.leaderboard()
    assert board[0] == ("/b", 50)
    assert board[1] == ("/a", 15)


def test_leaderboard_empty_when_no_log():
    assert ch.leaderboard() == []


def test_leaderboard_skips_blank_corrupt_non_cost_and_pathless_lines(isolate_log):
    with open(isolate_log, "w") as f:
        f.write("\n")
        f.write("{not json\n")
        f.write(json.dumps({"event": "other", "file_path": "/x", "tokens": 99}) + "\n")
        f.write(json.dumps({"event": "cost", "tokens": 7}) + "\n")
        f.write(json.dumps({"event": "cost", "file_path": "/a", "tokens": 3}) + "\n")
    assert ch.leaderboard() == [("/a", 3)]
