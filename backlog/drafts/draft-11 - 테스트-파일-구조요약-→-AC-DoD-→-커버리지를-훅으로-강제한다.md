---
id: DRAFT-11
title: 테스트 파일 구조(요약 → AC/DoD → 커버리지)를 훅으로 강제한다
status: Draft
assignee: []
created_date: '2026-10-12 02:28'
updated_date: '2026-10-12 02:29'
labels:
  - hooks
dependencies: []
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
- [ ] #1 5개 언어의 테스트 파일은 첫 주석 블록에 태스크 ID와 요약이 없으면 Edit · Write 결과를 deny한다
- [ ] #2 AC/DoD 섹션 표식이 Coverage 섹션 표식보다 앞에 있어야 하고, 순서가 어긋나거나 섹션이 빠지면 deny한다
- [ ] #3 AC · 규칙 · DoD 표식(<ID>#<n> · <ID>#B<k> · <ID>#D<n>)은 AC/DoD 섹션 안에만 있어야 한다
- [ ] #4 DoD 표식 <ID>#D<n>을 require_test_first.py의 Done 게이트에 추가한다
- [ ] #5 언어별 예시 파일(헤더 · 섹션 표식)과 규약을 README · CLAUDE.md.snippet에 적는다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 규약을 정한다: 섹션 표식 주석 문자열(예: '== AC/DoD ==', '== Coverage =='), 언어별 주석 문법(#, //, /* */), 헤더 형식('<ID>: <요약>').
2. 새 훅(가칭 require_test_layout.py, PreToolUse Edit|Write)에서 결과 내용(Write는 content, Edit는 적용 후 내용을 시뮬레이션)을 검사한다.
3. 대상 경로는 testFirst.testGlobs를 우선 쓰고, 없으면 언어별 기본 패턴(test_*.py · *.test|spec.[jt]sx? · *Test.java · *_test.cpp 등)을 쓴다.
4. require_test_first.py에 DoD 표식 수집과 Done 게이트를 추가한다.
5. 언어마다 통과 · 위반 픽스처로 테스트한다.
<!-- SECTION:PLAN:END -->
