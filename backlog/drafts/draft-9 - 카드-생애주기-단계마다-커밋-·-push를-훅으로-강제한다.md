---
id: DRAFT-9
title: 카드 생애주기 단계마다 커밋 · push를 훅으로 강제한다
status: Draft
assignee: []
created_date: '2026-10-12 02:26'
updated_date: '2026-10-12 02:27'
labels:
  - hooks
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): backlog.md CLI 작업 흐름을 draft 1장 작성 → 커밋 · push → To Do 승격 → 커밋 · push → In Progress → 커밋 · push → 실제 작업 → Done → 커밋 · push로 강제한다.

현재 상태와 충돌하는 지점(이 draft에서 정리할 것):
- backlog_commit_scope.py는 draft 생성 커밋과 승격 커밋의 분리만 강제한다. 커밋 하나에 draft 여러 장은 허용한다(예: 5d11356).
- pre_push_check.py는 task/<ID> 브랜치를 Done + final summary 전에 push하지 못하게 막는다 → In Progress 커밋을 push할 수 없다.
- pre_git_safety_check.py는 main 직접 push를 막는다(2026-10-12 draft-8 등록 때 실제로 차단됨) → draft · 승격 커밋을 어디로 push할지 정해야 한다.
- decision-4(원격 병합은 사람이 최종 승인)는 유지한다.

관련: backlog_commit_scope.py, pre_push_check.py, pre_git_safety_check.py, decision-4 · decision-11. 설계 문서 반영은 coralstay-software-factory 후속 draft(RAIL-021 예정)에서 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 커밋 하나에 새 draft 파일이 두 개 이상 들어가면 backlog_commit_scope.py가 커밋을 deny한다
- [ ] #2 상태 전환 커밋(→ In Progress, → Done)에는 그 태스크 파일만 들어가야 하고, 다른 변경이 섞이면 deny한다
- [ ] #3 다음 단계 명령(draft create · draft promote · -s "In Progress" · -s Done)을 실행하기 전에 커밋되지 않은 backlog/ 변경이 있거나 upstream보다 ahead면 deny한다
- [ ] #4 pre_push_check.py · pre_git_safety_check.py와 충돌하지 않도록 단계 커밋의 push 경로(브랜치)와 예외 범위를 정해 decision으로 남긴다
- [ ] #5 테스트를 쓰고 README · CLAUDE.md.snippet의 실행 절차에 단계별 커밋 · push를 반영한다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 먼저 push 경로를 결정한다(유저 확인): 예) draft · 승격 커밋은 backlog/<draft-ID> 브랜치로 push, In Progress · Done은 task/<ID>로 push. decision-N으로 기록한다.
2. backlog_commit_scope.py에 '새 draft 1장' 규칙과 상태 전환 커밋 범위 규칙을 추가한다.
3. 새 훅(가칭 require_stage_pushed.py, PreToolUse Bash): 단계 명령을 command position으로 감지하고 git status --porcelain backlog/ · git rev-list @{u}..HEAD로 미커밋 · 미푸시를 검사한다. upstream이 없으면 미푸시로 본다.
4. pre_push_check.py: 해당 태스크 파일만 바뀐 상태 전환 커밋의 push는 Done 전에도 허용한다.
5. AC 순서대로 테스트를 먼저 작성하고 구현한다.
<!-- SECTION:PLAN:END -->
