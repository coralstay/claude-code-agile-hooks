---
id: TASK-33
title: background_tasks 실제 원소 형태 확인 — block_stop_if_dirty 예외의 전제 검증
status: In Progress
assignee: []
created_date: '2026-10-03 07:58'
updated_date: '2026-10-03 08:02'
labels:
  - hooks
  - measure
dependencies: []
references:
  - TASK-31
documentation:
  - backlog/docs/doc-3 - 훅-시스템-구조적-문제-5가지와-컨텍스트-플래그-1차-구현.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-31은 Stop payload의 background_tasks가 비어 있지 않으면 block_stop_if_dirty를 통과시킨다. 원소 형태는 미확인이다. 끝난 작업이 목록에 남는다면 서브에이전트를 한 번 띄운 세션은 dirty 검사가 영구히 꺼진다. 서브에이전트 실행 중/종료 후 Stop payload를 실제로 덤프해 확인하고, 필요하면 상태 필터를 넣는다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 서브에이전트 실행 중과 종료 후의 Stop payload background_tasks를 실측해 doc-3에 기록한다
- [ ] #2 끝난 작업이 남는다면 실행 중인 것만 세도록 고치고 테스트를 추가한다
<!-- AC:END -->
