---
id: DRAFT-4
title: 훅이 계속 늘어날 때 hooks/ 디렉토리를 어떻게 정리할 것인가
status: Draft
assignee: []
created_date: '2026-09-19 12:43'
updated_date: '2026-09-19 12:43'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
지금 28개 훅이 hooks/ 밑에 전부 flat하게 있다. README 8장/doc-2가 이벤트별 분류표로 어느 정도 보완하고 있지만, 실제 디렉토리 구조 자체는 그대로다. 앞으로 해야 할 일로 기록해두는 열린 질문.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 카테고리별 서브디렉토리(예: hooks/backlog/, hooks/security/, hooks/observability/) 도입이 완전 독립형 원칙(decision-3)과 충돌하는지 검토 — 디렉토리 구조만 바뀌고 import 관계는 그대로면 원칙 위반이 아니라는 논리 정리
- [ ] #2 install.sh/settings.hooks.json의 경로 참조가 얼마나 바뀌어야 하는지 파악
- [ ] #3 이 draft도 promote하지 않고 사용자 검토 대기
<!-- AC:END -->
