---
id: TASK-48
title: 'config_guard: hooks-logs 경로를 보호 hooks 디렉토리로 오인하는 오탐'
status: In Progress
assignee: []
created_date: '2026-10-03 18:45'
updated_date: '2026-10-04 01:15'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-35
  - TASK-44
  - TASK-47
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-44 중 발견. 문서 텍스트에 .claude/hooks-logs/ 경로가 들어 있는 Python heredoc(저장소 문서 수정)이 '훅/설정 파일을 변경하는 명령'으로 막혔다. 끝 슬래시 없는 hooks 디렉토리 검사가 .claude/hooks-logs를 .claude/hooks의 하위로 보는 것으로 보인다(경로 구성요소 경계 미확인). 경로 비교를 구성요소 단위로 바꾼다. 이 오탐 때문에 서브에이전트가 보호 경로 문자열을 뺀 스크립트로 가드를 피해 간 일이 있었다 — 오탐은 가드 회피를 부르므로 우선 고친다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 보호 경로 판정이 경로 구성요소 경계를 지켜 .claude/hooks-logs·.claude/hooksx 등을 .claude/hooks로 보지 않는다
- [ ] #2 .claude/hooks 자체와 그 하위 경로 쓰기는 지금처럼 막는다
- [ ] #3 재현 테스트를 추가하고 커버리지 100%·전체 스위트를 유지하며 설치본을 갱신한다
<!-- AC:END -->
