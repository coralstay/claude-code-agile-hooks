---
id: TASK-35
title: 'config_guard.py: 설정 파일을 읽기만 하는 명령까지 막는 오탐 수정'
status: In Progress
assignee: []
created_date: '2026-10-03 08:01'
updated_date: '2026-10-03 12:16'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-3
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-03 일괄 설치 직후, 설치본 검증용 명령(cmp 루프 + heredoc의 python이 ~/.claude/settings.json을 json.load로 읽어 개수만 출력)이 config_guard.py에 '훅/설정 파일을 변경하는 명령'으로 차단됐다. 쓰기가 없는 읽기 전용 명령이었다. 같은 검증을 cmp 단독, jq 읽기로 나누자 통과했다. 어떤 패턴이 오탐을 냈는지(heredoc 본문, ~/.claude 경로 + python, cmp의 $HOME 경로 등) 재현으로 특정하고, 쓰기 신호가 없는 읽기는 통과시키되 기존 우회 차단(TASK-3: 인터프리터/curl 경유 쓰기)은 유지한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 오탐을 낸 패턴을 재현 테스트로 특정한다
- [x] #2 쓰기 신호가 없는 읽기 전용 명령(cmp, cat, jq, python의 json.load만 하는 heredoc 등)은 통과한다
- [x] #3 TASK-3의 인터프리터/curl 경유 쓰기 차단 테스트가 모두 그대로 통과한다
- [ ] #4 전체 스위트가 통과하고 설치본을 갱신한다
<!-- AC:END -->
