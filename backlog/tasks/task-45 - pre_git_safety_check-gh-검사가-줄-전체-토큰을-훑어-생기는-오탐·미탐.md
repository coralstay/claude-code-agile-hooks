---
id: TASK-45
title: 'pre_git_safety_check: gh 검사가 줄 전체 토큰을 훑어 생기는 오탐·미탐'
status: Done
assignee: []
created_date: '2026-10-03 13:13'
updated_date: '2026-10-03 17:33'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-37
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-03 실측: 'gh pr list ...; ... git merge --ff-only origin/main' 한 줄이 'gh pr merge 계열 금지'로 막혔다. gh 검사가 줄 전체 토큰에서 gh·pr·merge를 따로 찾기 때문이다(오탐). 반대로 /usr/bin/gh 같은 경로 호출은 basename 정규화가 없어 못 잡는다(미탐). TASK-37에서 git 쪽에 적용한 명령 위치 판정(세그먼트별 command_head + basename)을 gh 검사에도 적용한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 gh 파괴 명령은 같은 세그먼트의 명령 위치에서 gh(basename) 다음 하위 명령으로만 판정한다
- [x] #2 서로 다른 세그먼트에 흩어진 gh와 merge 같은 단어 조합은 막지 않는다
- [x] #3 /usr/bin/gh 같은 경로 호출도 같은 규칙으로 막는다
- [ ] #4 재현 테스트를 추가하고 전체 스위트·커버리지 100%를 유지하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pre_git_safety_check.py의 gh 검사를 git 쪽(TASK-37)과 같은 방식으로 바꿨다: 세그먼트별 명령 위치, 실행 파일 basename 비교, -R/--repo·--hostname 값 건너뛰기, 하위 명령 첫 두 단어 정확 일치. 'gh pr list; git merge --ff-only x' 같은 세그먼트 간 단어 조합 오탐을 없앴고, /usr/bin/gh 경로 호출과 cd x && gh pr merge(TASK-46 사고 줄)를 막는다. 금지 집합은 그대로(pr merge/close, issue close, release delete, repo delete). gh api 우회도 막는다: pulls/<n>/merge에 대한 비GET, repos·releases DELETE, pulls/issues PATCH state=closed 또는 --input, GraphQL merge/close/delete 뮤테이션. 러너 뒤 gh는 보수적으로 판정(따옴표 없는 echo gh pr merge는 오탐 수용). 파싱 불가 줄은 gh+파괴 동사쌍이면 차단. gh 검사를 push 검사보다 먼저 실행해 막힐 줄에서 git 호출을 하지 않는다. 1134 passed, 파일 커버리지 100%(__main__ 제외). 미커버: gh 별칭·확장, 파일에서 읽는 GraphQL, 기타 REST 엔드포인트, gh issue delete(원래 집합 밖). 검증 중 전체 스위트 1회 1 failed 후 12회 재실행 모두 통과 — 서브에이전트 실행과 겹친 동시 실행 간섭(공유 경로) 의심, TASK-43에서 병렬 실행 검증. AC #4 설치는 일괄.
<!-- SECTION:FINAL_SUMMARY:END -->
