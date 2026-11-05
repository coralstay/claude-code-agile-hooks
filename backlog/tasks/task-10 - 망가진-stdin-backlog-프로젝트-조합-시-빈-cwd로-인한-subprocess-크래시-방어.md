---
id: TASK-10
title: 망가진 stdin + backlog 프로젝트 조합 시 빈 cwd로 인한 subprocess 크래시 방어
status: Done
assignee: []
created_date: '2026-09-19 01:25'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/block_stop_if_dirty.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
block_stop_if_dirty.py/session_start.py/require_active_task.py는 stdin이 JSON이 아니면 cwd를 빈 문자열로 폴백한다. is_backlog_project("")가 os.path.join("", ...)을 pytest/Claude Code 프로세스의 실제 OS cwd 기준 상대경로로 평가하는데, 이 레포처럼 실제 cwd 자체가 backlog 프로젝트면 우연히 True가 되어 has_active_task("")/is_dirty("") 안의 subprocess.run(cwd="")이 FileNotFoundError로 죽는다(빈 문자열은 유효한 cwd가 아님). pre_commit_check.py/pre_push_check.py는 커맨드가 git commit인지부터 먼저 확인하는 게이트 순서 덕에 우연히 안 죽었을 뿐 — 이번 세션에 backlog init을 하면서 처음 드러난 실제 버그이지 기존부터 있던 무관한 실패가 아니다. cwd가 falsy면 is_backlog_project가 항상 False를 반환하도록 방어하고, pre_merge_check.py/pre_push_coverage_check.py/dedup_drift_guard.py도 같은 패턴이 있는지 점검해 필요하면 같이 고친다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 block_stop_if_dirty.py, session_start.py, require_active_task.py의 is_backlog_project()가 cwd가 falsy(빈 문자열 등)면 즉시 False를 반환하도록 가드 추가
- [x] #2 pre_merge_check.py, pre_push_coverage_check.py, dedup_drift_guard.py도 동일 패턴(빈 cwd + subprocess) 위험이 있는지 점검하고 필요하면 같은 가드 적용
- [x] #3 test_main_exits_cleanly_on_malformed_stdin이 3개 파일 모두 이 레포처럼 backlog/config.yml이 실제로 존재하는 상태에서도(즉 cwd='' 트릭 없이) 통과하는지 확인하는 회귀 테스트로 보강
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
block_stop_if_dirty.py/session_start.py/require_active_task.py의 is_backlog_project()에 'cwd가 falsy면 즉시 False' 가드 추가 (AC1). dedup_drift_guard.py의 REGISTRY가 이 함수의 AST 동일성을 5개 파일(+pre_commit_check.py, pre_push_check.py) 전체에 요구하므로(test_dedup_registry.py), 그 두 파일도 동일 가드로 함께 수정 — 안 그러면 dedup drift로 새 회귀가 생김. pre_merge_check.py(cwd/subprocess 미사용), pre_push_coverage_check.py, dedup_drift_guard.py는 점검 결과 위험 없음: 둘 다 command_invokes_git_subcommand()로 '이게 git push/commit인가'부터 확인하는 게이트가 cwd 사용보다 먼저 실행되어 malformed stdin(cwd='') 경로가 subprocess.run(cwd='')에 도달하기 전에 항상 먼저 종료됨 — 이는 순서상 설계된 방어이지 우연이 아님(코드 직접 추적으로 확인, 각 파일 기존 malformed_stdin 테스트로도 확인) (AC2). block_stop_if_dirty.py/session_start.py/require_active_task.py의 test_main_exits_cleanly_on_malformed_stdin 옆에 monkeypatch.chdir(tmp_path)로 실제 backlog 프로젝트처럼 보이는 디렉토리로 테스트 프로세스 cwd를 바꾼 뒤 망가진 stdin을 주는 회귀 테스트를 추가 — 가드를 되돌리면 FileNotFoundError로 실패하는 것 확인 완료 (AC3). 저장소 루트에서 python3 -m pytest hooks/ -q 실행 결과 438 passed (기존 435 + 신규 3), 3건 실패 모두 해소됨.
<!-- SECTION:FINAL_SUMMARY:END -->
