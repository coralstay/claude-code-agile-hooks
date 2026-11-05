---
id: DRAFT-6
title: 'pre_compact_backup: session_id에 경로 구분자가 있으면 백업 폴더 밖에 씀'
status: Draft
assignee: []
created_date: '2026-10-05 07:42'
labels:
  - bug
  - security
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
hooks/pre_compact_backup.py는 입력의 session_id를 그대로 파일 이름에 넣는다. session_id에 / 나 .. 가 들어 있으면 BACKUP_DIR(~/.claude/hooks-logs/transcript_backups) 밖 경로에 파일을 만들 수 있다(경로 조작). TASK-53 재작성 중 발견(재작성 전 코드에도 있던 동작).

후보: session_id를 [A-Za-z0-9_-]만 남기도록 정규화하거나, 최종 경로가 BACKUP_DIR 안인지 확인한 뒤에만 쓰기. 같은 패턴이 다른 훅(session_logger 등 세션 ID로 파일 경로를 만드는 곳)에도 있는지 함께 점검.
<!-- SECTION:DESCRIPTION:END -->
