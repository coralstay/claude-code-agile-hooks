---
id: DRAFT-8
title: 구현 계획 없는 승격 · 착수를 훅으로 막는다
status: Draft
assignee: []
created_date: '2026-10-12 02:24'
updated_date: '2026-10-12 02:26'
labels:
  - hooks
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): Claude가 backlog.md CLI로 일할 때 구현 계획(Implementation Plan) 없이 태스크를 만든다. 이를 훅으로 강제한다.

지금 require_draft_first.py는 task create만 막고(draft 경유 강제), 계획이 있는지는 아무도 보지 않는다. backlog draft create에는 --plan 옵션이 없으므로 draft edit --plan으로 계획을 적은 뒤에야 승격할 수 있게 한다.

관련: require_draft_first.py(명령 파싱 규칙), decision-1(커맨드 문자열 매칭의 한계), decision-12(테스트 먼저). 설계 문서 반영은 coralstay-software-factory 쪽 후속 draft에서 한다(BL-015 · RAIL-020 예정).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog draft promote <ID>는 draft에 비어 있지 않은 Implementation Plan 절이 없으면 deny하고 backlog draft edit <ID> --plan을 안내한다
- [ ] #2 backlog task edit <ID> -s "In Progress"는 그 태스크에 구현 계획이 없으면 deny한다(MCP · 웹 UI로 만든 카드에 대한 2차 방어선)
- [ ] #3 명령 위치(command position) 파싱은 require_draft_first.py와 같은 규칙을 쓰고, 인용문 · heredoc 안의 문자열은 통과시킨다
- [ ] #4 settings.hooks.json 등록 + 테스트, README · CLAUDE.md.snippet에 규칙을 반영한다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 새 훅 hooks/require_implementation_plan.py(완전 독립형, decision-3)를 PreToolUse(Bash)에 등록한다.
2. require_draft_first.py의 command_head · 세그먼트 분할 로직을 복사하고 dedup_drift_guard REGISTRY에 등록한다.
3. draft promote: backlog/drafts/에서 ID로 파일을 찾아 Implementation Plan 섹션(SECTION:PLAN 마커 사이)이 비어 있는지 검사한다.
4. In Progress: backlog task view <ID> --plain의 Implementation Plan 절을 검사한다.
5. 테스트를 먼저(AC 표식) 작성하고, 모든 테스트를 통과시킨 뒤 문서에 반영한다.
<!-- SECTION:PLAN:END -->
