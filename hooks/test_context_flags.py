import io
import json

import pytest

import context_flags as cf


@pytest.fixture(autouse=True)
def isolate_flags_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_HOOK_FLAGS_DIR", str(tmp_path))
    yield tmp_path


def run_main(monkeypatch, event):
    raw = event if isinstance(event, str) else json.dumps(event)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    with pytest.raises(SystemExit) as exc_info:
        cf.main()
    return exc_info.value.code


def read_flags(tmp_path, session_id):
    return json.loads((tmp_path / f"{session_id}.json").read_text())


def test_flags_dir_respects_env(isolate_flags_dir):
    assert cf.flags_dir() == str(isolate_flags_dir)


def test_session_start_compact_sets_post_compact(monkeypatch, isolate_flags_dir):
    code = run_main(
        monkeypatch,
        {"hook_event_name": "SessionStart", "session_id": "s1", "source": "compact"},
    )
    assert code == 0
    flags = read_flags(isolate_flags_dir, "s1")
    assert flags["session_id"] == "s1"
    assert flags["post_compact"] is True
    assert flags["compact_count"] == 1
    assert flags["compacted_at"]
    assert flags["last_start_source"] == "compact"
    assert flags["updated_at"]


def test_compact_count_accumulates(monkeypatch, isolate_flags_dir):
    for _ in range(2):
        run_main(
            monkeypatch,
            {"hook_event_name": "SessionStart", "session_id": "s1", "source": "compact"},
        )
    assert read_flags(isolate_flags_dir, "s1")["compact_count"] == 2


def test_session_start_startup_writes_post_compact_false(monkeypatch, isolate_flags_dir):
    run_main(
        monkeypatch,
        {"hook_event_name": "SessionStart", "session_id": "s2", "source": "startup"},
    )
    flags = read_flags(isolate_flags_dir, "s2")
    assert flags["post_compact"] is False
    assert flags["compact_count"] == 0


def test_clear_resets_post_compact(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s3", "source": "compact"})
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s3", "source": "clear"})
    flags = read_flags(isolate_flags_dir, "s3")
    assert flags["post_compact"] is False
    assert flags["compact_count"] == 1


def test_resume_keeps_post_compact(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s4", "source": "compact"})
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s4", "source": "resume"})
    flags = read_flags(isolate_flags_dir, "s4")
    assert flags["post_compact"] is True
    assert flags["last_start_source"] == "resume"


def test_pre_compact_records_trigger(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "PreCompact", "session_id": "s5", "trigger": "auto"})
    flags = read_flags(isolate_flags_dir, "s5")
    assert flags["compact_trigger"] == "auto"
    assert flags["pre_compact_at"]


def test_stop_records_parallel_session(monkeypatch, isolate_flags_dir):
    run_main(
        monkeypatch,
        {"hook_event_name": "Stop", "session_id": "s6", "background_tasks": [{"id": "a"}, {"id": "b"}]},
    )
    flags = read_flags(isolate_flags_dir, "s6")
    assert flags["parallel_session"] is True
    assert flags["background_task_count"] == 2
    assert flags["parallel_checked_at"]


def test_stop_without_background_tasks_clears_parallel_session(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s7", "background_tasks": ["x"]})
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s7", "background_tasks": []})
    flags = read_flags(isolate_flags_dir, "s7")
    assert flags["parallel_session"] is False
    assert flags["background_task_count"] == 0


def test_events_merge_into_one_file(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s8", "source": "compact"})
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s8", "background_tasks": ["x"]})
    flags = read_flags(isolate_flags_dir, "s8")
    assert flags["post_compact"] is True
    assert flags["parallel_session"] is True


def test_unknown_event_writes_nothing(monkeypatch, isolate_flags_dir):
    assert run_main(monkeypatch, {"hook_event_name": "PostToolUse", "session_id": "s9"}) == 0
    assert not (isolate_flags_dir / "s9.json").exists()


def test_malformed_stdin_exits_zero(monkeypatch, isolate_flags_dir):
    assert run_main(monkeypatch, "not json") == 0
    assert list(isolate_flags_dir.iterdir()) == []


def test_non_dict_payload_exits_zero(monkeypatch, isolate_flags_dir):
    assert run_main(monkeypatch, "[1, 2]") == 0


def test_corrupt_existing_flag_file_is_replaced(monkeypatch, isolate_flags_dir):
    (isolate_flags_dir / "s10.json").write_text("{broken")
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s10", "source": "compact"})
    assert read_flags(isolate_flags_dir, "s10")["post_compact"] is True


def test_session_id_cannot_escape_flags_dir(monkeypatch, isolate_flags_dir):
    run_main(
        monkeypatch,
        {"hook_event_name": "SessionStart", "session_id": "../../evil", "source": "compact"},
    )
    assert (isolate_flags_dir / "evil.json").exists()
    assert not (isolate_flags_dir.parent.parent / "evil.json").exists()


def test_missing_session_id_uses_unknown(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "source": "compact"})
    assert (isolate_flags_dir / "unknown.json").exists()


def test_fail_open_on_write_error(monkeypatch, isolate_flags_dir):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cf, "write_flags", boom)
    assert run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s11", "source": "compact"}) == 0


def test_no_tmp_files_left_behind(monkeypatch, isolate_flags_dir):
    run_main(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s12", "source": "compact"})
    assert [p.name for p in isolate_flags_dir.iterdir()] == ["s12.json"]


def test_read_flags_returns_empty_when_missing(isolate_flags_dir):
    assert cf.read_flags("nope") == {}


def test_write_flags_failure_removes_tmp_and_keeps_old_file(isolate_flags_dir):
    cf.write_flags("s13", {"post_compact": True})
    with pytest.raises(TypeError):
        cf.write_flags("s13", {"bad": {1, 2}})  # a set isn't JSON-serializable
    assert [p.name for p in isolate_flags_dir.iterdir()] == ["s13.json"]
    assert read_flags(isolate_flags_dir, "s13") == {"post_compact": True}
