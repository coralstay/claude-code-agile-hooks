---
id: DRAFT-9
title: 카드 생애주기 단계마다 커밋을 훅으로 강제한다
status: Draft
assignee: []
created_date: '2026-10-12 02:26'
updated_date: '2026-10-12 03:06'
labels:
  - hooks
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): backlog.md CLI 작업 흐름을 draft 1장 작성 → 커밋 → To Do 승격 → 커밋(+ 작업 순서 파일 커밋, DRAFT-12 참조) → In Progress → 커밋 → 실제 작업 → Done → 커밋으로 강제한다.

현재 상태와 충돌하는 지점(이 draft에서 정리할 것):
- backlog_commit_scope.py는 draft 생성 커밋과 승격 커밋의 분리만 강제한다. 커밋 하나에 draft 여러 장은 허용한다(예: 5d11356).
- push는 범위 밖이다(유저 결정 2026-10-12). pre_push_check.py · pre_git_safety_check.py와의 충돌은 더 이상 이 draft의 문제가 아니다.
- decision-4(원격 병합은 사람이 최종 승인)는 유지한다.

관련: backlog_commit_scope.py, decision-4 · decision-11, DRAFT-12(승격마다 작업 순서 파일). 설계 문서 반영은 coralstay-software-factory 후속 draft(RAIL-021 예정)에서 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 커밋 하나에 새 draft 파일이 두 개 이상 들어가면 backlog_commit_scope.py가 커밋을 deny한다
- [ ] #2 상태 전환 커밋(→ In Progress, → Done)에는 그 태스크 파일만 들어가야 하고, 다른 변경이 섞이면 deny한다
- [ ] #3 다음 단계 명령(draft create · draft promote · -s "In Progress" · -s Done) 실행 전에 커밋되지 않은 backlog/ 변경이 있으면 deny한다
- [ ] #4 테스트를 쓰고 README · CLAUDE.md.snippet의 실행 절차에 단계별 커밋을 반영한다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. backlog_commit_scope.py에 '새 draft 1장' 규칙과 상태 전환 커밋 범위 규칙을 추가한다.
2. 새 훅(가칭 require_stage_committed.py, PreToolUse Bash, 완전 독립형 decision-3): 단계 명령을 command position으로 감지하고 git status --porcelain backlog/로 커밋되지 않은 변경만 검사한다.
3. AC 순서대로 테스트를 먼저 작성하고 구현한다.
<!-- SECTION:PLAN:END -->
