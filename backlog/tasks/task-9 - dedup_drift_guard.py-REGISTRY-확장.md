---
id: TASK-9
title: dedup_drift_guard.py REGISTRY 확장
status: Done
assignee: []
created_date: '2026-09-19 01:25'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/dedup_drift_guard.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
grep으로 전수조사한 결과 REGISTRY에 is_backlog_project만 등록돼 있고, 실제로는 command_invokes_git_subcommand(5개 파일), has_command(5개 파일), has_active_task(3개 파일), run_shell(2개 파일)도 동일해야 하는 복붙 함수다. TASK-7에서 verb 정규화 로직이 command_invokes_git_subcommand 등에 새로 들어가면 그 변경도 5곳에 동시에 반영해야 하므로, 이 태스크는 TASK-7 이후에 진행해서 새 상태 기준으로 REGISTRY를 넓힌다. current_branch는 파일마다 반환값 계약이 달라(빈 문자열 vs None) 의도적으로 다른 구현으로 보이므로 REGISTRY 대상에서 제외한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 REGISTRY에 command_invokes_git_subcommand(5개 파일), has_command(5개 파일), has_active_task(3개 파일), run_shell(2개 파일) 추가
- [x] #2 TASK-7에서 basename 정규화가 반영된 이후의 최신 command_invokes_git_subcommand 기준으로 5개 파일이 실제로 AST 동일한지 확인 후 등록
- [x] #3 test_dedup_drift_guard.py에 새로 등록된 함수들에 대한 drift 탐지 케이스 추가(최소 1개 함수는 일부러 다르게 만들어서 차단되는지 확인)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
REGISTRY에 command_invokes_git_subcommand(5개), has_command(5개), has_active_task(3개), run_shell(2개) 등록 완료. 등록 전 AST 비교 스크립트로 4개 함수 모두 대상 파일 전체에서 완전히 동일함을 확인(코드 수정 불필요). current_branch는 실제로 파일마다 반환값이 다름(빈 문자열 vs None)을 AST 비교로 재확인하여 의도적으로 REGISTRY에서 제외. test_dedup_drift_guard.py의 fake-hooks 빌더를 단일 함수용(make_fake_registry_dir)에서 REGISTRY 전체를 커버하는 build_full_hooks_dir로 확장하고, has_command drift/missing 케이스 2개 및 REGISTRY 내용 자체를 검증하는 테스트를 추가. hooks/test_dedup_drift_guard.py 20건 전부 통과, hooks/ 디렉토리에서 실행한 전체 스위트 435건 전부 통과(리포 루트에서 실행 시 TASK-10 관련 malformed-stdin 3건만 별도 실패하며 본 태스크와 무관). dedup_drift_guard.py를 실제 리포에 대해 수동 실행해 이 리포 자신의 git commit이 새 REGISTRY 때문에 막히지 않음을 확인.
<!-- SECTION:FINAL_SUMMARY:END -->
