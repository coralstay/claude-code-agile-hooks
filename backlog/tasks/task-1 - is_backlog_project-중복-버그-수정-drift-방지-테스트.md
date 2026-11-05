---
id: TASK-1
title: is_backlog_project() 중복 버그 수정 + drift 방지 테스트
status: Done
assignee: []
created_date: '2026-09-18 16:12'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - 삽질기록.md
  - hooks/require_active_task.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
삽질기록.md(2026-09-10)에 기록된 "서브폴더 존재만으로 backlog 프로젝트라고 오판하면 안 된다" 교훈이 require_active_task.py 1곳에만 반영되고, 동일 is_backlog_project() 로직이 복붙된 나머지 4개 훅(pre_commit_check.py, pre_push_check.py, block_stop_if_dirty.py, session_start.py)에는 .git 체크가 빠져 있다. 훅이 완전 독립형(공용 import 없음)으로 설계된 데서 오는 부작용 — 한 곳에서 고친 버그가 복붙된 다른 곳에 전파 안 됨.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pre_commit_check.py, pre_push_check.py, block_stop_if_dirty.py, session_start.py의 is_backlog_project()에 require_active_task.py와 동일한 .git 존재 체크 추가
- [x] #2 5개 훅의 is_backlog_project() 구현이 전부 동일한지 비교하는 테스트 추가 (drift 재발 방지)
- [x] #3 각 훅의 기존 test_*.py에 backlog/config.yml만 있고 .git 없는 폴더에서는 검사가 스킵되는 케이스 추가
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
4개 훅(pre_commit_check, pre_push_check, block_stop_if_dirty, session_start)의 is_backlog_project()에 require_active_task.py와 동일한 .git 존재 체크를 추가(AC1). hooks/test_dedup_registry.py를 새로 추가해 5개 훅의 is_backlog_project() AST를 정규화 비교하는 drift 방지 테스트를 만들고, 원래 버그를 임시 재현해 테스트가 실제로 잡아내는지 검증(AC2). 각 훅의 기존 test_*.py에 .git 없이 backlog/config.yml만 있으면 스킵(False) 처리되는 케이스를 require_active_task.py 패턴대로 추가(AC3). python3 -m pytest hooks/ -v 결과 356 passed, 기존에도 있던(우리 변경과 무관, main에서도 동일하게 실패하는) test_main_exits_cleanly_on_malformed_stdin 3건만 실패.
<!-- SECTION:FINAL_SUMMARY:END -->
