---
id: TASK-8
title: 'block_dangerous_commands.py: rm -rf 플래그 변형 우회 수정'
status: Done
assignee: []
created_date: '2026-09-19 01:25'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/block_dangerous_commands.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
CRITICAL_PATTERNS/RM_RF_FLAGS 정규식이 결합된 소문자 -rf 토큰 하나만 본다. rm -Rf(macOS 표준 대문자), rm -r -f(분리 플래그), rm --recursive --force(GNU 롱플래그)가 critical/high/strict 전 레벨에서 미탐지 — 직접 재현 완료. 지난 작업에서 확장한 상위탈출/절대경로 패턴도 같은 RM_RF_FLAGS를 재사용해서 동일하게 뚫린다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 RM_RF_FLAGS 정규식(또는 대체 로직)이 -Rf, -r -f(분리), --recursive --force(롱플래그) 조합을 전부 잡도록 수정 — critical/high 레벨의 루트/홈 규칙과 이번 확장된 상위탈출/절대경로 규칙 양쪽 다 적용
- [x] #2 test_block_dangerous_commands.py에 -Rf/-r -f/--recursive --force 각각에 대한 positive 케이스 추가, 기존 정상 케이스(rm -rf ./dist 등) 회귀 테스트 유지
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RM_RF_FLAGS를 결합 소문자 단일 토큰 매칭에서, rm 뒤 플래그 클러스터를 스캔하는 두 개의 lookahead(재귀 계열/force 계열이 각각 어딘가에 존재하는지 대소문자 무시로 확인) + 클러스터 전체 소비 방식으로 재작성. find_violation에 re.IGNORECASE 적용. 이로써 rm -Rf, rm -r -f, rm --recursive --force가 critical(루트/홈) 및 high(상위탈출/절대경로, TASK-4에서 확장된 규칙) 양쪽에서 모두 탐지됨. CRITICAL_PATTERNS의 중복된 순서별 정규식 2개를 RM_RF_FLAGS 재사용 1개로 통합. rm -v/-i 같은 정상 사용은 여전히 미탐지 확인. 테스트: -Rf/-r -f/--recursive --force 각 critical+high 6개 positive 케이스, rm -v/-i regression 2개 추가. hooks/test_block_dangerous_commands.py 32/32 통과, 전체 hooks/ 스위트 428 passed / 3 failed(TASK-10 소관인 malformed-stdin 케이스, 무관).
<!-- SECTION:FINAL_SUMMARY:END -->
