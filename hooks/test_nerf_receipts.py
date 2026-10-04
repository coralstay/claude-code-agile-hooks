import io
import json
import os

import pytest

import nerf_receipts as nr


@pytest.fixture(autouse=True)
def isolate_log(tmp_path, monkeypatch):
    path = str(tmp_path / "nerf-receipts.jsonl")
    monkeypatch.setattr(nr, "LOG_PATH", path)
    yield path


def make_transcript(tmp_path, entries):
    path = tmp_path / "transcript.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return str(path)


ASSISTANT_ENTRY = {
    "type": "assistant",
    "message": {
        "model": "claude-sonnet-5",
        "usage": {
            "iterations": [
                {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 1}
            ]
        },
    },
}


def run_main(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    with pytest.raises(SystemExit) as exc_info:
        nr.main()
    return exc_info.value.code


def read_records(path):
    return [json.loads(line) for line in open(path).read().splitlines()]


def test_posttooluse_records_model_and_tokens(monkeypatch, isolate_log, tmp_path):
    transcript = make_transcript(tmp_path, [ASSISTANT_ENTRY])
    code = run_main(
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "transcript_path": transcript,
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x/main.py"},
        },
    )
    assert code == 0
    record = read_records(isolate_log)[0]
    assert record["model"] == "claude-sonnet-5"
    assert record["tokens"]["input_tokens"] == 10
    assert record["tokens"]["output_tokens"] == 20
    assert record["file_path"] == "/x/main.py"


def test_posttoolusefailure_marks_failed(monkeypatch, isolate_log, tmp_path):
    transcript = make_transcript(tmp_path, [ASSISTANT_ENTRY])
    run_main(
        monkeypatch,
        {"hook_event_name": "PostToolUseFailure", "session_id": "s2", "transcript_path": transcript, "tool_name": "Bash"},
    )
    record = read_records(isolate_log)[0]
    assert record["failed"] is True
    assert record["tool_name"] == "Bash"


def test_stop_event_records_without_tool_fields(monkeypatch, isolate_log, tmp_path):
    transcript = make_transcript(tmp_path, [ASSISTANT_ENTRY])
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s3", "transcript_path": transcript})
    record = read_records(isolate_log)[0]
    assert record["event"] == "Stop"
    assert "tool_name" not in record


def test_sums_multiple_iterations(monkeypatch, isolate_log, tmp_path):
    entry = json.loads(json.dumps(ASSISTANT_ENTRY))
    entry["message"]["usage"]["iterations"].append(
        {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    )
    transcript = make_transcript(tmp_path, [entry])
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s4", "transcript_path": transcript})
    record = read_records(isolate_log)[0]
    assert record["tokens"]["input_tokens"] == 11
    assert record["tokens"]["output_tokens"] == 22


def test_picks_most_recent_assistant_message(monkeypatch, isolate_log, tmp_path):
    older = json.loads(json.dumps(ASSISTANT_ENTRY))
    older["message"]["model"] = "claude-opus-5"
    transcript = make_transcript(tmp_path, [older, ASSISTANT_ENTRY])
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s5", "transcript_path": transcript})
    record = read_records(isolate_log)[0]
    assert record["model"] == "claude-sonnet-5"


def test_handles_missing_transcript_gracefully(monkeypatch, isolate_log):
    code = run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s6", "transcript_path": "/no/such/file.jsonl"})
    assert code == 0
    record = read_records(isolate_log)[0]
    assert record["model"] is None
    assert record["tokens"] is None


def test_handles_missing_transcript_path_field(monkeypatch, isolate_log):
    run_main(monkeypatch, {"hook_event_name": "Stop", "session_id": "s7"})
    record = read_records(isolate_log)[0]
    assert record["model"] is None


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch, isolate_log):
    import os

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        nr.main()
    assert exc_info.value.code == 0
    assert not os.path.exists(isolate_log)


def test_latest_assistant_usage_skips_non_assistant_entries(tmp_path):
    transcript = make_transcript(tmp_path, [{"type": "user", "message": {}}, ASSISTANT_ENTRY])
    model, usage = nr.latest_assistant_usage(transcript)
    assert model == "claude-sonnet-5"
    assert usage is not None


def test_latest_assistant_usage_handles_malformed_line(tmp_path):
    path = tmp_path / "t.jsonl"
    with open(path, "w") as f:
        f.write("not json\n")
        f.write(json.dumps(ASSISTANT_ENTRY) + "\n")
    model, _ = nr.latest_assistant_usage(str(path))
    assert model == "claude-sonnet-5"


def test_sum_tokens_empty_usage():
    totals = nr.sum_tokens({})
    assert totals["input_tokens"] == 0


def test_latest_assistant_usage_walks_back_past_unusable_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    with open(path, "w") as f:
        f.write(json.dumps(ASSISTANT_ENTRY) + "\n")  # oldest: the only usable one
        f.write(json.dumps({"type": "user", "message": {}}) + "\n")
        f.write("not json\n")
        f.write("\n")
        f.write(json.dumps({"type": "assistant", "message": {"model": "m-without-usage"}}) + "\n")
    assert nr.latest_assistant_usage(str(path)) == ("claude-sonnet-5", ASSISTANT_ENTRY["message"]["usage"])


def test_latest_assistant_usage_none_when_no_usable_entry(tmp_path):
    transcript = make_transcript(tmp_path, [{"type": "user", "message": {}}, {"type": "assistant", "message": {}}])
    assert nr.latest_assistant_usage(transcript) == (None, None)


def test_latest_assistant_usage_unreadable_transcript(tmp_path):
    transcript = make_transcript(tmp_path, [ASSISTANT_ENTRY])
    os.chmod(transcript, 0)
    try:
        if os.access(transcript, os.R_OK):  # running as root: permissions don't apply
            pytest.fail("cannot make the transcript unreadable in this environment")
        assert nr.latest_assistant_usage(transcript) == (None, None)
    finally:
        os.chmod(transcript, 0o600)


def test_posttooluse_without_file_path_omits_it(monkeypatch, isolate_log):
    run_main(monkeypatch, {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    [record] = read_records(isolate_log)
    assert record["tool_name"] == "Bash"
    assert "file_path" not in record
