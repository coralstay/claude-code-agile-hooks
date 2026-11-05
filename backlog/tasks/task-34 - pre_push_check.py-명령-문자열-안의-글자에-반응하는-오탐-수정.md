---
id: TASK-34
title: 'pre_push_check.py: 명령 문자열 안의 글자에 반응하는 오탐 수정'
status: Done
assignee: []
created_date: '2026-10-03 07:58'
updated_date: '2026-10-03 08:11'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-28
  - TASK-29
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pre_push_check.py는 Bash 명령 어디에든 'git' 'push' 글자가 있으면 push로 보고 태스크 상태를 검사한다. 2026-10-03 실측: heredoc 본문에 그 글자가 들어 있는 명령이 막혔고, 'backlog task edit ... -s Done && ... && (push)'처럼 상태를 바꾸는 명령과 같은 줄에 있으면 상태가 바뀌기 전 시점에 판정돼 막혔다. TASK-28(pr_provenance_stamp)과 같은 종류의 문제다. 실제 명령 위치의 push만 판정하도록 고친다(TASK-29의 tokenize/split_segments 패턴 재사용).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 따옴표 인자·heredoc 본문 안의 글자에는 반응하지 않는다
- [x] #2 실제 명령 위치의 push는 지금처럼 검사한다(경로·전역 플래그 포함)
- [x] #3 재현 케이스를 테스트로 추가하고 전체 스위트가 통과한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pre_push_check.py가 명령 문자열 어디든 push 글자가 있으면 반응하던 것을 고쳤다. heredoc 본문 제거 → 줄 이음 결합 → 토큰화·세그먼트 분할 → command_head(환경변수 할당·래퍼 건너뜀)로 명령어를 찾고 basename이 git이면 전역 플래그(-C, -c, --git-dir)를 건너뛰어 다음 단어가 push인지 본다. 따옴표 인자·heredoc·echo 안의 글자는 무시하고 실제 push는 기존과 동일하게 검사한다. 토큰화 불가(따옴표 불균형)면 보수적으로 push로 본다. PreToolUse 시점 한계(같은 줄의 상태 변경 전에 판정)는 docstring과 테스트로 고정. 헬퍼는 REGISTRY 등록(command_head 신규). 36개 테스트 추가, 701 passed. 설치본(dedup_drift_guard, pre_push_check)은 사용자가 갱신했고 cmp 일치 확인 — 설치된 drift 가드가 옛 REGISTRY로 저장소를 검사해 커밋이 막혔던 것이 계기. 같은 계열 문제(pre_push_coverage_check·pre_commit_check의 문자열 매칭, pre_git_safety_check의 git 절대경로 미정규화)는 후속 드래프트로.
<!-- SECTION:FINAL_SUMMARY:END -->
