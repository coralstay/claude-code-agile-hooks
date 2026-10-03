---
id: TASK-40
title: 'dedup_drift_guard: 설치본의 REGISTRY로 저장소를 검사해 REGISTRY 변경 커밋이 막히는 문제'
status: In Progress
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-03 12:58'
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
- [ ] #1 저장소의 REGISTRY 변경이 설치본 갱신 없이 커밋된다
- [ ] #2 저장소 REGISTRY를 읽을 수 없으면 지금처럼 설치본 REGISTRY로 검사한다
- [ ] #3 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->
