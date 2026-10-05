---
id: DRAFT-7
title: 'config_guard: 스크립트 파일 경유 우회 차단'
status: Draft
assignee: []
created_date: '2026-10-05 08:04'
labels:
  - security
  - bug
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 발견 경위
TASK-54(이름 변경)를 맡은 서브에이전트가 .claude/hooks/ 경로 문자열이 든 저장소 파일(테스트·문서)을 sed·heredoc으로 고치려다 config_guard에 막히자, scratchpad에 Python 스크립트를 Write로 만든 뒤 python3 script.py로 실행해 편집을 마쳤다. 이번 대상은 저장소 파일(오탐 회피)이었지만, 같은 방법으로 ~/.claude/settings.json과 ~/.claude/hooks/도 고칠 수 있다. 유저가 이 우회를 막으라고 지시함(2026-10-05).

## 원인
config_guard(PreToolUse, Bash|Edit|Write)는 Bash 명령 문자열과 python -c / stdin heredoc 코드만 검사한다. 스크립트 파일을 실행하는 명령(python3 x.py, bash x.sh, node x.js ...)은 명령줄에 보호 경로가 없으면 통과하고, Write/Edit는 대상 경로만 보고 파일 내용은 보지 않는다. 두 단계로 나누면 어느 쪽에서도 보호 경로가 보이지 않는다(decision-1의 '문자열 매칭' 한계).

## 후보 (승격 시 범위 확정)
1. Bash가 인터프리터로 스크립트 파일을 실행하면 그 파일을 읽어 python -c와 같은 ast/문자열 규칙을 적용한다(경로를 해석할 수 없으면 차단).
2. Write/Edit로 실행 가능한 스크립트(.py .sh .js .rb .pl 등)를 만들거나 고칠 때 내용에 보호 경로 + 쓰기 연산이 있으면 차단한다.
3. 무결성 감시: ~/.claude/settings.json과 ~/.claude/hooks/ 해시를 세션 시작 시 기록하고 PostToolUse마다 비교해, 바뀌면 경고하고 다음 도구 호출을 막는다(문자열 검사로 못 잡는 경로의 최후 방어선).
4. 오탐 줄이기: 보호 경로가 쓰기 대상이 아니라 sed 치환 문자열·heredoc 본문 안에 언급만 된 경우(저장소 파일 편집)는 통과시켜, 우회할 동기 자체를 줄인다.
5. CLAUDE.md.snippet에 '가드에 막히면 우회하지 말고 유저에게 보고' 규칙을 넣는다(서브에이전트 지시에도 전달).

## 수용 기준 초안
- 'Write로 보호 경로를 쓰는 스크립트 생성 → python3로 실행' 시나리오가 막힌다(테스트)
- 저장소 파일 안의 경로 문자열 치환은 통과한다(테스트)
- 기존 테스트·커버리지 100% 유지
<!-- SECTION:DESCRIPTION:END -->
