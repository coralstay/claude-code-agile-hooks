---
id: TASK-59
title: 카드 생애주기 단계마다 커밋을 훅으로 강제한다
status: Done
assignee: []
created_date: '2026-10-12 02:26'
updated_date: '2026-10-21 09:22'
labels:
  - hooks
dependencies: []
references:
  - decision-3
  - decision-4
  - decision-11
documentation:
  - >-
    https://github.com/coralstay/coralstay-software-factory/blob/main/design/2-요구사항-명세서/02-도메인-모델.md
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
- [x] #1 커밋 하나에 새 draft 파일이 두 개 이상 들어가면 backlog_commit_scope.py가 커밋을 deny한다
- [x] #2 상태 전환 커밋(→ In Progress, → Done)에는 그 태스크 파일만 들어가야 하고, 다른 변경이 섞이면 deny한다
- [x] #3 다음 단계 명령(draft create · draft promote · -s "In Progress" · -s Done) 실행 전에 커밋되지 않은 backlog/ 변경이 있으면 deny한다
- [x] #4 테스트를 쓰고 README · CLAUDE.md.snippet의 실행 절차에 단계별 커밋을 반영한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [x] #2 새 훅은 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트에 반영
- [x] #3 각 커밋에 TASK ID, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 backlog.md 작업 흐름을 단계마다 커밋하도록 강제하길 원한다: draft 1장 작성 → 커밋 → 승격 → 커밋(+ 작업 순서 파일, DRAFT-12) → In Progress → 커밋 → 작업 → Done → 커밋. push는 범위 밖(2026-10-12).

### Objective
- backlog_commit_scope.py는 draft 생성 커밋과 승격 커밋의 분리만 강제하고, 커밋 하나에 draft 여러 장을 허용한다(예: 5d11356).
- 상태 전환 커밋의 범위와, 단계 명령 전에 남은 미커밋 backlog/ 변경은 아무 훅도 보지 않는다.
- 최상위 설계 문서 2.02 '전이와 커밋' · RAIL-021이 이 규칙을 명세로 먼저 적었다.

### Assessment
커밋 범위 규칙(새 draft 1장, 상태 전환 커밋은 그 태스크 파일만)은 기존 backlog_commit_scope.py에 더한다. 단계 명령 전 미커밋 검사는 성격이 달라 새 독립 훅(require_stage_committed.py, decision-3)으로 둔다. git status --porcelain backlog/만 보아 다른 작업 파일은 막지 않는다.

### Plan
1. AC #1: backlog_commit_scope.py에 새 draft 2개 이상 deny — 테스트 먼저.
2. AC #2: 상태 전환 커밋(→ In Progress, → Done) 범위 검사 — 테스트 먼저.
3. AC #3: require_stage_committed.py — 단계 명령 command position 감지, 미커밋 backlog/ 변경 시 deny — 테스트 먼저, REGISTRY · settings.hooks.json 등록.
4. AC #4: README · CLAUDE.md.snippet 실행 절차 반영. 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
카드 생애주기를 단계마다 커밋하도록 강제했다.

- AC #1 backlog_commit_scope.py: 커밋 하나에 새 draft 파일 2개 이상이면 deny(7572811)
- AC #2 같은 훅: 상태 전환 커밋(→ In Progress · → Done)은 그 태스크 파일만 담는다. 전환은 스테이징 blob의 frontmatter status와 HEAD의 status 비교로 판정(이름 변경 추적, 새 파일은 전환으로 봄). 다른 경로나 두 번째 상태 전환 파일이 섞이면 deny(4197d73)
- AC #3 새 독립 훅 require_stage_committed.py: draft create · draft promote · task edit -s "In Progress"/Done이 명령 위치에 있고 git status --porcelain -- backlog/에 미커밋 변경(스테이징 · 미스테이징 · 미추적)이 있으면 deny. settings.hooks.json · REGISTRY · 등록 계약 반영(a66c49f)
- AC #4 README(단계별 커밋 절, 훅 표) · CLAUDE.md.snippet 실행 절차 반영(ed6508f)

검증: coverageCommand → 1926 passed, 4091 stmts · 1676 branches 100%.
알려진 영향: --add-ref · --doc 등을 따로 실행해 남긴 미커밋 변경 뒤의 -s는 막힌다(한 명령으로 합치거나 먼저 커밋). 완료 시 backlog doc(decision-8)은 Done 전환과 별도 커밋이 필요하다. TASK-58과 README 훅 수 · settings · REGISTRY에서 병합 충돌 예상. 컴포넌트 design/(01-시스템-구성, 01-three-natures.dot)에 새 훅 반영은 범위 밖.
<!-- SECTION:FINAL_SUMMARY:END -->
