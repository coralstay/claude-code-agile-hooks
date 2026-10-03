---
id: TASK-28
title: 'pr_provenance_stamp.py: 복합 명령(&&, |)을 깨뜨리는 버그 수정'
status: Done
assignee: []
created_date: '2026-10-03 03:38'
updated_date: '2026-10-03 07:10'
labels:
  - hooks
  - bug
dependencies:
  - TASK-26
references:
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pr_provenance_stamp.py는 'gh' 'pr create'가 포함된 Bash 명령 전체를 shlex.split 후 다시 조립한다. 그래서 cd X && (PR 생성 명령)은 'cd: too many arguments'로, (PR 생성 명령) | tail -1은 'unknown shorthand flag: 1'로 실패한다(2026-10-03 실측). 셸 연산자가 인자로 바뀐다. 게다가 명령의 문자열 인자(예: backlog 드래프트 본문) 안에 그 글자가 들어 있기만 해도 매칭돼 무관한 명령까지 깨진다(같은 날 실측). 수정 방향: 실제 명령 위치에 있는 PR 생성 세그먼트만 찾아 그 범위 안에서만 --body를 고치고, 안전하게 고칠 수 없으면 원래 명령을 그대로 통과시킨다(스탬프 누락이 명령 실패보다 낫다).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 &&, ||, ;, |가 섞인 명령에서도 원래 명령의 의미가 보존된다
- [x] #2 문자열 인자 안에만 그 글자가 있는 무관한 명령은 건드리지 않는다
- [x] #3 단일 PR 생성 명령에는 기존처럼 스탬프가 들어간다
- [x] #4 재현 케이스를 테스트로 추가하고 전체 스위트가 통과한다
- [ ] #5 설치된 사본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pr_provenance_stamp.py가 명령 전체를 shlex로 재조립하던 것을 고쳤다. 따옴표를 인식하는 스캐너로 최상위 연산자(&&, ||, ;, |, &, 개행) 기준 세그먼트를 나누고, 토큰이 실제로 PR 생성 명령으로 시작하는 세그먼트 하나만 다시 써서 원래 문자열에 끼워 넣는다. 나머지 바이트는 원본 그대로다. 명령 치환·heredoc·괄호·변수 확장·리다이렉션·glob처럼 재인용이 의미를 바꿀 수 있는 경우는 손대지 않고 통과시킨다(스탬프 누락이 명령 실패보다 낫다). 문자열 인자 안에만 그 글자가 있는 명령은 매칭하지 않는다. 테스트 26개 추가(실제 bash 실행 차등 테스트 포함), uvx pytest 457 passed.

AC #5(설치본 갱신)는 사용자와 합의해 TASK-32까지 끝난 뒤 일괄 설치 때 체크한다.

후속 후보: -b/-F 단축 플래그 미인식(기존 동작), doc-2의 스탬프 항목 서술이 실제 코드와 다름(기존), pre_push_check.py도 heredoc 텍스트 안의 'git push'에 반응하는 같은 종류의 오탐이 있음.
<!-- SECTION:FINAL_SUMMARY:END -->
