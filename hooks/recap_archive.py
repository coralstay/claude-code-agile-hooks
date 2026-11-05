#!/usr/bin/env python3
"""SessionStart + SessionEnd
TASK-44: keep Claude Code's session recaps beyond the transcript cleanup.

The grey recap Claude Code shows when you come back to an idle session is
stored in the session transcript as a record
`{"type": "system", "subtype": "away_summary", "content": "...", "uuid",
"sessionId", "timestamp", "gitBranch", "cwd", ...}`. Transcripts
(~/.claude/projects/<slug>/<sessionId>.jsonl) are deleted after
cleanupPeriodDays (default 30), and the recaps go with them. This hook
copies every away_summary record into an append-only archive:

  $CC_RECAP_ARCHIVE_DIR/recap-archive.jsonl
  (default ~/.claude/hooks-logs/recap-archive.jsonl)

one JSON object per line with timestamp, sessionId, uuid, gitBranch, cwd
and content (verbatim, including Claude Code's "(disable recaps in /config)"
suffix), deduplicated by (sessionId, uuid).

When to archive (AC2) - measured 2026-10-04 on 77 real transcripts (66
recaps in 26 files):
- a recap is written into the transcript *during* the session, about three
  minutes after a turn ends with no input (idle before the recap: min 182s,
  median 183s, max 577s; the record before it is the turn's
  `system/turn_duration` in 58 of 66 cases);
- it is followed by more records in 60 of 66 cases (the user came back),
  median 617 records before the end of the file - so it is not an
  end-of-session artifact, and SessionEnd may never fire for a session that
  is killed or whose terminal is closed;
- the 6 recaps that sit at the end of their file are sessions abandoned
  while idle.
So a recap is already on disk long before any session event that follows
it, and the reliable trigger is the *next* session event anywhere: on
SessionStart (and SessionEnd, which closes the gap for the last session
before a long break) the hook sweeps every transcript, not just its own.
The sweep is incremental - a state file keeps a byte offset per transcript
and only bytes appended since the last sweep are read - so a sweep with
nothing new is a stat() per transcript. Measured on the same machine
(77 transcripts, 263 MB, 66 recaps): first full sweep 0.31s, a sweep with
nothing new 2ms in-process (0.05s for the whole hook process).

Concurrency: the whole sweep (read state, scan, append, save state) runs
under an exclusive fcntl lock; a second session starting at the same
moment skips its sweep instead of waiting (the holder archives the same
records). Fail-open: any exception exits 0 with no output.

Query CLI (AC3):
  python3 recap_archive.py query [--project SUBSTR] [--since YYYY-MM-DD]
                                 [--until YYYY-MM-DD] [--limit N] [--json]
--project matches a substring of the recorded cwd, --since/--until compare
the UTC date of the recap (both inclusive), --limit keeps the newest N.

Recaps contain work details: the archive stays in the home directory and
nothing is sent anywhere. Recaps from transcripts deleted before this hook
was installed can't be recovered, and with recaps disabled in /config there
is nothing to archive.

Fully self-contained: no imports from any other file in this repo."""

import argparse
import contextlib
import glob
import json
import os
import sys
import tempfile

try:
    import fcntl
except ImportError:  # non-POSIX: sweep without the file lock
    fcntl = None

ARCHIVE_NAME = "recap-archive.jsonl"
STATE_NAME = "recap-archive.state.json"
LOCK_NAME = "recap-archive.lock"
FIELDS = ("timestamp", "sessionId", "uuid", "gitBranch", "cwd", "content")
MARKER = b'"away_summary"'
EVENTS = ("SessionStart", "SessionEnd")


def archive_dir():
    return os.environ.get("CC_RECAP_ARCHIVE_DIR") or os.path.expanduser(
        "~/.claude/hooks-logs"
    )


def projects_dir():
    return os.environ.get("CC_RECAP_PROJECTS_DIR") or os.path.expanduser(
        "~/.claude/projects"
    )


def archive_path():
    return os.path.join(archive_dir(), ARCHIVE_NAME)


def state_path():
    return os.path.join(archive_dir(), STATE_NAME)


def transcripts():
    return sorted(glob.glob(os.path.join(glob.escape(projects_dir()), "*", "*.jsonl")))


def load_json(path, default):
    try:
        with open(path) as f:
            value = json.load(f)
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def save_json(path, value):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def to_entry(line):
    """The archive entry for one transcript line, or None if it isn't an
    away_summary record."""
    if MARKER not in line:
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("subtype") != "away_summary":
        return None
    if not record.get("sessionId") or not record.get("uuid"):
        return None
    return {field: record.get(field) for field in FIELDS}


