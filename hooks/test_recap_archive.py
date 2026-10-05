import io
import json
import os

import pytest

import recap_archive as ra


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    projects = tmp_path / "projects"
    archive.mkdir()
    projects.mkdir()
    monkeypatch.setenv("CC_RECAP_ARCHIVE_DIR", str(archive))
    monkeypatch.setenv("CC_RECAP_PROJECTS_DIR", str(projects))
    return {"archive": archive, "projects": projects}


def recap(uuid, session="s1", ts="2026-10-03T07:40:50.510Z", **extra):
    record = {
        "parentUuid": "p",
        "isSidechain": False,
        "type": "system",
        "subtype": "away_summary",
        "content": f"recap {uuid} (disable recaps in /config)",
        "timestamp": ts,
        "uuid": uuid,
        "cwd": "/Users/me/githubs/interlock",
        "sessionId": session,
        "gitBranch": "task/TASK-44",
        "slug": "x",
    }
    record.update(extra)
    return json.dumps(record, ensure_ascii=False)


def other(text="hi"):
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}})


def transcript(dirs, name="s1", project="-Users-me-githubs-interlock"):
    d = dirs["projects"] / project
    d.mkdir(exist_ok=True)
    return d / f"{name}.jsonl"


def append(path, *lines, newline=True):
    with open(path, "a") as f:
        f.write("\n".join(lines) + ("\n" if newline else ""))


def archived(dirs):
    path = dirs["archive"] / ra.ARCHIVE_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def run_main(monkeypatch, stdin, argv=()):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    with pytest.raises(SystemExit) as exc:
        ra.main(list(argv))
    return exc.value.code


def start(monkeypatch, event="SessionStart"):
    return run_main(monkeypatch, json.dumps({"hook_event_name": event}))


# --- paths ---


def test_default_dirs_are_under_home(monkeypatch):
    monkeypatch.delenv("CC_RECAP_ARCHIVE_DIR")
    monkeypatch.delenv("CC_RECAP_PROJECTS_DIR")
    assert ra.archive_dir() == os.path.expanduser("~/.claude/hooks-logs")
    assert ra.projects_dir() == os.path.expanduser("~/.claude/projects")


def test_main_without_argv_reads_sys_argv(monkeypatch, dirs):
    monkeypatch.setattr("sys.argv", ["recap_archive.py"])
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as exc:
        ra.main()
    assert exc.value.code == 0


# --- archiving ---


def test_archives_recaps_with_the_listed_fields(monkeypatch, dirs):
    t = transcript(dirs)
    append(t, other(), recap("u1"), other("again"))
    assert start(monkeypatch) == 0
    entries = archived(dirs)
    assert entries == [
        {
            "timestamp": "2026-10-03T07:40:50.510Z",
            "sessionId": "s1",
            "uuid": "u1",
            "gitBranch": "task/TASK-44",
            "cwd": "/Users/me/githubs/interlock",
            "content": "recap u1 (disable recaps in /config)",
        }
    ]


def test_session_end_also_sweeps(monkeypatch, dirs):
    append(transcript(dirs), recap("u1"))
    assert start(monkeypatch, "SessionEnd") == 0
    assert [e["uuid"] for e in archived(dirs)] == ["u1"]


def test_sweeps_every_project_transcript(monkeypatch, dirs):
    append(transcript(dirs, "s1", "proj-a"), recap("u1", "s1"))
    append(transcript(dirs, "s2", "proj-b"), recap("u2", "s2"))
    start(monkeypatch)
    assert sorted(e["uuid"] for e in archived(dirs)) == ["u1", "u2"]


@pytest.mark.parametrize("event", [None, "Stop", "UserPromptSubmit", "PreCompact"])
def test_other_events_do_nothing(monkeypatch, dirs, event):
    append(transcript(dirs), recap("u1"))
    run_main(monkeypatch, json.dumps({"hook_event_name": event}))
    assert archived(dirs) == []
    assert not (dirs["archive"] / ra.STATE_NAME).exists()


@pytest.mark.parametrize("stdin", ["", "{not json", "[1, 2]", '"x"'])
def test_bad_stdin_exits_zero_without_writing(monkeypatch, dirs, stdin):
    append(transcript(dirs), recap("u1"))
    assert run_main(monkeypatch, stdin) == 0
    assert archived(dirs) == []


def test_fail_open_on_unexpected_error(monkeypatch, dirs):
    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(ra, "sweep", boom)
    assert start(monkeypatch) == 0


