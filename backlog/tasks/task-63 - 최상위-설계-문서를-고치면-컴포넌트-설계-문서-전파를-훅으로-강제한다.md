---
id: TASK-63
title: 최상위 설계 문서를 고치면 컴포넌트 설계 문서 전파를 훅으로 강제한다
status: To Do
assignee: []
created_date: '2026-10-12 06:16'
updated_date: '2026-10-22 04:57'
labels:
  - hooks
dependencies: []
references:
  - decision-15
  - decision-1
  - decision-3
  - decision-12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): 최상위 설계 문서(coralstay-software-factory의 design/)를 고치면 하위 컴포넌트 설계 문서도 반드시 고치게 강제한다.

지금은 컴포넌트 design/의 00 문서 정보에 상속 규칙("어겨야 하면 최상위 결정을 먼저 고친다")만 있고, 최상위를 고치면 하위도 맞춘다는 전파 의무는 없다. 10-11 사전 점검에서 최상위 ↔ 컴포넌트 불일치 29건이 나왔다. 컴포넌트는 최상위 .gitignore가 제외하는 독립 저장소이고 서브모듈이 아니다(2026-10-12 확인).

핵심 규칙: coralstay-software-factory에서 design/을 바꾸는 커밋(또는 -s Done)이면 장 대응표로 영향받는 컴포넌트를 찾는다. 그 컴포넌트 저장소에 대응 변경(같은 태스크 ID의 커밋 · 브랜치)이 있거나, 커밋 트레일러에 "영향 없음(사유)"가 있어야 통과한다.

미결(착수 시 결정):
- 저장소를 건너는 확인 방식: 로컬 components/* 경로의 git을 보는가, 원격 브랜치를 보는가.
- "영향 없음(사유)" 트레일러의 이름.
- 차단 시점: 커밋 · Done · push 전 중 어디인가.

관련:
- coralstay-software-factory DRAFT-2(설계 문서 계층의 이유와 전파 규칙을 최상위 문서에 넣는다): 장 대응표(최상위 장 → 컴포넌트 장)를 최상위 00 문서 정보의 '문서 계층' 절에 둔다. 이 훅은 그 표를 읽는다. 트레일러 이름은 여기서 정해 그쪽 편집 규칙에 반영한다.
- decision-3(라우터 · 디스패처 없이 완전 독립형 설계 유지): 새 독립형 훅 파일로 만든다.
- decision-1(커맨드 문자열 매칭 훅은 basename 정규화까지만): git commit 명령 문자열 매칭의 한계를 그대로 안고 간다.
- decision-12(테스트 먼저).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 장 대응표는 하드코딩하지 않고 최상위 design/00-문서-정보.md에서 읽는다
- [ ] #2 훅은 최상위 design/을 가진 저장소에서만 작동하고, 그 밖의 저장소에서는 통과시킨다
- [ ] #3 테스트를 먼저 쓰고, settings.hooks.json에 등록하고, README · CLAUDE.md.snippet에 전파 규칙과 트레일러 형식을 반영한다
- [ ] #4 최상위 태스크를 -s Done으로 옮길 때, 그 태스크 브랜치에서 design/을 바꾼 커밋들의 장을 장 대응표로 컴포넌트에 대응시키고, 컴포넌트마다 로컬 components/<이름> 저장소(모든 브랜치)에 'Refs: coralstay-software-factory <최상위 태스크 ID>' 커밋이 있거나 최상위 커밋에 'Propagation-None: <컴포넌트>: <사유>' 트레일러가 있지 않으면 deny하고 빠진 컴포넌트를 안내한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 테스트가 통과한 로그를 final summary에 남긴다
- [ ] #2 새 훅은 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트에 반영, 커버리지 100%
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 최상위 설계 문서를 고치면 하위 컴포넌트 설계 문서도 반드시 고치게 훅으로 강제하기를 원한다(2026-10-12). 최상위 ↔ 컴포넌트 불일치가 쌓이는 것을 막기 위해서다.

### Objective
- 최상위 저장소(coralstay-software-factory)는 components/를 .gitignore로 제외하고, 컴포넌트 3개는 서브모듈이 아닌 독립 git 저장소다. .gitmodules는 없다.
- 지금 어떤 훅도 최상위 design/ 변경과 컴포넌트 design/ 변경을 서로 대조하지 않는다.
- 장 대응표는 아직 없다. 최상위 00 문서 정보의 '대상 저장소' 표에 컴포넌트 → 3.03 §1 ~ §3 대응만 있다. 표는 coralstay-software-factory DRAFT-2에서 만든다.
- 10-11 사전 점검에서 최상위 ↔ 컴포넌트 불일치 29건.

### Assessment
새 독립형 훅(decision-3) 하나로 최상위 design/ 변경을 잡는다. 영향 범위는 최상위 00 문서 정보의 장 대응표에서 읽어, 표만 고치면 훅을 고치지 않아도 되게 한다. 영향이 없는 변경도 있으므로 사유를 남기는 트레일러로 빠져나갈 길을 둔다. 저장소를 건너는 확인 방식 · 트레일러 이름 · 차단 시점은 착수 시 유저와 정한다. 명령 문자열 매칭의 한계(decision-1)는 그대로 받아들인다.

### Plan
1. 미결 세 가지(확인 방식 · 트레일러 이름 · 차단 시점)를 유저와 정하고 decision으로 남긴다.
2. coralstay-software-factory DRAFT-2의 장 대응표 형식을 확인한다(없으면 그 반영을 먼저 한다).
3. AC 순서대로 테스트를 먼저 쓴다(<ID>#<n> · <ID>#B<k> 표식).
4. 훅 파일을 만든다: 최상위 저장소 판별 → 스테이징된 design/ 변경 장 추출 → 대응표로 컴포넌트 찾기 → 대응 변경 또는 트레일러 확인.
5. PreToolUse(Bash)에 settings.hooks.json으로 등록하고, 공유 함수를 복사했으면 dedup_drift_guard REGISTRY에 등록한다.
6. README · CLAUDE.md.snippet에 전파 규칙과 트레일러 형식을 반영한다.

착수 시 결정(유저, 2026-10-21): 확인 방식 = 로컬 components/* 저장소의 모든 브랜치, 영향 없음 트레일러 = 'Propagation-None: <컴포넌트>: <사유>'(컴포넌트마다 한 줄), 차단 시점 = 최상위 태스크 -s Done. 대응 변경은 '같은 태스크 ID'가 아니라 컴포넌트 카드 커밋 본문의 'Refs: coralstay-software-factory <ID>'로 본다(최상위 TASK-16 결정). 장 대응표는 최상위 TASK-16이 00 문서 정보 '문서 계층 > 장 대응표'에 넣었다(파싱 규칙은 표 위에 적혀 있다).
<!-- SECTION:PLAN:END -->
