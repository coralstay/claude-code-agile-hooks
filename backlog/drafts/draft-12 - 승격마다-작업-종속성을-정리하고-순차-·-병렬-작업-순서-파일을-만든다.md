---
id: DRAFT-12
title: 승격마다 작업 종속성을 정리하고 순차 · 병렬 작업 순서 파일을 만든다
status: Draft
assignee: []
created_date: '2026-10-12 03:07'
updated_date: '2026-10-12 03:07'
labels:
  - hooks
dependencies: []
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 의존 데이터 소스(태스크 파일 frontmatter dependencies 또는 backlog task list --plain 출력)는 착수 시 정한다.
2. scripts/work_order.py: 미완료 태스크의 의존 그래프를 위상 정렬해 단계(level)별 표를 backlog/work-order.md에 쓴다. 파일 상단에 생성 시각 대신 입력 해시(태스크 집합 · 의존)를 적어 최신 여부를 판정한다.
3. 새 훅(PreToolUse Bash, 완전 독립형 decision-3): 다음 promote · -s "In Progress"를 command position으로 감지한다(require_draft_first.py 방식). 입력 해시가 맞지 않으면 deny하고 scripts/work_order.py 실행을 안내한다.
4. backlog_commit_scope.py에 작업 순서 커밋 범위(backlog/work-order.md + 의존을 고친 태스크 파일) 규칙을 추가한다.
5. AC 순서대로 테스트를 먼저 작성하고 구현한 뒤 README · CLAUDE.md.snippet에 반영한다.
<!-- SECTION:PLAN:END -->
