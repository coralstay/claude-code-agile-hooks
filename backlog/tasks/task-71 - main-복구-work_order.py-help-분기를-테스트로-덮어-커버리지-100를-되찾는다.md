---
id: TASK-71
title: 'main 복구: work_order.py --help 분기를 테스트로 덮어 커버리지 100%를 되찾는다'
status: To Do
assignee: []
created_date: '2026-10-30T17:05:00Z'
updated_date: '2026-10-30T17:05:00Z'
labels:
  - bug
  - test
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-31: main(origin/main 9244103)의 커버리지가 99.94%다. e89810b(10-30, 유저 변경 'work_order.py: --help 사용법 출력')가 scripts/work_order.py:223-227에 -h · --help · help 분기를 넣었지만 테스트가 없다. 이 변경은 Antigravity 세션이 PR 없이 main에 올렸다. pre_push_coverage_check가 이 저장소의 모든 push를 막는다(같은 브랜치의 README 복원 3f8abc8 · DRAFT-9 포함).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/work_order.py의 -h · --help · help가 사용법을 stdout에 출력하고 0을 반환하는지 테스트로 확인한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand가 100%로 통과한 로그를 final summary에 남긴다 (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저(2026-10-31): hooks main 복구를 작은 카드로 바로 진행한다.

### Objective
- coverage: scripts/work_order.py 135 stmts, miss 224-227, BrPart 1 → 99.94%.
- 분기: main(argv)에서 argv[0]이 -h · --help · help면 사용법 3줄을 출력하고 0을 반환한다(scripts/work_order.py:222-227).
- 기존 테스트: scripts/test_work_order.py.

### Assessment
분기 동작을 그대로 확인하는 테스트를 scripts/test_work_order.py에 더한다. 코드는 바꾸지 않는다.

### Plan
1. 테스트(표식 <ID>#1) 추가 → 전체 테스트 · 커버리지 100% 확인 → 커밋.
2. Done → push → PR(README 복원 · DRAFT-9 포함, merge commit).
<!-- SECTION:PLAN:END -->
