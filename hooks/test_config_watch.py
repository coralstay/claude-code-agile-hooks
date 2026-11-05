import io
import json

import pytest

import config_watch as cw


@pytest.fixture(autouse=True)
def isolate_log(tmp_path, monkeypatch):
    log_path = str(tmp_path / "config-watch.jsonl")
    monkeypatch.setattr(cw, "LOG_PATH", log_path)
    monkeypatch.delenv("CONFIG_WATCH_BLOCK", raising=False)
    yield log_path


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        cw.main()
    return exc_info.value.code


def test_logs_and_allows_by_default(monkeypatch, isolate_log):
    code = run_main(monkeypatch, {"source": "user_settings", "file_path": "/x/settings.json"})
    assert code == 0
    lines = open(isolate_log).read().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["config_type"] == "user_settings"
    assert record["file_path"] == "/x/settings.json"


def test_blocks_when_block_env_set(monkeypatch, capsys):
    monkeypatch.setenv("CONFIG_WATCH_BLOCK", "true")
    code = run_main(monkeypatch, {"source": "project_settings", "file_path": "/x/.claude/settings.json"})
    assert code == 2
    assert "project_settings" in capsys.readouterr().err


def test_policy_settings_never_blocked_even_with_block_env(monkeypatch):
    monkeypatch.setenv("CONFIG_WATCH_BLOCK", "true")
    assert run_main(monkeypatch, {"source": "policy_settings", "file_path": "/x/managed.json"}) == 0


def test_multiple_events_append_multiple_lines(monkeypatch, isolate_log):
    run_main(monkeypatch, {"source": "skills"})
    run_main(monkeypatch, {"source": "local_settings"})
    lines = open(isolate_log).read().splitlines()
    assert len(lines) == 2


def test_unknown_fields_default_to_unknown(monkeypatch, isolate_log):
    run_main(monkeypatch, {})
    record = json.loads(open(isolate_log).read().splitlines()[0])
    assert record["config_type"] == "unknown"
    assert record["file_path"] == "unknown"


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch, isolate_log):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        cw.main()
    assert exc_info.value.code == 0
    import os

    assert not os.path.exists(isolate_log)


def test_append_log_creates_directory(tmp_path, monkeypatch):
    nested = str(tmp_path / "nested" / "dir" / "log.jsonl")
    monkeypatch.setattr(cw, "LOG_PATH", nested)
    cw.append_log({"a": 1})
    assert json.loads(open(nested).read().strip()) == {"a": 1}
