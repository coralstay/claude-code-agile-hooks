---
id: TASK-41
title: >-
  훅 테스트 커버리지 100% (1/2) —
  config_guard·backlog_commit_scope·pipeline_trace·pr_provenance_stamp
status: Done
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 17:51'
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
- [x] #1 네 훅의 줄·분기 커버리지가 100%다
- [x] #2 추가한 테스트는 각각 해당 분기의 기대 동작(차단/통과/fail-open)을 단언한다
- [x] #3 도달 불가능한 코드는 제거하고 그 근거를 커밋 메시지에 남긴다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config_guard·backlog_commit_scope·pipeline_trace·pr_provenance_stamp 네 파일을 줄·분기 커버리지 100%로 맞췄다(남은 것은 TASK-42가 설정으로 제외할 if __name__ 줄뿐). 추가한 테스트는 모두 차단/통과/fail-open/반환값을 단언한다. config_guard는 코드 제거 없이 모든 분기를 실제 입력으로 도달시켰다. 제거한 코드: backlog_commit_scope.staging_plan의 도달 불가 elif 조건(앞에서 add/commit 외는 continue하므로 항상 commit) → else, 동작 동일. pipeline_trace의 fcntl ImportError 폴백에 붙어 있던 pragma: no cover를 실제 테스트로 대체. 네 파일 모두 pragma 없음. 1330 passed, 동시 2회 실행도 모두 통과. 발견: config_guard가 uv run --with x rm <보호 경로>를 통과시킨다(uv run 플래그 인자 처리 누락) — 후속 드래프트.
<!-- SECTION:FINAL_SUMMARY:END -->
