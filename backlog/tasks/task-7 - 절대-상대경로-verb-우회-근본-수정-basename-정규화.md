---
id: TASK-7
title: 절대/상대경로 verb 우회 근본 수정 (basename 정규화)
status: Done
assignee: []
created_date: '2026-09-19 01:25'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - README.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
command_invokes_git_subcommand()(5개 파일 복붙: pre_commit_check.py, pre_push_check.py, pre_merge_check.py, pre_push_coverage_check.py, dedup_drift_guard.py), config_guard.py의 MUTATING_VERBS/INTERPRETER_VERBS 매칭, case_insensitive_guard.py, protect_tests.py가 전부 tokens[0]을 원본 문자열 그대로 정확 일치(== "git", in {"rm",...})로만 비교한다. /usr/bin/git, ./git, /bin/rm, /usr/bin/python3 같은 절대/상대경로 호출이면 전부 미탐지 — python3 -c로 직접 재현 완료. sudoers 모범 사례(절대경로 전체 명시 또는 basename 정규화)를 참고해 각 verb 비교 지점에서 os.path.basename()으로 정규화한 뒤 비교하도록 고친다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 command_invokes_git_subcommand()의 tokens[i] != 'git' 비교를 os.path.basename(tokens[i]) != 'git'로 바꿔 pre_commit_check.py, pre_push_check.py, pre_merge_check.py, pre_push_coverage_check.py, dedup_drift_guard.py 5곳 전부 동일하게 수정
- [x] #2 config_guard.py의 verb 추출(tokens[0])을 basename 정규화해서 MUTATING_VERBS/INTERPRETER_VERBS 비교
- [x] #3 case_insensitive_guard.py, protect_tests.py의 verb/토큰 비교도 basename 정규화 적용
- [x] #4 각 파일 test_*.py에 /usr/bin/git, ./git, /bin/rm, /usr/bin/python3 같은 절대/상대경로 우회가 이제 차단되는 회귀 테스트 추가 (정상 케이스도 유지되는지 negative 테스트 포함)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
5개 파일(pre_commit_check, pre_push_check, pre_merge_check, pre_push_coverage_check, dedup_drift_guard)의 command_invokes_git_subcommand()를 os.path.basename() 정규화로 통일(AST 동일성 검증 완료), config_guard.py의 verb 추출과 case_insensitive_guard.py/protect_tests.py의 rm/mv/unlink 토큰 비교도 동일 원칙으로 수정. 8개 파일 전부에 절대/상대경로 우회 회귀 테스트 + verb 위치 밖 오탐 방지 negative 테스트 추가. python3 -m pytest hooks/ -q: 421 passed, TASK-10 소관인 malformed-stdin 3건만 기존대로 실패(무관).
<!-- SECTION:FINAL_SUMMARY:END -->
