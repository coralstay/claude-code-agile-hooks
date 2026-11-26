---
id: DRAFT-11
title: 워크플로 안내문에 저장소별 담당 규칙 한 줄 — Claude 담당이 아닌 저장소는 편집하지 않는다
status: Draft
assignee: []
created_date: '2026-11-26T08:22:00Z'
labels:
  - workflow
  - agents
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 결정(2026-11-22): 저장소를 에이전트별로 나눠 갖는다(Claude · Antigravity · 다른 Claude 세션). 담당 기록 SSOT 는 dev-toolchain workspace/repos.tsv 의 담당 열이고, 조회 명령은 dev-toolchain workspace owner <경로>(dev-toolchain TASK-179, PR #6 병합).
Claude 가 매 세션 받는 안내문(hooks/workflow_guide.md, TASK-76)에 이 규칙이 없어, 다른 에이전트 저장소를 실수로 고칠 수 있다.
계획: ~/.claude/plans/agent-repo-split-record.md (승인됨, 2번 항목)

## 범위
- hooks/workflow_guide.md 에 한 줄: 저장소마다 담당 에이전트가 있다(dev-toolchain workspace owner <경로>). Claude 담당(claude)이 아닌 저장소는 편집 · 커밋하지 않고 읽기 · 보고만 한다. unknown 이면 유저에게 묻는다
- README 에 같은 규칙(안내문 규칙은 모두 README 에 있어야 한다 — TASK-76 B1 대조 테스트)

## 비즈니스 규칙
- B1 (AC #1) 안내문은 담당 표를 복사하지 않고 명령만 가리킨다(SSOT 는 repos.tsv)
- B2 (AC #1) 안내문은 30줄 상한을 지킨다(TASK-76 B4)

## 하지 않는 것
훅으로 다른 담당 저장소 편집을 막기(안내만), Antigravity 쪽 규칙(upkeep 카드)
<!-- SECTION:DESCRIPTION:END -->
