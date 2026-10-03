---
id: TASK-41
title: >-
  훅 테스트 커버리지 100% (1/2) —
  config_guard·backlog_commit_scope·pipeline_trace·pr_provenance_stamp
status: To Do
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 17:21'
labels:
  - tests
  - coverage
dependencies:
  - TASK-37
  - TASK-38
  - TASK-39
  - TASK-40
  - TASK-45
  - TASK-46
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-03 기준 전체 커버리지 96%(6047줄 중 251줄 미커버). 미커버의 대부분이 이 네 훅에 몰려 있다(config_guard 84%, backlog_commit_scope 89%, pipeline_trace 93%, pr_provenance_stamp 93%). 미커버 분기는 대부분 방어 경로(파싱 실패, 예외 시 fail-open, 드문 셸 문법)다. 줄을 채우려고 의미 없는 테스트를 쓰지 않는다 — 각 테스트는 그 분기가 지켜야 할 동작을 단언한다. 도달 불가능한 코드는 테스트 대신 제거한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 네 훅의 줄·분기 커버리지가 100%다
- [ ] #2 추가한 테스트는 각각 해당 분기의 기대 동작(차단/통과/fail-open)을 단언한다
- [ ] #3 도달 불가능한 코드는 제거하고 그 근거를 커밋 메시지에 남긴다
<!-- AC:END -->
