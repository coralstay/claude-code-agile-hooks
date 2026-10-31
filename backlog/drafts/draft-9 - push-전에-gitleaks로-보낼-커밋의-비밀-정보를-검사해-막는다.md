---
id: DRAFT-9
title: push 전에 gitleaks로 보낼 커밋의 비밀 정보를 검사해 막는다
status: Draft
assignee: []
created_date: '2026-10-30T16:55:00Z'
updated_date: '2026-10-30T16:55:00Z'
labels:
  - hooks
  - security
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 지시(2026-10-31): push 전 gitleaks 검증을 훅으로 강제한다. 계기: agent-orchestrator를 공개로 전환하기 전에 gitleaks로 전체 이력을 손으로 검사했다(발견 0). 네 저장소가 모두 공개(AGPL)가 됐으므로, 비밀 정보가 섞인 커밋은 push되는 순간 회수할 수 없다 — push 전에 막아야 한다.

현황: 이 저장소의 push 게이트는 pre_push_check(태스크 Done · final summary)와 pre_push_coverage_check(커버리지)뿐이고 비밀 정보 검사는 없다. protect_secrets.py는 파일 읽기 · 쓰기 경로를 막는 훅이라 커밋 내용은 보지 않는다. 로컬에 gitleaks 8.30.1이 있다(~/.local/bin/gitleaks).

한계(알고 시작한다): Claude Code 훅이라 Antigravity · 터미널 직접 push에는 걸리지 않는다. 도구와 무관한 강제는 CI(gitleaks 액션) + main 보호 규칙의 필수 상태 검사로 따로 한다.

## 비즈니스 규칙
- B1 (AC #1) 검사 범위는 이번 push로 원격에 새로 올라가는 커밋 전부다(원격에 이미 있는 커밋은 다시 보지 않는다). 원격에 없는 새 브랜치면 원격의 어떤 ref에도 없는 커밋 전부다.
- B2 (AC #2) 발견이 하나라도 있으면 push를 막고, 비밀 값은 메시지에 원문으로 쓰지 않는다(파일 · 줄 · 규칙 ID만).
- B3 (AC #3) gitleaks가 없거나 실행에 실패하면 통과시키지 않고 막는다 — 검사를 못 한 것을 통과로 치지 않는다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 git push 명령이면 이번 push로 새로 올라가는 커밋 범위를 계산해 그 범위만 gitleaks로 검사한다
- [ ] #2 발견이 있으면 push를 거부하고 파일 · 줄 · 규칙 ID만 안내한다(값은 가린다)
- [ ] #3 gitleaks가 없거나 실행이 실패하면 설치 · 확인 안내와 함께 거부한다
- [ ] #4 명령의 대상 저장소(git -C · cd 체인)를 기준으로 판정한다(세션 cwd가 아니라)
- [ ] #5 settings.hooks.json에 등록하고 README · CLAUDE.md.snippet에 동작 · 허용 목록(.gitleaks.toml) · 한계를 적는다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 테스트 통과 로그를 final summary에 남긴다 (수동)
- [ ] #2 커버리지 100% (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저(2026-10-31): push 전 gitleaks 검증을 훅으로 강제한다. 이 저장소(Claude 훅)에 draft만 등록한다.

### Objective
- 기존 push 훅: pre_push_check.py · pre_push_coverage_check.py(PreToolUse Bash, git push 명령 감지). 명령 해석은 decision-1(basename 정규화까지)의 한계를 따른다.
- 세션 cwd로 저장소를 판정하는 결함(TASK-67)이 push 훅에도 있다 — 새 훅은 명령의 대상 저장소(git -C · cd 체인)를 보도록 TASK-67의 해석 함수를 재사용해야 한다.
- gitleaks 8.x: 'gitleaks git --log-opts=<rev-range> --redact --no-banner --exit-code 1 --report-format json --report-path -'로 범위만 검사할 수 있다.

### Assessment
새 독립 훅(decision-3) pre_push_secret_scan.py로 둔다. push 대상 ref를 명령에서 풀고, 원격 추적 ref와 비교해 새 커밋 범위를 만든 뒤 그 범위만 gitleaks로 검사한다. 비밀 값은 --redact로 가린다. 저장소 루트의 .gitleaks.toml(허용 목록)이 있으면 gitleaks가 그대로 읽는다.

### Plan
1. AC마다 테스트 먼저(<ID>#n · #B<k> 표식) → 구현 → 커밋.
2. settings.hooks.json 등록 · dedup REGISTRY · 등록 계약 테스트.
3. README · CLAUDE.md.snippet에 동작과 한계(Claude 세션 전용, CI로 보완) 반영.
<!-- SECTION:PLAN:END -->