def test_creates_missing_archive_dir(monkeypatch, dirs, tmp_path):
    target = tmp_path / "deep" / "logs"
    monkeypatch.setenv("CC_RECAP_ARCHIVE_DIR", str(target))
    append(transcript(dirs), recap("u1"))
    start(monkeypatch)
    assert (target / ra.ARCHIVE_NAME).exists()


def test_no_projects_dir_writes_only_state(monkeypatch, dirs, tmp_path):
    monkeypatch.setenv("CC_RECAP_PROJECTS_DIR", str(tmp_path / "missing"))
    start(monkeypatch)
    assert archived(dirs) == []
    assert json.loads((dirs["archive"] / ra.STATE_NAME).read_text()) == {}


def test_dedup_across_sweeps_and_sessions_reopened(monkeypatch, dirs):
    t = transcript(dirs)
    append(t, recap("u1"))
    start(monkeypatch)
    # state lost: the whole file is read again, the archive still dedups
    (dirs["archive"] / ra.STATE_NAME).unlink()
    append(t, recap("u2"))
    start(monkeypatch)
    start(monkeypatch)
    assert [e["uuid"] for e in archived(dirs)] == ["u1", "u2"]


def test_dedup_within_one_sweep(monkeypatch, dirs):
    # the same record copied into a resumed/forked session's transcript
    append(transcript(dirs, "s1"), recap("u1"))
    append(transcript(dirs, "s2"), recap("u1"))
    start(monkeypatch)
    assert len(archived(dirs)) == 1


def test_same_uuid_in_other_session_is_kept(monkeypatch, dirs):
    append(transcript(dirs), recap("u1", "s1"), recap("u1", "s2"))
    start(monkeypatch)
    assert [(e["sessionId"], e["uuid"]) for e in archived(dirs)] == [
        ("s1", "u1"),
        ("s2", "u1"),
    ]


def test_incremental_reads_only_new_bytes(monkeypatch, dirs):
    t = transcript(dirs)
    append(t, other(), recap("u1"))
    start(monkeypatch)
    size = t.stat().st_size
    state = json.loads((dirs["archive"] / ra.STATE_NAME).read_text())
    assert state[str(t)]["offset"] == size

    seen = []
    real_scan = ra.scan
    monkeypatch.setattr(ra, "scan", lambda p, o: seen.append(o) or real_scan(p, o))
    start(monkeypatch)  # nothing new: the file isn't opened
    assert seen == []
    append(t, recap("u2"))
    start(monkeypatch)
    assert seen == [size]
    assert [e["uuid"] for e in archived(dirs)] == ["u1", "u2"]


def test_partial_last_line_waits_for_next_sweep(monkeypatch, dirs):
    t = transcript(dirs)
    line = recap("u1")
    append(t, other())
    append(t, line[:20], newline=False)
    start(monkeypatch)
    assert archived(dirs) == []
    append(t, line[20:])
    start(monkeypatch)
    assert [e["uuid"] for e in archived(dirs)] == ["u1"]


def test_truncated_or_replaced_file_is_read_from_start(monkeypatch, dirs):
    t = transcript(dirs)
    append(t, other("a" * 500), recap("u1"))
    start(monkeypatch)
    t.write_text(recap("u2") + "\n")  # shorter than the stored offset
    start(monkeypatch)
    replacement = t.with_suffix(".new")
    replacement.write_text(recap("u2") + "\n" + recap("u3") + "\n")
    os.replace(replacement, t)  # new inode, longer
    start(monkeypatch)
    assert [e["uuid"] for e in archived(dirs)] == ["u1", "u2", "u3"]


@pytest.mark.parametrize(
    "stored",
    ["garbage", {"ino": None, "offset": 5}, {"offset": "x"}, []],
)
def test_bad_state_entries_restart_from_zero(monkeypatch, dirs, stored):
    t = transcript(dirs)
    append(t, recap("u1"))
    state = {str(t): stored} if not isinstance(stored, list) else stored
    if isinstance(stored, dict) and "ino" not in stored:
        stored["ino"] = t.stat().st_ino
    (dirs["archive"] / ra.STATE_NAME).write_text(json.dumps(state))
    start(monkeypatch)
    assert [e["uuid"] for e in archived(dirs)] == ["u1"]