def scan(path, offset):
    """Entries in the complete lines of `path` from byte `offset`, and the
    offset just past the last complete line (a line still being written is
    left for the next sweep)."""
    entries = []
    with open(path, "rb") as f:
        f.seek(offset)
        for line in f:
            if not line.endswith(b"\n"):
                break
            offset += len(line)
            entry = to_entry(line)
            if entry:
                entries.append(entry)
    return entries, offset


def start_offset(state, path, st):
    """Where to resume: 0 for a new, replaced or truncated file."""
    seen = state.get(path)
    if not isinstance(seen, dict) or seen.get("ino") != st.st_ino:
        return 0
    offset = seen.get("offset")
    if not isinstance(offset, int) or offset > st.st_size:
        return 0
    return offset


def archived_keys():
    keys = set()
    try:
        with open(archive_path(), encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError, AttributeError):
                    entry = json.loads(line)
                    keys.add((entry.get("sessionId"), entry.get("uuid")))
    except FileNotFoundError:
        pass
    return keys


def sweep():
    """Archive the away_summary records appended to any transcript since
    the last sweep. Returns how many new entries were archived."""
    state = load_json(state_path(), {})
    new_state, found = {}, []
    for path in transcripts():
        try:
            st = os.stat(path)
            offset = start_offset(state, path, st)
            if offset < st.st_size:
                entries, offset = scan(path, offset)
                found.extend(entries)
        except OSError:
            continue  # vanished or unreadable: retry from scratch next time
        new_state[path] = {"ino": st.st_ino, "offset": offset}
    added = 0
    if found:
        keys = archived_keys()
        with open(archive_path(), "a", encoding="utf-8") as f:
            for entry in found:
                key = (entry["sessionId"], entry["uuid"])
                if key in keys:
                    continue
                keys.add(key)
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                added += 1
    # deleted transcripts drop out of the state, so it stays small
    save_json(state_path(), new_state)
    return added


class SweepLock:
    """Exclusive, non-blocking: `acquired` is False if another process is
    sweeping right now."""

    def __init__(self):
        self.fd = None
        self.acquired = True

    def __enter__(self):
        if fcntl is not None:
            self.fd = os.open(
                os.path.join(archive_dir(), LOCK_NAME), os.O_CREAT | os.O_RDWR, 0o600
            )
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.acquired = False
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            if self.acquired:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
        return False


def run_hook(data):
    if not isinstance(data, dict) or data.get("hook_event_name") not in EVENTS:
        return
    os.makedirs(archive_dir(), exist_ok=True)
    with SweepLock() as lock:
        if lock.acquired:
            sweep()


# --- query CLI ---


def read_archive():
    entries = []
    try:
        with open(archive_path(), encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError):
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        entries.append(entry)
    except FileNotFoundError:
        pass
    return entries


def select(entries, project=None, since=None, until=None, limit=None):
    """Matching entries, oldest first; `limit` keeps the newest N."""
    out = []
    for entry in entries:
        day = str(entry.get("timestamp") or "")[:10]
        if project and project not in str(entry.get("cwd") or ""):
            continue
        if since and day < since:
            continue
        if until and day > until:
            continue
        out.append(entry)
    out.sort(key=lambda e: str(e.get("timestamp") or ""))
    if limit is not None:
        out = out[-limit:] if limit > 0 else []
    return out


def format_entry(entry):
    return (
        f"{entry.get('timestamp') or '?'}  [{entry.get('gitBranch') or '-'}]  "
        f"{entry.get('cwd') or '?'}\n  {entry.get('content') or ''}"
    )


def iso_date(value):
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")
    return value


def query(argv):
    parser = argparse.ArgumentParser(
        prog="recap_archive.py query", description="Print archived session recaps."
    )
    parser.add_argument("--project", help="substring of the recap's cwd")
    parser.add_argument("--since", type=iso_date, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--until", type=iso_date, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--limit", type=int, help="newest N only")
    parser.add_argument("--json", action="store_true", help="one JSON object per line")
    args = parser.parse_args(argv)
    rows = select(read_archive(), args.project, args.since, args.until, args.limit)
    for entry in rows:
        if args.json:
            print(json.dumps(entry, ensure_ascii=False))
        else:
            print(format_entry(entry))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "query":
        sys.exit(query(argv[1:]))
    try:
        run_hook(json.load(sys.stdin))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
