import io
import json
import os

import pytest

import pre_compact_backup as pcb


@pytest.fixture(autouse=True)
def isolate_backup_dir(tmp_path, monkeypatch):
    backup_dir = str(tmp_path / "transcript_backups")
    monkeypatch.setattr(pcb, "BACKUP_DIR", backup_dir)
    yield {"backup_dir": backup_dir}


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        pcb.main()
    return exc_info.value.code


def test_backup_transcript_creates_copy(tmp_path, isolate_backup_dir):
    src = tmp_path / "transcript.jsonl"
    src.write_text('{"role": "user", "content": "hi"}\n')

    dest = pcb.backup_transcript(str(src), "session-abc")

    assert dest is not None
    assert os.path.isfile(dest)
    assert open(dest).read() == open(src).read()


def test_backup_transcript_missing_file_returns_none(isolate_backup_dir):
    assert pcb.backup_transcript("/no/such/file.jsonl", "session-x") is None


def test_backup_transcript_missing_path_returns_none(isolate_backup_dir):
    assert pcb.backup_transcript(None, "session-x") is None


def test_main_backs_up_transcript_on_precompact(monkeypatch, tmp_path, isolate_backup_dir):
    src = tmp_path / "transcript.jsonl"
    src.write_text('{"role": "assistant"}\n')

    code = run_main(
        monkeypatch,
        {"hook_event_name": "PreCompact", "session_id": "s1", "transcript_path": str(src)},
    )
    assert code == 0
    backups = os.listdir(isolate_backup_dir["backup_dir"])
    assert len(backups) == 1
    assert backups[0].startswith("s1-")


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        pcb.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_without_transcript_path(monkeypatch, isolate_backup_dir):
    code = run_main(monkeypatch, {"hook_event_name": "PreCompact", "session_id": "s2"})
    assert code == 0
    assert not os.path.isdir(isolate_backup_dir["backup_dir"])
