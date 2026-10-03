---
id: DRAFT-5
title: 'pre_git_safety_check: gh 검사가 줄 전체 토큰을 훑어 생기는 오탐·미탐'
status: Draft
assignee: []
created_date: '2026-10-03 13:13'
updated_date: '2026-10-03 13:13'
labels:
  - hooks
  - bug
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-03 실측: 'gh pr list ...; ... git merge --ff-only origin/main' 한 줄이 'gh pr merge 계열 금지'로 막혔다. gh 검사가 줄 전체 토큰에서 gh·pr·merge를 따로 찾기 때문이다(오탐). 반대로 /usr/bin/gh 같은 경로 호출은 basename 정규화가 없어 못 잡는다(미탐). TASK-37에서 git 쪽에 적용한 명령 위치 판정(세그먼트별 command_head + basename)을 gh 검사에도 적용한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 gh 파괴 명령은 같은 세그먼트의 명령 위치에서 gh(basename) 다음 하위 명령으로만 판정한다
- [ ] #2 서로 다른 세그먼트에 흩어진 gh와 merge 같은 단어 조합은 막지 않는다
- [ ] #3 /usr/bin/gh 같은 경로 호출도 같은 규칙으로 막는다
- [ ] #4 재현 테스트를 추가하고 전체 스위트·커버리지 100%를 유지하며 설치본을 갱신한다
<!-- AC:END -->
