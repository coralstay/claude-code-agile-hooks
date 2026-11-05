import io
import json
import os

import pytest

import standup_autopilot as sa


@pytest.fixture(autouse=True)
def isolate_dirs(tmp_path, monkeypatch):
    standup_dir = tmp_path / "standup"
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(sa, "STANDUP_DIR", str(standup_dir))
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda p: p.replace("~/.claude/hooks-logs/sessions", str(sessions_dir)) if "sessions" in p else real_expanduser(p),
    )
    yield {"standup": standup_dir, "sessions": sessions_dir}


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        sa.main()
    return exc_info.value.code


def write_session_log(sessions_dir, session_id, entries):
    sessions_dir.mkdir(exist_ok=True)
    with open(sessions_dir / f"{session_id}.jsonl", "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_stop_event_appends_standup_entry(monkeypatch, isolate_dirs):
    write_session_log(
        isolate_dirs["sessions"],
        "s1",
        [
            {"event": "tool_use", "file_path": "/x/a.py"},
            {"event": "tool_use", "file_path": "/x/b.py"},
            {"event": "tool_use", "tool_name": "Bash"},
        ],
    )
    code = run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s1"})
    assert code == 0
    today_file = sa.today_path()
    assert os.path.isfile(today_file)
    content = open(today_file).read()
    assert "2개 파일" in content
    assert "a.py" in content and "b.py" in content


def test_stop_event_with_no_activity_writes_nothing(monkeypatch, isolate_dirs):
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "no-such-session"})
    assert not os.path.isfile(sa.today_path())


def test_session_start_startup_injects_yesterday_summary(monkeypatch, isolate_dirs, capsys):
    isolate_dirs["standup"].mkdir(parents=True, exist_ok=True)
    with open(sa.yesterday_path(), "w") as f:
        f.write("- 09:00 UTC: worked on stuff\n")

    code = run_main(monkeypatch, {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s2"})
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "worked on stuff" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_resume_does_not_inject(monkeypatch, isolate_dirs, capsys):
    isolate_dirs["standup"].mkdir(parents=True, exist_ok=True)
    with open(sa.yesterday_path(), "w") as f:
        f.write("- stuff\n")

    run_main(monkeypatch, {"hook_event_name": "SessionStart", "source": "resume", "session_id": "s3"})
    assert capsys.readouterr().out == ""


def test_session_start_no_yesterday_file_no_output(monkeypatch, capsys):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s4"})
    assert capsys.readouterr().out == ""


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        sa.main()
    assert exc_info.value.code == 0


def test_session_activity_returns_empty_for_missing_log():
    assert sa.session_activity("no-such-session") == []


def test_read_yesterday_summary_none_when_missing():
    assert sa.read_yesterday_summary() is None


def test_entry_skips_malformed_lines_and_truncates_long_file_list(monkeypatch, isolate_dirs):
    sessions = isolate_dirs["sessions"]
    sessions.mkdir()
    files = [f"/p/f{n:02d}.py" for n in range(12)]
    with open(sessions / "s5.jsonl", "w") as f:
        f.write("not json\n")
        for path in files:
            f.write(json.dumps({"event": "tool_use", "file_path": path}) + "\n")

    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s5"})

    entry = open(sa.today_path()).read()
    assert "12개 파일 작업" in entry
    assert ", ".join(files[:10]) + " 외 2개" in entry
    assert "/p/f10.py" not in entry


def test_unknown_event_writes_nothing(monkeypatch, isolate_dirs, capsys):
    write_session_log(isolate_dirs["sessions"], "s6", [{"event": "tool_use", "file_path": "/p/a.py"}])
    assert run_main(monkeypatch, {"hook_event_name": "PreCompact", "session_id": "s6"}) == 0
    assert capsys.readouterr().out == ""
    assert not os.path.exists(isolate_dirs["standup"])
