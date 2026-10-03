import io
import json
import os

import pytest

import dead_end_registry as der


@pytest.fixture(autouse=True)
def isolate_paths(tmp_path, monkeypatch):
    registry_path = str(tmp_path / "dead-end-registry.jsonl")
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(der, "REGISTRY_PATH", registry_path)
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda p: p.replace("~/.claude/hooks-logs/sessions", str(sessions_dir)) if "sessions" in p else real_expanduser(p),
    )
    yield {"registry": registry_path, "sessions": sessions_dir}


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        der.main()
    return exc_info.value.code


def write_session_log(sessions_dir, session_id, files):
    sessions_dir.mkdir(exist_ok=True)
    with open(sessions_dir / f"{session_id}.jsonl", "w") as f:
        for path in files:
            f.write(json.dumps({"event": "tool_use", "file_path": path}) + "\n")


def test_revert_mention_registers_recent_files(monkeypatch, isolate_paths):
    write_session_log(isolate_paths["sessions"], "s1", ["/x/a.py"])
    code = run_main(
        monkeypatch,
        {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "revert that change because it broke tests"},
    )
    assert code == 0
    records = [json.loads(l) for l in open(isolate_paths["registry"]).read().splitlines()]
    assert records[0]["file_path"] == "/x/a.py"
    assert "broke tests" in records[0]["reason"]


def test_prompt_without_revert_mention_registers_nothing(monkeypatch, isolate_paths):
    run_main(monkeypatch, {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "add a new feature"})
    assert not os.path.exists(isolate_paths["registry"])


def test_korean_revert_mention_is_recognized(monkeypatch, isolate_paths):
    write_session_log(isolate_paths["sessions"], "s3", ["/x/b.py"])
    run_main(
        monkeypatch,
        {"hook_event_name": "UserPromptSubmit", "session_id": "s3", "prompt": "그거 되돌려줘 이유는 성능이 나빠져서"},
    )
    records = [json.loads(l) for l in open(isolate_paths["registry"]).read().splitlines()]
    assert records[0]["file_path"] == "/x/b.py"


def test_pretooluse_warns_on_registered_dead_end(monkeypatch, isolate_paths, capsys):
    write_session_log(isolate_paths["sessions"], "s4", ["/x/c.py"])
    run_main(
        monkeypatch,
        {"hook_event_name": "UserPromptSubmit", "session_id": "s4", "prompt": "revert it because it was slow"},
    )
    code = run_main(
        monkeypatch,
        {"hook_event_name": "PreToolUse", "session_id": "s4", "tool_input": {"file_path": "/x/c.py"}},
    )
    assert code == 0
    assert "slow" in capsys.readouterr().err


def test_pretooluse_silent_for_file_without_dead_end(monkeypatch, capsys):
    code = run_main(
        monkeypatch,
        {"hook_event_name": "PreToolUse", "session_id": "s5", "tool_input": {"file_path": "/x/clean.py"}},
    )
    assert code == 0
    assert capsys.readouterr().err == ""


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        der.main()
    assert exc_info.value.code == 0


def test_dead_ends_for_file_empty_when_no_registry():
    assert der.dead_ends_for_file("/x") == []


def test_recent_files_for_session_empty_when_missing():
    assert der.recent_files_for_session("no-such-session") == []


def test_recent_files_skips_malformed_and_non_edit_records(isolate_paths):
    sessions = isolate_paths["sessions"]
    sessions.mkdir()
    with open(sessions / "s9.jsonl", "w") as f:
        f.write("not json\n")
        f.write(json.dumps({"event": "prompt", "file_path": "/x/prompt.py"}) + "\n")
        f.write(json.dumps({"event": "tool_use"}) + "\n")
        f.write(json.dumps({"event": "tool_use", "file_path": "/x/real.py"}) + "\n")
    assert der.recent_files_for_session("s9") == ["/x/real.py"]


def test_dead_ends_for_file_skips_malformed_and_other_files(isolate_paths):
    with open(isolate_paths["registry"], "w") as f:
        f.write("not json\n")
        f.write(json.dumps({"file_path": "/x/other.py", "reason": "r1"}) + "\n")
        f.write(json.dumps({"file_path": "/x/a.py", "reason": "r2"}) + "\n")
    assert der.dead_ends_for_file("/x/a.py") == [{"file_path": "/x/a.py", "reason": "r2"}]


def test_pretooluse_without_file_path_is_silent(monkeypatch, isolate_paths, capsys):
    with open(isolate_paths["registry"], "w") as f:
        f.write(json.dumps({"file_path": "", "reason": "r"}) + "\n")
    code = run_main(monkeypatch, {"hook_event_name": "PreToolUse", "tool_input": {"command": "ls"}})
    assert code == 0
    assert capsys.readouterr().err == ""


def test_unknown_event_is_ignored(monkeypatch, isolate_paths, capsys):
    code = run_main(monkeypatch, {"hook_event_name": "Stop", "prompt": "revert because broken"})
    assert code == 0
    assert capsys.readouterr().err == ""
    assert not os.path.exists(isolate_paths["registry"])
