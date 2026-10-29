---
id: TASK-66
title: >-
  require_design_propagation: 태스크 변경을 브랜치 범위가 아니라 커밋 메시지의 태스크 ID로 고른다(쌓인 브랜치 ·
  브랜치 없음 대응)
status: To Do
assignee: []
created_date: 2026-10-22 05:52
updated_date: '2026-10-29T23:49:00Z'
labels:
  - hooks
  - bug
dependencies:
  - TASK-70
references:
  - decision-15
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-63 훅을 최상위 저장소에 읽기 전용으로 돌려 본 결과(2026-10-22): (1) 쌓인 브랜치(task/task-15 → 17 → 18)에서는 'main에 없는 task 브랜치 커밋' 범위에 아래 태스크들의 변경까지 들어가 대상이 부풀려진다 — TASK-17(문서 3개 · 문장 삭제)에 거의 모든 장이 잡혔다. (2) TASK-16처럼 task/<ID> 브랜치 없이 다른 태스크 브랜치에서 작업하면 검사 없이 통과한다. 선행: TASK-63(PR #59) 머지.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 태스크의 design/ 변경은 기준 브랜치에 없는 로컬 커밋 중 메시지(제목 · 본문 · 트레일러)에 그 태스크 ID가 단어 경계로 들어 있는 커밋으로 고른다 — 쌓인 브랜치의 다른 태스크 커밋은 빠진다
- [ ] #2 task/<ID> 브랜치가 없어도 위 규칙으로 커밋을 찾아 검사하고, 그런 커밋이 하나도 없을 때만 통과한다
- [ ] #3 design/을 바꾸는 최상위 커밋에 태스크 ID가 없으면(어느 태스크 변경인지 모르면) -s Done 때 그 커밋을 안내한다 — 조용히 빠뜨리지 않는다
- [ ] #4 README · 훅 docstring에 바뀐 판정 규칙을 반영한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [ ] #2 각 커밋에 TASK ID, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 전파 계획을 승인하면서 전파 훅의 정확도 문제(쌓인 브랜치 · 브랜치 없음)를 고치는 카드도 함께 승인했다(2026-10-22).

### Objective
- TASK-63은 git log task/<ID> --not <기준 브랜치들>로 범위를 잡는다. 쌓인 브랜치에서는 아래 태스크의 커밋이 섞인다.
- task/<ID> 브랜치가 없으면 통과한다(TASK-16 사례).
- 최상위 커밋 대부분은 메시지에 '(TASK-N)'을 적지만, TASK-14 커밋들처럼 ID가 없는 커밋도 있다.

### Assessment
커밋 메시지의 태스크 ID로 고르면 브랜치 구조와 무관해진다. ID 없는 design/ 커밋은 귀속을 알 수 없으므로 안내해 사람이 판단하게 한다.

### Plan
1. AC #1 → #2 → #3 순서로 테스트 먼저(쌓인 브랜치 · 브랜치 없음 · ID 없는 커밋 픽스처).
2. README · docstring, 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 조건(유저, 2026-10-22): TASK-63(PR #59) 머지 후
<!-- SECTION:NOTES:END -->
