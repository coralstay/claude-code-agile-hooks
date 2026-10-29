---
id: TASK-65
title: >-
  최상위 TASK-15 · 17 · 18의 설계 변경을 이 저장소 design/에 반영한다(새 훅 6개 · 계획 승인 · 작업 순서 · 테스트
  파일 구조 · 커버리지)
status: To Do
assignee: []
created_date: 2026-10-22 05:52
updated_date: '2026-10-29T12:26:00Z'
labels:
  - design
dependencies: []
references:
  - decision-15
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
최상위 coralstay-software-factory TASK-15(구현 계획 · 단계별 커밋 · 작업 순서 · 커버리지 · 테스트 파일 구조 · PRG) · TASK-17(서명 키 전제 삭제) · TASK-18(go → 계획 승인, 사람 서명자 확인, 미정 항목 확정)의 전파(RAIL-024). 훅 코드는 TASK-58 ~ TASK-63에서 만들었지만 이 저장소 design/(3.01 시스템 구성, diagrams/01-three-natures.dot, 인터페이스 · 설정 등)에는 새 훅과 규칙이 없다. 커밋 본문에 'Refs: coralstay-software-factory TASK-15 · TASK-17 · TASK-18'을 적는다. 선행: TASK-58 ~ 63 PR(#54 ~ #59) 머지 — 문서가 실제 main의 훅과 맞아야 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 design/의 훅 목록 · 시스템 구성 · three-natures 다이어그램에 require_implementation_plan · require_stage_committed · require_work_order · require_test_layout · require_coverage_on_done · require_design_propagation과 바뀐 backlog_commit_scope · require_test_first · pre_push_coverage_check를 반영한다(다이어그램은 build-diagrams.py로 재렌더)
- [ ] #2 design/의 동작 · 인터페이스 · 설정 장에 계획 → 리뷰 → 계획 승인(Plan-Approved, humanSigners), 단계별 커밋, 작업 순서 파일, 테스트 파일 구조, 커버리지 100%(line + branch) · coverageReportDir, 설계 문서 전파(Propagation-None)를 최상위 2.02 · 2.03 · 3.04 · 3.05와 같은 ID로 반영한다
- [ ] #3 각 커밋 본문에 'Refs: coralstay-software-factory TASK-15 · TASK-17 · TASK-18'을 적는다
- [ ] #4 최상위 TASK-19의 결정을 design/의 해당 장에 반영한다: A1(착수 검사 — 계획 승인 · 형식 · 작업 순서 — 를 task/<ID> 브랜치 생성 · 전환 때와 -s "In Progress" 때 두 번, 훅 설치 시에만), A2(착수 = main에 미병합 task/<ID> 브랜치, Edit/Write 게이트는 현재 브랜치 카드의 In Progress 확인), A5(작업 순서 검사도 브랜치 시점), A6(텍스트가 (수동)으로 끝나는 AC · DoD는 테스트 표식 예외, 비즈니스 규칙은 예외 없음), C2(RAIL-025 task 브랜치 커밋 메시지의 태스크 ID), squash 대응(병합 뒤 task/<ID> 브랜치 삭제 규칙과 '삭제 안 된 squash 브랜치는 착수 중으로 보인다'는 한계) — 이 커밋들의 본문에는 'Refs: coralstay-software-factory TASK-19'를 적는다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 design/ 상대 링크 검사에서 깨진 링크가 없다
- [ ] #2 파일 하나에 커밋 하나, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 최상위 설계 변경(TASK-15 · 17 · 18)의 컴포넌트 전파를 별도 카드로 하자고 했다(2026-10-22).

### Objective
- 전파 훅(TASK-63)을 읽기 전용으로 돌린 결과와 키워드 검사: 이 저장소 design/에는 새 훅 6개 이름이 0건, 계획 승인 · 서명 0건이다.
- 훅 코드와 README는 TASK-58 ~ 63 브랜치에 있고 아직 main에 머지 전이다.

### Assessment
문서는 main의 실제 훅과 맞아야 하므로 #54 ~ #59 머지 뒤 착수한다. 최상위 장 대응표(3.01 · 3.02 · 3.03 §2 · 3.04 · 3.05 → 이 저장소 같은 장)를 따라 장마다 고친다.

### Plan
1. #54 ~ #59 머지 확인, 최상위 TASK-15 · 17 · 18 diff를 장 대응표로 정리.
2. 장마다 반영, 파일 하나에 커밋 하나(Refs 줄).
3. 다이어그램 재렌더, 링크 검사.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 조건(유저, 2026-10-22): TASK-58 ~ 63(PR #54 ~ #59) 머지 후. Refs: coralstay-software-factory TASK-15 · TASK-17 · TASK-18

결정 반영(유저, 2026-10-29): 최상위 TASK-19(충돌 A1 ~ A6 · C2 결정)의 전파를 AC #4로 더했다. 기존 AC #1 ~ #3은 그대로다. TASK-19 몫의 커밋에는 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다(TASK-15 · 17 · 18 몫은 AC #3대로). 구현 카드 DRAFT-8 ~ 11(승격 뒤 ID)이 끝난 뒤 실제 동작과 맞춰 반영한다.
<!-- SECTION:NOTES:END -->
