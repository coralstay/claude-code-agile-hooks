---
id: DRAFT-8
title: 구현 계획(SOAP + AC + DoD)과 Plan-Review-Go 없이 승격 · 착수를 훅으로 막는다
status: Draft
assignee: []
created_date: '2026-10-12 02:24'
updated_date: '2026-10-12 04:46'
labels:
  - hooks
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): Claude가 backlog.md CLI로 일할 때 구현 계획(Implementation Plan) 없이 태스크를 만든다. 이를 훅으로 강제한다.

지금 require_draft_first.py는 task create만 막고(draft 경유 강제), 계획이 있는지는 아무도 보지 않는다. backlog draft create에는 --plan 옵션이 없으므로 draft edit --plan으로 계획을 적은 뒤에야 승격할 수 있게 한다.

유저 결정(2026-10-12):
- 구현 계획은 SOAP + AC + DoD 형식을 쓴다. 계획에는 S(Subjective: 요청 · 배경), O(Objective: 확인한 사실 · 코드 · 측정), A(Assessment: 판단 · 선택한 접근), P(Plan: 구현 순서) 절이 있어야 하고, 카드에는 AC와 DoD가 있어야 한다.
- Plan-Review-Go: 태스크가 In Progress로 가기 전에 구현 계획이 작성되고, 사람이 리뷰하고, 승인(go)해야 한다. 그 뒤에만 In Progress로 옮길 수 있다.

미결(착수 시 결정): 훅은 사람과 Claude를 구분하지 못한다. 그래서 go를 어떻게 기록할지(예: 사람만 붙이는 라벨이나 필드, 사람이 만든 리뷰 파일이나 커밋)는 착수할 때 정한다. SOAP 절의 헤딩 이름(예: ### S, ### O, ### A, ### P)도 착수할 때 확정한다.

관련: require_draft_first.py(명령 파싱 규칙), decision-1(커맨드 문자열 매칭의 한계), decision-12(테스트 먼저). 설계 문서 반영은 coralstay-software-factory 쪽 후속 draft에서 한다(BL-015 · BL-017 · RAIL-020 예정).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog draft promote <ID>는 draft에 비어 있지 않은 Implementation Plan 절이 없으면 deny하고 backlog draft edit <ID> --plan을 안내한다
- [ ] #2 backlog task edit <ID> -s "In Progress"는 그 태스크에 구현 계획이 없으면 deny한다(MCP · 웹 UI로 만든 카드에 대한 2차 방어선)
- [ ] #3 draft promote와 -s "In Progress"는 구현 계획에 S · O · A · P 절 중 하나라도 없거나 비어 있으면, 또는 카드에 AC나 DoD가 없으면 deny하고 빠진 항목을 안내한다
- [ ] #4 backlog task edit <ID> -s "In Progress"는 그 태스크의 구현 계획에 Plan-Review-Go 승인(go)이 기록돼 있지 않으면 deny한다(기록 방식은 미결 항목에서 정한다)
- [ ] #5 명령 위치(command position) 파싱은 require_draft_first.py와 같은 규칙을 쓰고, 인용문 · heredoc 안의 문자열은 통과시킨다
- [ ] #6 settings.hooks.json 등록 + 테스트, README · CLAUDE.md.snippet에 규칙(SOAP + AC + DoD 형식, Plan-Review-Go)을 반영한다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
0. 착수 시 미결 항목을 정한다: SOAP 절 헤딩 이름(예: ### S, ### O, ### A, ### P)과 go 기록 방식(사람만 붙이는 라벨 · 필드, 또는 사람의 리뷰 파일 · 커밋).
1. 새 훅 hooks/require_implementation_plan.py(완전 독립형, decision-3)를 PreToolUse(Bash)에 등록한다.
2. require_draft_first.py의 command_head · 세그먼트 분할 로직을 복사하고 dedup_drift_guard REGISTRY에 등록한다.
3. draft promote: backlog/drafts/에서 ID로 파일을 찾아 Implementation Plan 섹션(SECTION:PLAN 마커 사이)이 비어 있는지, S · O · A · P 절이 모두 있고 비어 있지 않은지 검사한다.
4. 같은 파일에서 Acceptance Criteria(AC 마커 사이)와 Definition of Done 항목이 하나 이상 있는지 검사한다.
5. In Progress: backlog task view <ID> --plain의 Implementation Plan 절과 AC · DoD를 3 · 4와 같은 규칙으로 검사한다.
6. In Progress: 0에서 정한 방식으로 Plan-Review-Go 승인(go) 기록이 있는지 검사하고, 없으면 사람의 리뷰 · go를 받으라고 안내한다.
7. 테스트를 먼저(AC 표식) 작성하고, 모든 테스트를 통과시킨 뒤 settings.hooks.json · README · CLAUDE.md.snippet에 반영한다.
<!-- SECTION:PLAN:END -->
