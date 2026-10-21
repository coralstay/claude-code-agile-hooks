---
id: TASK-57
title: design/00-문서-정보.md에 최상위 00 문서 계층 참조 한 줄을 둔다
status: To Do
assignee: []
created_date: '2026-10-21 04:37'
updated_date: '2026-10-21 04:37'
labels:
  - design
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
최상위 coralstay-software-factory TASK-16이 design/00-문서-정보.md에 '문서 계층' 절(장 대응표 포함)과 최상위 → 컴포넌트 전파 편집 규칙을 넣었다(RAIL-024, ADR-025). 이 저장소의 design/00-문서-정보.md 편집 규칙에 그 절을 가리키는 한 줄을 두어, 최상위 변경이 이 저장소의 장에 닿으면 같은 작업으로 여기에도 커밋해야 함을 알린다. 상위 태스크: coralstay-software-factory TASK-16. 수정은 이미 worktree에 작성돼 있다(커밋 전).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 design/00-문서-정보.md 편집 규칙에 최상위 00 '문서 계층' 절을 가리키는 한 줄과 링크 정의가 있다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 커밋 본문에 coralstay-software-factory TASK-16을 참조로 적는다
- [ ] #2 push는 하지 않는다
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 최상위 설계 문서를 고치면 컴포넌트 설계 문서도 반드시 고치도록 하고, 그 규칙을 최상위에 넣으라고 했다(2026-10-12). 최상위 TASK-16이 그 규칙을 넣었고, 컴포넌트 3곳에 참조 한 줄을 두는 것이 TASK-16 AC #5다.

### Objective
- 최상위 design/00-문서-정보.md에 '## 문서 계층' 절과 '### 장 대응표', 편집 규칙 전파 항목이 있다(최상위 커밋 2227265).
- 이 저장소의 design/00-문서-정보.md 편집 규칙에는 최상위 → 컴포넌트 전파 언급이 없다.
- 컴포넌트 문서는 최상위를 상대 경로가 아니라 GitHub URL로 가리킨다.

### Assessment
편집 규칙 끝에 한 줄과 링크 정의([hierarchy]: 최상위 main의 00-문서-정보.md#문서-계층)를 둔다. 앵커는 최상위 TASK-16이 main에 머지된 뒤 살아난다.

### Plan
1. 승격된 카드 번호로 브랜치를 바꾼다.
2. 승격 커밋, 이어 design/00-문서-정보.md 한 줄 커밋(본문에 coralstay-software-factory TASK-16 참조).
3. 링크 정의가 최상위 절 제목과 맞는지 확인한다.
<!-- SECTION:PLAN:END -->