def test_corrupt_state_file_is_ignored(monkeypatch, dirs):
    append(transcript(dirs), recap("u1"))
    (dirs["archive"] / ra.STATE_NAME).write_text("{oops")
    start(monkeypatch)
    assert len(archived(dirs)) == 1


def test_deleted_transcripts_drop_out_of_state(monkeypatch, dirs):
    t1 = transcript(dirs, "s1")
    t2 = transcript(dirs, "s2")
    append(t1, recap("u1"))
    append(t2, other())
    start(monkeypatch)
    t1.unlink()
    start(monkeypatch)
    state = json.loads((dirs["archive"] / ra.STATE_NAME).read_text())
    assert list(state) == [str(t2)]
    assert len(archived(dirs)) == 1  # the archive outlives the transcript


def test_unreadable_transcript_is_skipped_and_retried(monkeypatch, dirs):
    t1 = transcript(dirs, "s1")
    t2 = transcript(dirs, "s2")
    append(t1, recap("u1", "s1"))
    append(t2, recap("u2", "s2"))
    real_scan = ra.scan

    def flaky(path, offset):
        if path == str(t1):
            raise PermissionError(path)
        return real_scan(path, offset)

    monkeypatch.setattr(ra, "scan", flaky)
    start(monkeypatch)
    state = json.loads((dirs["archive"] / ra.STATE_NAME).read_text())
    assert str(t1) not in state
    monkeypatch.setattr(ra, "scan", real_scan)
    start(monkeypatch)
    assert sorted(e["uuid"] for e in archived(dirs)) == ["u1", "u2"]


def test_failed_append_keeps_old_state(monkeypatch, dirs):
    t = transcript(dirs)
    append(t, recap("u1"))
    monkeypatch.setattr(ra, "archived_keys", lambda: 1 / 0)
    start(monkeypatch)
    assert not (dirs["archive"] / ra.STATE_NAME).exists()


def test_failed_state_write_leaves_no_temp_file(monkeypatch, dirs):
    append(transcript(dirs), recap("u1"))

    def bad_dump(*a, **k):
        raise ValueError("x")

    monkeypatch.setattr(ra.json, "dump", bad_dump)
    start(monkeypatch)
    assert sorted(os.listdir(dirs["archive"])) == [ra.ARCHIVE_NAME, ra.LOCK_NAME]


def test_archive_with_bad_lines_still_dedups(monkeypatch, dirs):
    (dirs["archive"] / ra.ARCHIVE_NAME).write_text(
        "not json\n[1]\n" + json.dumps({"sessionId": "s1", "uuid": "u1"}) + "\n"
    )
    append(transcript(dirs), recap("u1"), recap("u2"))
    start(monkeypatch)
    lines = (dirs["archive"] / ra.ARCHIVE_NAME).read_text().splitlines()
    assert len(lines) == 4
    assert json.loads(lines[-1])["uuid"] == "u2"


@pytest.mark.parametrize(
    "line",
    [
        other(),
        '{"broken": "away_summary"',
        '["away_summary"]',
        json.dumps({"type": "user", "content": "talks about away_summary"}),
        recap("", session="s1"),
        recap("u1", session=""),
    ],
)
def test_non_recap_lines_are_ignored(line):
    assert ra.to_entry(line.encode()) is None


def test_missing_optional_fields_become_null():
    line = json.dumps(
        {"subtype": "away_summary", "sessionId": "s", "uuid": "u"}
    ).encode()
    assert ra.to_entry(line) == {
        "timestamp": None,
        "sessionId": "s",
        "uuid": "u",
        "gitBranch": None,
        "cwd": None,
        "content": None,
    }


def test_non_ascii_content_is_stored_verbatim(monkeypatch, dirs):
    append(transcript(dirs), recap("u1", content="한국어 recap"))
    start(monkeypatch)
    raw = (dirs["archive"] / ra.ARCHIVE_NAME).read_text(encoding="utf-8")
    assert "한국어 recap" in raw


# --- locking ---


