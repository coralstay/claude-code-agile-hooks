---
id: TASK-48
title: 'config_guard: hooks-logs 경로를 보호 hooks 디렉토리로 오인하는 오탐'
status: Done
assignee: []
created_date: '2026-10-03 18:45'
updated_date: '2026-10-04 01:20'
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
- [x] #1 보호 경로 판정이 경로 구성요소 경계를 지켜 .claude/hooks-logs·.claude/hooksx 등을 .claude/hooks로 보지 않는다
- [x] #2 .claude/hooks 자체와 그 하위 경로 쓰기는 지금처럼 막는다
- [ ] #3 재현 테스트를 추가하고 커버리지 100%·전체 스위트를 유지하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config_guard의 hooks 디렉토리 텍스트 검사가 hooks\b를 써서 '-'를 경계로 보던 탓에 .claude/hooks-logs를 보호 디렉토리로 오인했다. 이제 .claude/hooks 뒤가 끝·/·공백·따옴표·셸/코드 구분자(;&|()<>,:[]{}*?$·백틱)일 때만 일치한다(글롭·$ 뒤는 hooks 자체로 확장될 수 있어 보호 유지). hooks-logs/hooksx/hooks_old/hooks.bak은 보호 대상이 아니다. 테스트 중 실제 우회도 찾아 막았다: ..가 들어간 경로(cp x ~/.claude/hooks-x/../hooks/y, > ~/.claude/hooks-logs/../settings.json, Write .../hooks-logs/../hooks/x.py)가 셸 검사와 Edit/Write 검사를 모두 통과했다 → 쓰기 대상은 원문과 normpath 결과 둘 다 검사, 코드·텍스트 속 .claude/ 아래 ..는 보수적으로 보호 경로 언급으로 본다. hooks-logs 쓰기·삭제는 통과(훅 자신의 로그). settings.json* 동작은 유지(.bak 쓰기 대상은 이미 통과, 텍스트 언급은 보수적). 실패 상태 재현 18건, 추가 55건, 기존 테스트 변경 없음. 1688 passed, 커버리지 100%. 이번엔 훅 차단·우회 없음. AC #3 설치 남음.
<!-- SECTION:FINAL_SUMMARY:END -->
