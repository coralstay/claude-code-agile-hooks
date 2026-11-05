---
id: TASK-4
title: 'block_dangerous_commands.py: rm -rf 탐지 범위 확장'
status: Done
assignee: []
created_date: '2026-09-18 16:12'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/block_dangerous_commands.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
CRITICAL_PATTERNS의 rm -rf 규칙이 대상이 정확히 /, ~, $HOME일 때만 매칭된다. rm -rf ../other-project, rm -rf * 처럼 루트/홈이 아닌 임의 경로를 통째로 지우는 흔한 실수/오판은 critical/high/strict 어느 레벨에서도 전혀 안 걸린다. README는 이 훅을 "재앙적/고위험 셸 명령 차단"이라 소개하지만 실제 방어 범위는 루트/홈 삭제로 좁게 한정돼 있다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 high 레벨 이상에 rm -rf 대상이 ..로 상위 디렉토리를 벗어나거나 cwd 밖 절대경로를 가리키는 경우를 새 패턴으로 추가 (cwd 내부 rm -rf는 그대로 통과)
- [x] #2 test_block_dangerous_commands.py에 새 패턴의 positive/negative 케이스 추가 (정상 rm -rf ./dist 회귀 테스트 포함)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
HIGH_PATTERNS에 rm -rf 상위 디렉토리 탈출(.., 중간 경로 포함)과 cwd 밖 절대경로(흔한 /tmp류 안전 디렉토리 제외) 탐지 패턴 2개 추가. 기존 critical 루트/홈 규칙은 그대로 유지. test_block_dangerous_commands.py에 positive 4건 + negative(회귀) 4건 추가, TDD로 red(4 fail)->green(25 pass) 확인. 전체 hooks/ 스위트 384건 중 무관한 기존 실패 3건(test_main_exits_cleanly_on_malformed_stdin) 외 전부 통과.
<!-- SECTION:FINAL_SUMMARY:END -->
