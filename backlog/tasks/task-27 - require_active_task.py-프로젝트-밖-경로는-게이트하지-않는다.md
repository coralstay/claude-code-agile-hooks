---
id: TASK-27
title: 'require_active_task.py: 프로젝트 밖 경로는 게이트하지 않는다'
status: Done
assignee: []
created_date: '2026-10-03 03:38'
updated_date: '2026-10-03 03:48'
labels:
  - hooks
  - backlog
dependencies:
  - TASK-26
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
require_active_task.py는 In Progress 태스크가 없으면 Edit/Write를 경로와 무관하게 전부 막는다. 2026-10-03 세션에서 실제로 세 번 막혔다: plan mode의 계획 파일(~/.claude/plans/*.md) 저장, auto memory 파일(~/.claude/projects/*/memory/*.md) 수정, 세션 스크래치패드(/private/tmp/claude-*/.../scratchpad) 쓰기. 이 훅의 목적은 프로젝트 코드를 태스크 없이 고치지 않게 하는 것이므로, tool_input.file_path가 cwd(프로젝트 루트) 밖이면 통과시키는 것이 맞다. plan mode 단계는 태스크가 생기기 전이므로 이 예외 없이는 계획→드래프트 파이프라인 자체가 데드락이다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Edit/Write의 file_path가 프로젝트 루트(cwd) 밖이면 태스크 검사 없이 통과한다
- [x] #2 경로를 realpath로 정규화한 뒤 판정해 ../나 심볼릭 링크로 프로젝트 안을 가리키는 우회를 막는다
- [x] #3 file_path가 없는 입력은 기존과 동일하게 검사한다
- [x] #4 테스트를 추가하고 전체 스위트가 통과한다
- [x] #5 설치된 사본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
require_active_task.py가 Edit/Write의 file_path(또는 notebook_path)를 cwd 기준으로 realpath 정규화해 프로젝트 루트 밖이면 태스크 검사 없이 통과시킨다. plan 파일·memory·scratchpad 쓰기가 막히던 데드락 해소. ../ 경유나 심볼릭 링크로 프로젝트 안을 가리키는 경로는 계속 검사한다. 테스트 10개 추가, uvx pytest 431 passed. README·doc-2 반영. 설치본은 사용자가 직접 cp(config_guard가 에이전트 복사를 막음)했고 cmp로 일치 확인.
<!-- SECTION:FINAL_SUMMARY:END -->
