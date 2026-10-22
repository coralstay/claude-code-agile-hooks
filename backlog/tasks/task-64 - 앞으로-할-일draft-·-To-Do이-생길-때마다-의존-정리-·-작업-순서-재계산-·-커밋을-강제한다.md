---
id: TASK-64
title: 앞으로 할 일(draft · To Do)이 생길 때마다 의존 정리 · 작업 순서 재계산 · 커밋을 강제한다
status: To Do
assignee: []
created_date: '2026-10-22 05:34'
updated_date: '2026-10-22 05:35'
labels:
  - hooks
dependencies: []
references:
  - decision-3
  - decision-12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-22): TASK-60(작업 순서 파일)은 '승격할 때마다'만 규칙으로 적고, 다음 promote · In Progress에서만 늦게 검사하며, 의존을 실제로 검토했는지는 보지 않는다. 또 draft는 계산에서 빠져 있다. 규칙: draft든 To Do 태스크든 앞으로 할 일이 새로 생기거나 다시 열리거나 의존이 바뀔 때마다 의존을 정리하고 작업 순서를 다시 계산해 바로 커밋한다. 선행: TASK-59(단계별 커밋, PR #55) · TASK-60(작업 순서, PR #56) — 머지 뒤 착수하거나 TASK-60 브랜치 위에 쌓는다. 최상위 문서 반영은 coralstay-software-factory DRAFT-1(→ TASK-18)에서 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 생성 직후 강제: draft create · draft promote · 재오픈(Done에서 다른 상태로) 커밋 바로 다음 커밋은 작업 순서 커밋이어야 하고, 그 사이에 다른 커밋이 오면 deny한다
- [ ] #2 검사 시점 확대: 다음 draft promote · -s "In Progress"에 더해 draft create · -s Done · git push에서도 작업 순서가 없거나 낡았으면 deny한다
- [ ] #3 의존 검토 기록: 새로 생긴 draft · 태스크마다 의존이 있으면 --dep로, 없으면 '의존 없음'을 명시해야 하고(형식은 착수 시 결정), 표시가 없는 항목이 있으면 work_order.py가 실패한다
- [ ] #4 문구 반영 + draft 포함: work_order.py와 해시 계산 대상을 미완료 태스크 + draft로 넓히고(draft는 구분 표시, 승격 뒤 DRAFT-N을 가리키는 의존이 남아 있으면 다시 걸라고 안내), README · CLAUDE.md.snippet의 '승격할 때마다'를 '앞으로 할 일(draft · To Do)이 생기거나 다시 열리거나 의존이 바뀔 때마다'로 바꾼다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [ ] #2 바뀐 훅은 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트와 맞는다
- [ ] #3 각 커밋에 TASK ID, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 앞으로 할 일이 들어올 때마다 의존성을 매번 계산해야 한다고 했고, draft도 마찬가지로 계산해야 한다고 했다(2026-10-22). 강화 범위로 규칙 문구 명시 · 검사 시점 확대 · 의존 검토 기록 · 승격 직후 강제를 모두 골랐다.

### Objective
- TASK-60의 해시는 미완료 태스크 ID와 의존으로 만든다. 새 To Do · 재오픈 · 의존 변경은 해시를 바꾸지만, 검사는 다음 promote · In Progress에서만 한다.
- draft도 frontmatter dependencies가 있고 backlog draft edit --dep를 지원한다. 지금 계산에는 빠져 있다.
- 의존을 비워 둔 채 재계산해도 해시가 맞아 통과한다.
- TASK-59는 단계 명령 전 미커밋 backlog/ 변경을 막고 커밋 범위를 검사한다.

### Assessment
TASK-60의 work_order.py · require_work_order.py · backlog_commit_scope.py를 넓힌다. 생성 직후 강제는 '직전 커밋이 생성 · 승격 · 재오픈 커밋이면 이번 커밋은 작업 순서 커밋이어야 한다'로 backlog_commit_scope.py에서 판정한다. 검사 시점은 require_work_order.py의 감지 명령에 draft create · -s Done · git push를 더한다. 의존 검토 표시 형식은 착수 시 유저와 정한다.

### Plan
1. 의존 검토 표시 형식을 유저와 정한다.
2. AC #4(draft 포함 · 문구)부터 — 해시 · 표 대상 확장, 테스트 먼저.
3. AC #1 · #2 · #3 순서로 테스트 먼저 구현.
4. README · CLAUDE.md.snippet, 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 조건(유저, 2026-10-22): TASK-59(PR #55) · TASK-60(PR #56)이 main에 머지된 뒤 착수한다. 이 카드는 main 기준 브랜치에서 승격돼 그 태스크 파일이 아직 없어 --dep를 걸지 못했다 — 착수 시 --dep TASK-59,TASK-60을 건다.
<!-- SECTION:NOTES:END -->
