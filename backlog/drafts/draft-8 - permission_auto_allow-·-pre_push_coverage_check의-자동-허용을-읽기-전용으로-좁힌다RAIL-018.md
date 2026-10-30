---
id: DRAFT-8
title: permission_auto_allow · pre_push_coverage_check의 자동 허용을 읽기 전용으로 좁힌다(RAIL-018)
status: Draft
assignee: []
created_date: '2026-10-30T12:46:00Z'
updated_date: '2026-10-30T12:46:00Z'
labels:
  - hooks
  - bug
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
최상위 2026-10-30 코드 ↔ 문서 대조에서 나왔다. RAIL-018은 권한 요청의 자동 허용을 부작용 없는 읽기 전용 도구 · 명령으로만 한정하는데, 코드는 그보다 넓게 허용한다. 최상위 문서는 바꾸지 않고(유저 결정: 원칙보다 넓은 허용은 코드 버그로 본다) 여기서 코드를 고친다. TASK-65 설명의 ⑦(통과 시 push 자동 허용)과 겹치므로 TASK-65는 이 카드를 참조만 한다.

- permission_auto_allow.py:24-28 — SAFE_COMMANDS에 find가 있어 find . -delete · find -exec 류가, SAFE_GIT_SUBCOMMANDS에 branch · remote가 있어 git branch -D · git remote add/remove가 자동 허용된다. git diff/log/show의 --output=<file>도 파일을 쓴다.
- pre_push_coverage_check.py:427 — 커버리지 검사를 통과하면 PreToolUse에서 permissionDecision allow를 내 git push 권한 확인이 자동 승인된다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 permission_auto_allow는 find에 -delete · -exec · -execdir · -ok · -okdir · -fprint · -fprint0 · -fprintf · -fls가 있으면 자동 허용하지 않는다
- [ ] #2 permission_auto_allow는 git branch · git remote를 목록 조회 형태일 때만 자동 허용하고 삭제 · 생성 · 이름 변경 · remote add/remove/set-url 등은 넘기지 않는다
- [ ] #3 permission_auto_allow는 git diff · log · show에 --output이 있으면 자동 허용하지 않는다
- [ ] #4 pre_push_coverage_check는 검사를 통과해도 permissionDecision allow를 내지 않는다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 테스트 통과 로그를 final summary에 남긴다 (수동)
- [ ] #2 커버리지 100% (수동)
- [ ] #3 README · CLAUDE.md.snippet의 자동 허용 설명을 코드에 맞춘다 (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
최상위 코드 ↔ 문서 대조(2026-10-30)에서 유저가 '코드가 원칙보다 넓게 허용하는 것은 문서를 바꾸지 않고 hooks 버그로 넘긴다'고 정했다.

### Objective
- permission_auto_allow.py:24-28 SAFE_COMMANDS에 find, SAFE_GIT_SUBCOMMANDS에 branch · remote. 첫 단어 · 하위 명령만 보고 인자는 보지 않는다.
- pre_push_coverage_check.py:427 통과 시 permissionDecision allow.
- 최상위 2.03 RAIL-018: 자동 허용은 부작용 없는 읽기 전용 도구 · 명령으로만, 허용하지 않는 요청은 일반 권한 흐름으로.

### Assessment
허용 목록을 하위 명령 단위에서 인자 단위로 좁힌다. find는 실행 · 삭제 · 파일 쓰기 액션이 있으면, git branch · remote는 목록 조회가 아니면, git diff · log · show는 --output이 있으면 넘긴다. 커버리지 훅은 통과 시 판정을 내지 않아 일반 권한 흐름을 탄다(게이트 역할만).

### Plan
1. AC마다 테스트 먼저(표식 <ID>#n) → 구현 → 커밋.
2. README · CLAUDE.md.snippet의 자동 허용 설명을 맞춘다.
<!-- SECTION:PLAN:END -->
