---
id: TASK-56
title: 테스트 먼저(AC 단위 TDD + 비즈니스 규칙)를 훅으로 강제
status: To Do
assignee: []
created_date: '2026-10-11 08:33'
labels:
  - feature
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정(2026-10-11): 테스트 먼저 = AC 하나씩 TDD, 테스트는 비즈니스 규칙도 다룬다(카드의 ## 비즈니스 규칙 절, - B<k> (AC #<n>) …). 새 훅 require_test_first.py가 강제한다. 최상위 Sigkill Foundry RAIL-019 · ADR-020. 계획: ~/.claude/plans/typed-chasing-conway.md

수용 기준(승격 시 AC로 등록):
1. opt-in(testFirst.sourceGlobs · testGlobs)일 때 PreToolUse Edit|Write: 소스 편집 전에 체크 안 된 첫 AC n의 표식 <ID>#<n>과 관련 규칙 <ID>#B<k> 표식이 테스트에 있어야 한다
2. PreToolUse Bash: backlog task edit … -s Done 전에 모든 AC · 규칙 표식이 테스트에 있어야 한다
3. 규칙 절 없음 → AC만, 형식 오류 → 안내와 함께 차단, AC 전부 체크 → 허용, 비대상은 통과
4. settings.hooks.json · README · doc-2 · design 3.01(33개) · CLAUDE.md.snippet · backlog decision에 반영
5. 테스트 통과 · 커버리지 100%
<!-- SECTION:DESCRIPTION:END -->