def test_busy_lock_skips_the_sweep(monkeypatch, dirs):
    import fcntl

    append(transcript(dirs), recap("u1"))
    fd = os.open(dirs["archive"] / ra.LOCK_NAME, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        assert start(monkeypatch) == 0
        assert archived(dirs) == []
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    start(monkeypatch)
    assert len(archived(dirs)) == 1


def test_lock_is_released_after_sweep(monkeypatch, dirs):
    import fcntl

    start(monkeypatch)
    fd = os.open(dirs["archive"] / ra.LOCK_NAME, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # would raise if held
    finally:
        os.close(fd)


def test_without_fcntl_sweeps_unlocked(monkeypatch, dirs):
    """On a platform without fcntl the module still imports and sweeps,
    just without the lock."""
    import importlib.util
    import sys

    monkeypatch.setitem(sys.modules, "fcntl", None)  # makes `import fcntl` fail
    spec = importlib.util.spec_from_file_location("recap_archive_nofcntl", ra.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.fcntl is None
    append(transcript(dirs), recap("u1"))
    mod.run_hook({"hook_event_name": "SessionStart"})
    assert len(archived(dirs)) == 1
    assert not (dirs["archive"] / ra.LOCK_NAME).exists()


# --- query CLI ---


def seed(dirs, *entries):
    with open(dirs["archive"] / ra.ARCHIVE_NAME, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(
                (e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)) + "\n"
            )


E1 = {
    "timestamp": "2026-09-20T10:00:00Z",
    "sessionId": "a",
    "uuid": "1",
    "gitBranch": "main",
    "cwd": "/w/git-format",
    "content": "first",
}
E2 = {
    "timestamp": "2026-10-01T10:00:00Z",
    "sessionId": "b",
    "uuid": "2",
    "gitBranch": "task/TASK-1",
    "cwd": "/w/interlock",
    "content": "second",
}
E3 = {
    "timestamp": "2026-10-03T23:59:59Z",
    "sessionId": "c",
    "uuid": "3",
    "gitBranch": None,
    "cwd": "/w/interlock",
    "content": "third",
}


def query(monkeypatch, capsys, *args):
    code = run_main(monkeypatch, "", ["query", *args])
    return code, capsys.readouterr().out


def test_query_prints_all_oldest_first(monkeypatch, capsys, dirs):
    seed(dirs, E3, E1, E2)
    code, out = query(monkeypatch, capsys)
    assert code == 0
    assert out == (
        "2026-09-20T10:00:00Z  [main]  /w/git-format\n  first\n"
        "2026-10-01T10:00:00Z  [task/TASK-1]  /w/interlock\n  second\n"
        "2026-10-03T23:59:59Z  [-]  /w/interlock\n  third\n"
    )


def test_query_filters_project_and_dates_inclusive(monkeypatch, capsys, dirs):
    seed(dirs, E1, E2, E3)
    _, out = query(monkeypatch, capsys, "--project", "interlock", "--json")
    assert [json.loads(line)["uuid"] for line in out.splitlines()] == ["2", "3"]
    _, out = query(
        monkeypatch, capsys, "--since", "2026-09-20", "--until", "2026-10-01", "--json"
    )
    assert [json.loads(line)["uuid"] for line in out.splitlines()] == ["1", "2"]
    _, out = query(monkeypatch, capsys, "--since", "2026-10-03", "--json")
    assert [json.loads(line)["uuid"] for line in out.splitlines()] == ["3"]


def test_query_limit_keeps_newest(monkeypatch, capsys, dirs):
    seed(dirs, E1, E2, E3)
    _, out = query(monkeypatch, capsys, "--limit", "2", "--json")
    assert [json.loads(line)["uuid"] for line in out.splitlines()] == ["2", "3"]
    _, out = query(monkeypatch, capsys, "--limit", "0")
    assert out == ""


def test_query_json_keeps_non_ascii(monkeypatch, capsys, dirs):
    seed(dirs, dict(E1, content="한국어"))
    _, out = query(monkeypatch, capsys, "--json")
    assert "한국어" in out


def test_query_without_archive_prints_nothing(monkeypatch, capsys, dirs):
    code, out = query(monkeypatch, capsys)
    assert (code, out) == (0, "")


def test_query_skips_bad_lines_and_missing_fields(monkeypatch, capsys, dirs):
    seed(dirs, "garbage", "[1]", {"uuid": "x"})
    _, out = query(monkeypatch, capsys)
    assert out == "?  [-]  ?\n  \n"
    _, out = query(monkeypatch, capsys, "--project", "w", "--since", "2026-01-01")
    assert out == ""


@pytest.mark.parametrize("bad", ["2026-1-01", "20261001", "yesterday"])
def test_query_rejects_bad_dates(monkeypatch, capsys, dirs, bad):
    code = run_main(monkeypatch, "", ["query", "--since", bad])
    assert code == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_select_until_excludes_later_days():
    assert ra.select([E1, E2, E3], until="2026-09-30") == [E1]
