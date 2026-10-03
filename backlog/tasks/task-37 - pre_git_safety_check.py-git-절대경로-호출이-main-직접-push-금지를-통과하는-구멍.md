---
id: TASK-37
title: 'pre_git_safety_check.py: git 절대경로 호출이 main 직접 push 금지를 통과하는 구멍'
status: To Do
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-03 12:39'
labels:
  - hooks
  - security
dependencies: []
references:
  - decision-1
  - TASK-34
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-34 조사 중 발견. pre_git_safety_check.py의 git_args_after_subcommand는 tokens[i] != 'git'으로 비교해 basename 정규화를 하지 않는다. 그래서 /usr/bin/git으로 main에 직접 push하면 규칙을 통과한다(decision-1이 요구하는 basename 정규화 미적용). 또 명령 전체를 shlex로 나눠 따옴표 안 글자에도 반응하고, 파싱 실패 시 통과시킨다(fail-open). 보안 가드라 파싱 실패는 보수적으로 판정해야 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 git 실행 파일을 basename으로 비교해 절대·상대 경로 호출도 같은 규칙을 적용한다
- [ ] #2 명령 위치의 git만 판정하고 따옴표 인자·heredoc 안 글자는 무시한다(TASK-29/34 헬퍼 재사용, REGISTRY 등록)
- [ ] #3 파싱 실패 시 보수적으로 판정하고 그 근거를 docstring에 남긴다
- [ ] #4 재현 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->
