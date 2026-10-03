---
id: TASK-26
title: TASK-24 잔여물 test_pre_merge_check.py 삭제 — 테스트 스위트 수집 실패 복구
status: Done
assignee: []
created_date: '2026-10-03 03:38'
updated_date: '2026-10-03 03:44'
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
- [x] #1 hooks/test_pre_merge_check.py를 삭제한다
- [x] #2 hooks 디렉토리에서 pytest 전체가 수집 에러 없이 통과한다
- [x] #3 설치된 사본 ~/.claude/hooks/claude-rails/test_pre_merge_check.py도 있으면 제거한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
TASK-24에서 남은 hooks/test_pre_merge_check.py를 삭제했다(사용자가 git rm으로 직접 실행 — protect_tests.py가 에이전트의 테스트 파일 삭제를 막음). 설치된 사본도 제거됐다. hooks에서 uvx pytest -q 결과 421 passed, 수집 에러 없음.
<!-- SECTION:FINAL_SUMMARY:END -->
