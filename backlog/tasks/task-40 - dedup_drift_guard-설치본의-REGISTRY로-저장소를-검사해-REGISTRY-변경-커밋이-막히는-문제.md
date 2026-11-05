---
id: TASK-40
title: 'dedup_drift_guard: 설치본의 REGISTRY로 저장소를 검사해 REGISTRY 변경 커밋이 막히는 문제'
status: Done
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-03 13:13'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-34
  - decision-2
  - decision-3
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-34에서 발생. 설치된 dedup_drift_guard.py는 자기 안의 REGISTRY로 저장소의 hooks/를 검사한다. 저장소 쪽 REGISTRY를 바꾸는 커밋(함수 사본을 빼거나 더하는 경우)은 설치본을 먼저 갱신하지 않으면 항상 막힌다. 실제로 사용자가 설치본을 손으로 갱신해야 커밋할 수 있었다. 검사 대상 저장소의 hooks/dedup_drift_guard.py에 REGISTRY가 있으면 그것을 읽어 쓰는 방식 등을 검토한다(완전 독립형 원칙과 충돌하지 않게, 데이터만 읽기).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 저장소의 REGISTRY 변경이 설치본 갱신 없이 커밋된다
- [x] #2 저장소 REGISTRY를 읽을 수 없으면 지금처럼 설치본 REGISTRY로 검사한다
- [x] #3 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
dedup_drift_guard.py가 검사 대상 저장소의 hooks/dedup_drift_guard.py에서 REGISTRY를 ast로 파싱해 마지막 최상위 REGISTRY = 리터럴만 literal_eval로 읽어 쓴다(저장소 코드를 import·실행하지 않음 — decision-3 유지). 파일 없음·문법 오류·리터럴 아님·형태 불일치면 설치본의 내장 REGISTRY로 대체. REGISTRY와 훅 파일 모두 작업 트리에서 읽어 일관성을 유지(auto_stage로 실제로는 인덱스와 같음). 비운 REGISTRY도 신뢰 — 드리프트 탐지기이지 보안 장치가 아님을 docstring·doc-2에 명시. 940 passed, 파일 커버리지 100%(__main__ 제외). AC #3 설치는 일괄 — 설치 전까지는 옛 설치본이 REGISTRY 항목 제거 커밋을 계속 막는다.
<!-- SECTION:FINAL_SUMMARY:END -->
