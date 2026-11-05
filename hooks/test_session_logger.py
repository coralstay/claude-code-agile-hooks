import io
import json
import subprocess

import pytest

import session_logger as sl


@pytest.fixture(autouse=True)
def isolate_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_SESSION_LOG_DIR", str(tmp_path))
    yield tmp_path


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        sl.main()
    return exc_info.value.code


def read_entries(tmp_path, session_id):
    path = tmp_path / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_session_start_logs_cwd_and_branch(monkeypatch, isolate_log_dir, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "task/TASK-1"], cwd=repo, check=True, capture_output=True)
    (repo / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    code = run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(repo)})
    assert code == 0
    entries = read_entries(isolate_log_dir, "s1")
    assert entries[0]["event"] == "session_start"
    assert entries[0]["branch"] == "task/TASK-1"


def test_user_prompt_submit_logs_prompt(monkeypatch, isolate_log_dir):
    run_main(monkeypatch, {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "hello there"})
    entries = read_entries(isolate_log_dir, "s2")
    assert entries[0] == {**entries[0], "event": "prompt", "prompt": "hello there"}


def test_post_tool_use_logs_edited_file(monkeypatch, isolate_log_dir):
    run_main(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s3",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x/main.py"},
        },
    )
    entries = read_entries(isolate_log_dir, "s3")
    assert entries[0]["event"] == "tool_use"
    assert entries[0]["file_path"] == "/x/main.py"


def test_post_tool_use_logs_and_redacts_bash_command(monkeypatch, isolate_log_dir):
    run_main(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s4",
            "tool_name": "Bash",
            "tool_input": {"command": "export API_KEY=sk-supersecret123"},
        },
    )
    entries = read_entries(isolate_log_dir, "s4")
    assert "sk-supersecret123" not in entries[0]["command"]
    assert "[REDACTED]" in entries[0]["command"]


def test_post_tool_use_for_other_tool_has_no_extra_fields(monkeypatch, isolate_log_dir):
    run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUse", "session_id": "s5", "tool_name": "Read", "tool_input": {"file_path": "/x"}},
    )
    entries = read_entries(isolate_log_dir, "s5")
    assert "file_path" not in entries[0]
    assert "command" not in entries[0]


def test_session_end_logs_reason(monkeypatch, isolate_log_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionEnd", "session_id": "s6", "reason": "exit"})
    entries = read_entries(isolate_log_dir, "s6")
    assert entries[0]["event"] == "session_end"
    assert entries[0]["reason"] == "exit"


def test_multiple_events_append_to_same_session_log(monkeypatch, isolate_log_dir):
    run_main(monkeypatch, {"hook_event_name": "UserPromptSubmit", "session_id": "s7", "prompt": "a"})
    run_main(monkeypatch, {"hook_event_name": "UserPromptSubmit", "session_id": "s7", "prompt": "b"})
    entries = read_entries(isolate_log_dir, "s7")
    assert len(entries) == 2


def test_unknown_event_is_ignored(monkeypatch, isolate_log_dir):
    code = run_main(monkeypatch, {"hook_event_name": "SomethingElse", "session_id": "s8"})
    assert code == 0
    assert read_entries(isolate_log_dir, "s8") == []


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        sl.main()
    assert exc_info.value.code == 0


def test_redact_direct():
    assert sl.redact("token: abc123") == "token: [REDACTED]"
    assert sl.redact("ls -la") == "ls -la"


def test_current_branch_returns_none_when_not_a_repo(tmp_path):
    assert sl.current_branch(str(tmp_path)) is None
