---
id: TASK-26
title: TASK-24 잔여물 test_pre_merge_check.py 삭제 — 테스트 스위트 수집 실패 복구
status: To Do
assignee: []
created_date: '2026-10-03 03:38'
updated_date: '2026-10-03 03:40'
labels:
  - hooks
  - tests
dependencies: []
references:
  - TASK-24
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-24에서 hooks/pre_merge_check.py는 지웠지만 hooks/test_pre_merge_check.py가 git에 남아 있다. pytest 수집 단계에서 ModuleNotFoundError: pre_merge_check로 전체 스위트가 중단된다. 이 파일만 빼면 421개가 통과한다(2026-10-03 실측).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 hooks/test_pre_merge_check.py를 삭제한다
- [ ] #2 hooks 디렉토리에서 pytest 전체가 수집 에러 없이 통과한다
- [ ] #3 설치된 사본 ~/.claude/hooks/claude-rails/test_pre_merge_check.py도 있으면 제거한다
<!-- AC:END -->
