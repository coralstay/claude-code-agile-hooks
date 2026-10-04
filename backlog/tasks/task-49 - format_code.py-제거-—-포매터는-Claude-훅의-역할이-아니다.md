---
id: TASK-49
title: format_code.py 제거 — 포매터는 Claude 훅의 역할이 아니다
status: In Progress
assignee: []
created_date: '2026-10-04 01:48'
updated_date: '2026-10-04 01:57'
labels:
  - hooks
  - policy
dependencies: []
references:
  - TASK-24
  - TASK-44
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
format_code.py(PostToolUse Edit|Write)는 수정된 파일 전체에 ruff format / prettier --write를 돌리고 ruff check·tsc 결과를 보고한다. 업스트림 플러그인 두 개를 이식한 것으로, claude-rails의 목적(가드·게이트·관측)을 위해 설계된 훅이 아니다.

## 왜 제거하나

- 유일하게 에이전트 모르게 파일 내용을 바꾸는 훅이다. 포맷은 프로젝트가 자기 설정으로 git pre-commit·에디터·CI(--check)에서 책임질 일이다.
- 프로젝트가 그 포매터를 쓰는지 확인하지 않는다. 이 저장소는 Python 29개 파일·671줄이 ruff 스타일과 달라, 한 줄 Edit에 무관한 줄이 대량으로 바뀌었다(문서 행 하나 추가에 약 160줄).
- 수정 직후 파일이 바뀌어 Claude가 본 내용이 낡고 다음 Edit가 어긋난다.
- diff를 작게 유지하려던 서브에이전트들이 파일을 되돌리고 스크립트로 다시 쓰면서 Edit/Write의 PreToolUse 검사(protect_tests, config_guard)를 거치지 않게 됐다. TASK-44의 가드 회피도 이 흐름에서 나왔다.
- 프로젝트 밖 파일(계획 파일, 스크래치패드)까지 포맷한다.
- prettier가 없으면 npx --yes prettier로 매 Edit마다 npm에서 패키지를 받아 실행할 수 있다(공급망·네트워크 위험).

## 범위

- hooks/format_code.py, hooks/test_format_code.py 삭제(테스트 삭제는 protect_tests가 막으므로 사용자가 git rm)
- settings.hooks.json의 PostToolUse(Edit|Write) 항목 제거
- README·doc-2의 서술과 훅 수 갱신
- 계약 테스트·커버리지 100% 유지
- 설치본과 ~/.claude/settings.json 항목 제거(merge_settings는 삭제하지 않으므로 사용자가 직접)

lint 피드백(ruff check, tsc)은 필요해지면 "파일을 바꾸지 않고, 프로젝트에 lint 설정이 있을 때만 보고하는 훅"으로 따로 설계한다 — 이번 범위가 아니다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 hooks/format_code.py와 hooks/test_format_code.py를 삭제한다
- [ ] #2 settings.hooks.json에서 format_code 항목을 제거하고 계약 테스트(등록·실행)가 통과한다
- [ ] #3 README·doc-2에서 format_code 서술을 제거하고 훅 수를 맞춘다
- [ ] #4 전체 스위트와 커버리지 100% 게이트가 통과한다
- [ ] #5 설치본과 ~/.claude/settings.json의 format_code 항목을 제거한다
<!-- AC:END -->
