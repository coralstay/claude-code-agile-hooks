#!/usr/bin/env python3
# ---
# title: pre_compact_backup
# description: 컨텍스트 압축 직전에 세션 트랜스크립트를 바이트 그대로 백업하는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreCompact
Back up the full session transcript right before compaction discards
context, so whatever the summary leaves out can still be read later.

Each backup is a byte-for-byte copy written to
~/.claude/hooks-logs/transcript_backups/<session_id>-<UTC %Y%m%dT%H%M%SZ>.jsonl
A missing or unreadable transcript path is skipped silently; the hook always
exits 0 and never blocks compaction.

This is this repository's own implementation.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

BACKUP_DIR = os.path.expanduser("~/.claude/hooks-logs/transcript_backups")  # ---- 1


def backup_transcript(transcript_path, session_id):
    if not isinstance(transcript_path, str) or not os.path.isfile(transcript_path):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = os.path.join(BACKUP_DIR, f"{session_id}-{stamp}.jsonl")
    shutil.copyfile(transcript_path, dest)  # ---- 2
    return dest


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    data = data if isinstance(data, dict) else {}

    backup_transcript(data.get("transcript_path"), data.get("session_id") or "unknown")  # ---- 3
    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 백업 위치
#   설명: 파일 이름은 `<session_id>-<UTC 시각>.jsonl`이다. 압축이 요약에서 버리는 내용을 나중에 원문으로 다시 읽기 위한 보관소다.
#   관련: hooks/recap_archive.py (recap 보관), backlog draft-5·6 (같은 초 덮어쓰기, session_id의 경로 구분자)
# 2 바이트 그대로 복사
#   설명: 내용을 해석하거나 줄이지 않고 원본 바이트를 복사한다. 같은 초에 두 번 백업하면 덮어쓰고, session_id에 경로 구분자가 있으면 백업 폴더 밖에 쓰는 알려진 한계가 있다(draft-5, draft-6).
# 3 압축을 절대 막지 않는다
#   설명: 트랜스크립트가 없거나 못 읽어도 조용히 건너뛰고 항상 exit 0이다. PreCompact 훅이 압축 자체를 막으면 세션이 멈추기 때문이다.
