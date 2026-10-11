---
id: TASK-56
title: 테스트 먼저(AC 단위 TDD + 비즈니스 규칙)를 훅으로 강제
status: Done
assignee: []
created_date: '2026-10-11 08:33'
updated_date: '2026-10-11 08:47'
labels:
  - feature
dependencies: []
references:
  - decision-12
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

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 opt-in(testFirst.sourceGlobs · testGlobs)일 때 PreToolUse Edit|Write: 소스 편집 전에 체크 안 된 첫 AC n의 표식 <ID>#<n>과 관련 규칙 <ID>#B<k> 표식이 테스트에 있어야 한다
- [x] #2 PreToolUse Bash: backlog task edit … -s Done 전에 모든 AC · 규칙 표식이 테스트에 있어야 한다
- [x] #3 규칙 절 없음 → AC만, 형식 오류 → 안내와 함께 차단, AC 전부 체크 → 허용, 비대상은 통과
- [x] #4 settings.hooks.json · README · doc-2 · design 3.01(33개) · CLAUDE.md.snippet · backlog decision에 반영
- [x] #5 테스트 통과 · 커버리지 100%
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
새 훅 require_test_first.py(성격 ① 절차 강제, backlog 전용, opt-in)로 테스트 먼저(AC 단위 TDD + 비즈니스 규칙)를 강제한다.
- 조건: backlog.md 프로젝트 · 설정의 testFirst(sourceGlobs·testGlobs) · task/<ID> 브랜치 · 그 태스크 In Progress. 아니면 통과.
- PreToolUse Edit|Write: sourceGlobs에 맞고 testGlobs에 안 맞는 파일 편집 전에, 체크 안 된 첫 AC n의 <ID>#<n>과 관련 AC가 n인 규칙 <ID>#B<k> 표식이 testGlobs 파일에 있어야 함(앞 [A-Za-z0-9-]·뒤 숫자 경계). AC 전부 체크면 허용.
- PreToolUse Bash: 명령 위치의 backlog task edit <ID> ... -s/--status Done(브랜치 태스크, AO-27·ao-27·27)이면 모든 AC·규칙 표식 필요.
- 카드의 ## 비즈니스 규칙 절: - B<k> (AC #<n>) <규칙>. 없으면 AC만, 형식 오류·없는 AC 참조는 형식 안내와 함께 차단. testFirst 형식 오류는 태스크 브랜치에서 차단(설정 파일 편집은 허용).
- 글롭: ** = / 포함, **/ = 0단계 이상 디렉토리, * = / 제외, ? = 한 글자, 그 밖은 글자 그대로.
- 등록: settings.hooks.json PreToolUse Edit|Write · Bash(if 없음), 등록 계약 CONTRACT, dedup REGISTRY 8개 헬퍼.
- 문서: README, doc-2, design 3.01(33개, ①9, XP·TDD, RAIL-019, 다이어그램 52건), CLAUDE.md.snippet, decision-12.
- 검증: 테스트 1812 통과, 커버리지 100%.
- 한계: Bash로 쓴 소스, 실제 빨강 여부, 표식 문자열 외 매칭은 보지 않음. AC 없는 카드는 요구 없음. 설치는 유저가 install.sh 실행.
<!-- SECTION:FINAL_SUMMARY:END -->
