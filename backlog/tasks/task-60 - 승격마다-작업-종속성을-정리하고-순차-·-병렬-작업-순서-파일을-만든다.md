---
id: TASK-60
title: 승격마다 작업 종속성을 정리하고 순차 · 병렬 작업 순서 파일을 만든다
status: In Progress
assignee: []
created_date: '2026-10-12 03:07'
updated_date: '2026-10-21 09:24'
labels:
  - hooks
dependencies: []
references:
  - decision-3
  - decision-12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): 태스크가 생기면(draft가 태스크로 승격될 때마다) backlog.md CLI의 의존성 기능으로 작업 종속성을 정리하고, 순차로 할 일과 병렬로 할 일을 나눠 작업 순서 파일을 만들고 커밋한다(push 없음).

backlog.md 1.51.0이 제공하는 기능:
- task edit --dep/--depends-on/--clear-deps: 의존을 적고 지운다.
- task list --ready: 의존이 모두 끝난 태스크만 보여 준다.
- --ordinal / --sort ordinal: 사용자 지정 순서.
- task view: 의존 그래프 트리를 보여 준다.
- backlog doctor: 자기 참조 · 순환 의존을 보고한다.

병렬 묶음을 바로 출력하는 기능은 없다. 그래서 의존 그래프를 위상 정렬해 단계(level)를 직접 계산한다. 같은 단계 = 병렬, 단계 사이 = 순차.

관련: DRAFT-9(단계별 커밋), backlog_commit_scope.py. 승격 커밋에는 이름 변경과 backlog/tasks 파일만 들어갈 수 있으므로, 작업 순서 커밋은 승격 커밋과 별도로 둔다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/work_order.py가 미완료 태스크의 의존을 읽어 단계별 표를 backlog/work-order.md에 쓴다. 각 단계는 병렬 묶음이고, 순환 의존이 있으면 실패한다
- [ ] #2 승격 뒤 backlog/work-order.md가 현재 태스크 집합 · 의존과 맞지 않으면 다음 단계 명령(다음 promote · -s "In Progress")을 deny한다
- [ ] #3 작업 순서 커밋에는 backlog/work-order.md와 의존을 고친 태스크 파일만 들어간다
- [ ] #4 README · CLAUDE.md.snippet의 백로깅 절차에 "승격 → --dep 정리 → 작업 순서 생성 → 커밋"을 반영한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [ ] #2 새 훅 · 스크립트는 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트에 반영
- [ ] #3 각 커밋에 TASK ID, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 draft가 태스크로 승격될 때마다 backlog.md 의존 기능으로 작업 종속성을 정리하고, 순차 · 병렬을 나눈 작업 순서 파일을 만들어 커밋하길 원한다(2026-10-12, push 없음).

### Objective
- backlog.md 1.51.0: task edit --dep로 의존을 적고, task list --ready는 지금 착수 가능한 것만 보여 준다. 병렬 묶음을 바로 내는 기능은 없다.
- 태스크 파일 frontmatter에 dependencies: [...] 키가 항상 있다(빈 목록 포함).
- 승격 커밋은 이름 변경과 backlog/tasks 파일만 담을 수 있다(backlog_commit_scope.py). 단계별 커밋은 TASK-59에서 강제한다.

### Assessment
의존 데이터는 태스크 파일 frontmatter의 dependencies를 직접 읽는다 — CLI 출력 형식에 기대지 않고, 훅에서 subprocess 없이 빠르다(TASK-58과 같은 방식). 미완료(Done이 아닌) 태스크로 그래프를 만들어 위상 정렬 단계(level)를 계산한다. 같은 단계 = 병렬, 단계 사이 = 순차. 최신 여부는 생성 시각 대신 입력 해시(태스크 ID 집합 · 의존)로 판정한다. 완료된 태스크에 대한 의존은 충족된 것으로 본다.

### Plan
1. AC #1: scripts/work_order.py — 순환 의존이면 실패, backlog/work-order.md에 해시 + 단계별 표. 테스트 먼저.
2. AC #2: 새 독립 훅(require_work_order.py) — 다음 promote · -s "In Progress" 전에 해시가 다르면 deny하고 scripts/work_order.py 실행을 안내. 테스트 먼저, 등록 · REGISTRY.
3. AC #3: backlog_commit_scope.py에 작업 순서 커밋 범위 규칙. 테스트 먼저.
4. AC #4: README · CLAUDE.md.snippet 백로깅 절차. 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->
