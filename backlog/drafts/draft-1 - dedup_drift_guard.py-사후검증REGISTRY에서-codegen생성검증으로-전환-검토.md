---
id: DRAFT-1
title: 'dedup_drift_guard.py: 사후검증(REGISTRY)에서 codegen(생성+검증)으로 전환 검토'
status: Draft
assignee: []
created_date: '2026-09-19 04:31'
updated_date: '2026-09-19 04:31'
labels: []
dependencies: []
documentation:
  - >-
    backlog/decisions/decision-2 -
    복붙-함수-drift는-REGISTRY-사후검증으로-—-codegen-전환은-보류.md
  - hooks/dedup_drift_guard.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-2에서 "REGISTRY 확장으로 유지, codegen 전환은 보류"라고 판단 보류한 항목. Kubernetes의 hack/update-codegen.sh + hack/verify-codegen.sh 패턴(하나의 소스에서 N개 파일 생성 -> CI가 재생성 후 diff로 검증)을 리서치로 확보해뒀다. dedup_drift_guard.py는 지금 "사후 검증"만 하고 "애초에 손으로 복붙 못 하게" 막는 건 아니다 — 이 draft는 그 전환이 실제로 가치 있는지, 있다면 어떻게 설계할지 탐색한다. 아직 할지 말지도 정해지지 않은 탐색 단계라 draft로 남기고 promote하지 않는다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 REGISTRY 등록 함수 5개를 하나의 소스에서 생성하는 방식으로 바꿨을 때 무엇이 소스가 되어야 하는지(예: hooks/_shared/dedup_sources.py 같은 비-훅 소스 파일) 설계안 작성
- [ ] #2 생성 스크립트(hack/update-hooks.py 등)와 검증 스크립트(기존 dedup_drift_guard.py 재사용 여부 포함) 설계안 작성
- [ ] #3 이 전환이 완전 독립형 훅 설계 원칙(decision-3)과 충돌하지 않는지 — 생성된 파일은 런타임에는 여전히 완전 독립형이라는 논리를 정리
- [ ] #4 이 draft 자체는 promote하지 않고 사용자 검토 후 필요하면 별도 승격
<!-- AC:END -->
