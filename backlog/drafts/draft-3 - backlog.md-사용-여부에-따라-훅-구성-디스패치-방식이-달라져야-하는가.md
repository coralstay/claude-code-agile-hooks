---
id: DRAFT-3
title: backlog.md 사용 여부에 따라 훅 구성/디스패치 방식이 달라져야 하는가
status: Draft
assignee: []
created_date: '2026-09-19 12:43'
updated_date: '2026-09-19 12:43'
labels: []
dependencies: []
documentation:
  - backlog/decisions/decision-3 - 라우터-dispatcher-훅-도입-안-함-—-완전-독립형-설계-유지.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-3에서 "이 저장소를 라우터로 재설계하지 않는다"는 결론을 내렸지만, 그건 "이 저장소 자체를 완전 독립형에서 공용 dispatcher로 바꿀지"에 대한 판단이었다. 이번 질문은 결이 다르다 — backlog.md를 쓰는 프로젝트에서는 5개 훅이 추가로 동작하고, 안 쓰는 프로젝트에서는 23개 범용 훅만 동작한다. 이 두 경우에 훅을 어떻게 조직화해야 하는지, 그리고 그 조직화 방식에 따라 라우터(또는 다른 디스패치 방식)가 필요해지는 지점이 있는지는 아직 따로 검토된 적이 없다. 아직 결론 없는 열린 질문이라 decision이 아니라 draft로 남긴다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog.md 미사용 프로젝트에서 5개 backlog 전용 훅이 조용히 통과(no-op)하는 지금 방식이 계속 최선인지, 아니면 애초에 등록조차 안 하는 편이 나은지 검토
- [ ] #2 라우터/디스패처가 실제로 필요해지는 조건을 구체화 — 예: 훅 개수가 더 늘어 프로젝트별로 등록/해제를 다르게 하고 싶어질 때
- [ ] #3 이 draft 자체는 promote하지 않고 사용자 검토 대기
<!-- AC:END -->
