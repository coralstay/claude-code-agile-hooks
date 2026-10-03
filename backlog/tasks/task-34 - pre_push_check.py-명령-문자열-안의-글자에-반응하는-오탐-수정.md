---
id: TASK-34
title: 'pre_push_check.py: 명령 문자열 안의 글자에 반응하는 오탐 수정'
status: To Do
assignee: []
created_date: '2026-10-03 07:58'
updated_date: '2026-10-03 08:02'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-28
  - TASK-29
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pre_push_check.py는 Bash 명령 어디에든 'git' 'push' 글자가 있으면 push로 보고 태스크 상태를 검사한다. 2026-10-03 실측: heredoc 본문에 그 글자가 들어 있는 명령이 막혔고, 'backlog task edit ... -s Done && ... && (push)'처럼 상태를 바꾸는 명령과 같은 줄에 있으면 상태가 바뀌기 전 시점에 판정돼 막혔다. TASK-28(pr_provenance_stamp)과 같은 종류의 문제다. 실제 명령 위치의 push만 판정하도록 고친다(TASK-29의 tokenize/split_segments 패턴 재사용).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 따옴표 인자·heredoc 본문 안의 글자에는 반응하지 않는다
- [ ] #2 실제 명령 위치의 push는 지금처럼 검사한다(경로·전역 플래그 포함)
- [ ] #3 재현 케이스를 테스트로 추가하고 전체 스위트가 통과한다
<!-- AC:END -->
