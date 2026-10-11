---
id: DRAFT-5
title: 'pre_compact_backup: 같은 초에 두 번 백업하면 덮어씀'
status: Draft
assignee: []
created_date: '2026-10-05 07:42'
labels:
  - bug
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
hooks/pre_compact_backup.py는 백업 파일 이름을 <session_id>-<UTC %Y%m%dT%H%M%SZ>.jsonl로 만든다. 타임스탬프 해상도가 1초라 같은 세션에서 1초 안에 두 번 PreCompact가 일어나면 뒤 백업이 앞 백업을 덮어써 transcript 사본 하나를 잃는다. TASK-53 재작성 중 발견(재작성 전 코드에도 있던 동작).

후보: 마이크로초까지 넣거나, 이름이 이미 있으면 -1, -2 접미사를 붙이거나, 열 때 배타 생성(x 모드)으로 충돌을 감지.
<!-- SECTION:DESCRIPTION:END -->
