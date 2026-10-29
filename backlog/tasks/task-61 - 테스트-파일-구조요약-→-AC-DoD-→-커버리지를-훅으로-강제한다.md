---
id: TASK-61
title: 테스트 파일 구조(요약 → AC/DoD → 커버리지)를 훅으로 강제한다
status: Done
assignee: []
created_date: '2026-10-12 02:28'
updated_date: '2026-10-21 10:06'
labels:
  - hooks
dependencies: []
references:
  - decision-3
  - decision-12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): JS · TS · Java · Python · C++ 테스트 파일은 태스크 카드의 AC/DoD를 바탕으로 테스트를 쓰고, 파일 안 순서를 고정한다.
1. 맨 위: 테스트 파일 요약 — 작업한 태스크 ID와 짧은 요약
2. 그 아래: AC/DoD 기반 테스트(표식 <ID>#<n> · <ID>#B<k> · 새 DoD 표식 <ID>#D<n>)
3. 맨 아래: 커버리지 100%를 채우기 위한 테스트

현재 상태: require_test_first.py(TASK-56, decision-12)는 AC · 비즈니스 규칙 표식이 testGlobs 어딘가에 있는지만 본다. 파일 안 위치나 순서, DoD 표식은 보지 않는다.

관련: require_test_first.py, protect_tests.py(테스트 파일 패턴), 커버리지 100% draft. 설계 문서 반영은 coralstay-software-factory 후속 draft(2.02 테스트 표식 · RAIL-022 예정)에서 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 5개 언어의 테스트 파일은 첫 주석 블록에 태스크 ID와 요약이 없으면 Edit · Write 결과를 deny한다
- [x] #2 AC/DoD 섹션 표식이 Coverage 섹션 표식보다 앞에 있어야 하고, 순서가 어긋나거나 섹션이 빠지면 deny한다
- [x] #3 AC · 규칙 · DoD 표식(<ID>#<n> · <ID>#B<k> · <ID>#D<n>)은 AC/DoD 섹션 안에만 있어야 한다
- [x] #4 DoD 표식 <ID>#D<n>을 require_test_first.py의 Done 게이트에 추가한다
- [x] #5 언어별 예시 파일(헤더 · 섹션 표식)과 규약을 README · CLAUDE.md.snippet에 적는다
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
유저는 JS · TS · Java · Python · C++ 테스트 파일을 카드의 AC/DoD로 쓰고 파일 안 순서를 고정하길 원한다: 맨 위 요약(태스크 ID + 요약) → AC/DoD 테스트 → 커버리지용 테스트(2026-10-12). 규약 문자열과 기존 파일 처리 방식은 2026-10-21에 정했다.

### Objective
- require_test_first.py(decision-12)는 AC · 규칙 표식이 testGlobs 어딘가에 있는지만 본다. 파일 안 위치 · 순서와 DoD 표식은 보지 않는다.
- 이 저장소 테스트 파일을 포함해 기존 테스트 파일에는 요약 헤더 · 섹션 표식이 없다.

### Assessment
규약(유저 결정 2026-10-21): 첫 주석 블록에 '<ID>: <한 줄 요약>' 줄(태스크마다 한 줄), 그 아래 '== AC/DoD ==' 섹션, 그 아래 '== Coverage ==' 섹션. 주석 기호는 언어별(# · // · /* */). 적용 범위: 새로 만드는 테스트 파일과 이미 헤더(또는 섹션 표식)가 있는 파일만 검사하고, 헤더가 없는 기존 파일은 통과시키되 규약 안내를 보여 준다. 새 독립 훅 require_test_layout.py(PreToolUse Edit|Write)가 결과 내용(Write는 content, Edit는 적용 후 내용 시뮬레이션)을 검사한다. DoD 표식 <ID>#D<n>은 require_test_first.py의 Done 게이트에 더한다.

### Plan
1. AC #1: 헤더 검사(5개 언어 주석 문법, 대상 경로는 testFirst.testGlobs 우선, 없으면 언어별 기본 패턴) — 테스트 먼저.
2. AC #2: 섹션 순서 · 누락 검사 — 테스트 먼저.
3. AC #3: 표식이 AC/DoD 섹션 안에만 — 테스트 먼저.
4. AC #4: require_test_first.py Done 게이트에 DoD 표식 — 테스트 먼저.
5. AC #5: 언어별 예시와 규약을 README · CLAUDE.md.snippet에. 등록 · REGISTRY, 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 시 결정(유저, 2026-10-21): 섹션 표식 '== AC/DoD ==' · '== Coverage ==', 헤더 '<ID>: <요약>'(태스크마다 한 줄). 새 파일과 이미 규약을 따르는 파일만 검사, 헤더 없는 기존 파일은 통과 + 안내.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
JS · TS · Java · Python · C++ 테스트 파일의 구조(헤더 → AC/DoD → Coverage)를 강제하는 새 독립 훅 require_test_layout.py(PreToolUse Edit|Write)를 추가하고, DoD 표식을 Done 게이트에 더했다.

- AC #1 첫 주석 블록에 '<ID>: <요약>' 줄 필수(#, //, /* */ 지원, Edit는 적용 후 내용 시뮬레이션)(1c8e132)
- AC #2 '== AC/DoD ==' · '== Coverage ==' 섹션 표식이 한 번씩, 이 순서로(32a0278)
- AC #3 <ID>#<n> · #B<k> · #D<n> 표식은 AC/DoD 섹션 안에만(ef86630)
- AC #4 require_test_first.py Done 게이트가 DoD 항목마다 <ID>#D<n>을 요구(testFirst 설정 프로젝트)(a394ed9)
- AC #5 README(언어별 예시 4개, 예시가 훅 검사를 통과하는지 테스트) · CLAUDE.md.snippet(dabe841)
- 적용 범위(유저 결정): 새 테스트 파일과 이미 헤더 · 섹션 표식이 있는 파일만 검사, 없는 기존 파일은 통과 + 안내(systemMessage · additionalContext). 대상은 testFirst.testGlobs, 없으면 언어별 기본 패턴
- 새 테스트 파일 hooks/test_require_test_layout.py는 규약을 스스로 따른다

검증: coverageCommand → 1920 passed, 4128 stmts · 1696 branches 100%.
과정 메모: AC #1은 훅 첫 버전을 테스트보다 먼저 써서 Red 단계가 없었다(AC #2 ~ #4는 Red → Green). 이 저장소엔 testFirst가 없어 DoD 표식 게이트는 적용되지 않으며, 검증 불가능한 DoD #1 · #3에는 표식을 달지 않았다.
범위 밖: README 훅 수가 원래 1 많았다(재집계 필요, TASK-58 · 59 · 60과 충돌 정리 때 함께). protect_tests.py 패턴이 Java · C++를 못 잡음. Bash로 쓴 테스트 파일은 보지 못함.
<!-- SECTION:FINAL_SUMMARY:END -->
