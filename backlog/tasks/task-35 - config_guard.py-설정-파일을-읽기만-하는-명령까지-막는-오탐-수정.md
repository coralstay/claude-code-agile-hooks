---
id: TASK-35
title: 'config_guard.py: 설정 파일을 읽기만 하는 명령까지 막는 오탐 수정'
status: Done
assignee: []
created_date: '2026-10-03 08:01'
updated_date: '2026-10-03 12:22'
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
- [x] #4 전체 스위트가 통과하고 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config_guard.py를 셸 세그먼트 파싱 + Python ast 쓰기 판정으로 다시 썼다. 오탐 원인은 TASK-3의 인터프리터 규칙(python3 + 보호 경로가 어디든 등장하면 차단)이었다. 이제 heredoc 본문은 소유 명령에 붙여 판정하고, Python 코드(-c, stdin heredoc, here-string)는 보호 경로 언급과 쓰기 동작(쓰기 모드 open, write_text, shutil/os 파일 조작, subprocess, exec/eval, 별칭)이 함께 있을 때만 막는다. 순수 읽기(json.load, read_text, cmp/cat/jq 읽기)는 통과. 다시 쓰는 과정에서 기존 가드가 놓치던 쓰기 우회(-c 코드 안 ;로 잘림, sudo/FOO= 접두, bash -c/eval/$(...), xargs rm, ln/chmod/sed -i.bak, 디렉토리 대상 rm -rf/cp, 상대 경로)를 막고 테스트로 고정했다. 기존 테스트는 전부 변경 없이 통과, 760 passed. 의도적으로 남긴 오탐: 보호 경로를 텍스트로 언급하며 다른 곳에 쓰는 Python(대상이 변수라 증명 불가). 못 잡는 것(decision-1 범위): 난독화 경로, 앞 세그먼트 변수 경유, find -exec/awk 쓰기, Write 도구로 만든 스크립트 실행. 설치본은 사용자가 갱신했고 cmp 일치 + 실제 세션에서 읽기 전용 확인 명령 통과 확인.
<!-- SECTION:FINAL_SUMMARY:END -->
