---
id: TASK-67
title: pre_commit_check의 fail-closed 테스트 타임아웃을 저장소로 회수하고, 설치본 · 저장소를 다시 맞춘다
status: To Do
assignee: []
created_date: '2026-10-29T12:17:00Z'
updated_date: '2026-11-06T04:39:00Z'
labels:
  - hooks
dependencies:
  - TASK-75
documentation:
  - >-
    https://github.com/coralstay/coralstay-software-factory/tree/task/task-19/design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정 · 발견(2026-10-29): 설치본(~/.claude/hooks/claude-code-agile-hooks)에만 있던 pre_commit_check의 fail-closed 테스트 타임아웃(`testTimeoutSeconds` · `CC_AGILE_TEST_TIMEOUT`)을 저장소로 회수한다. 지금 settings.json의 pre_commit_check 항목에는 timeout이 없어(기본 600초) 내부 제한보다 Claude Code가 먼저 취소하고 커밋이 그냥 진행된다(fail-open).

분리(2026-11-06, 유저 결정): 원래 이 카드에 있던 '대상 저장소 판정'(project_root · command_target_dir, pre_commit · pre_push · backlog 게이트 · Edit/Write가 세션 cwd가 아니라 대상 저장소로 판정, 모르면 거부)은 TASK-75로 옮겼다. 원래 AC #1 · #2 · #4 · #5 · #6 · #9와 규칙 B1 · B2 · B4~B7이 그쪽으로 갔다. 이 카드에는 타임아웃 회수와 설치본 정합만 남는다.

주의: 회수 원본은 ~/.cache/claude-hook-patch/new/claude-code-agile-hooks(2026-10-25 스냅숏)와 ~/.cache/claude-hook-patch/fail-closed.patch다. 스냅숏은 TASK-59 ~ 63 · 72 · 74 이전 기준이라 파일째 덮으면 안 되고, 타임아웃 hunk(TIMEOUT_ENV · commit_test_timeout · _kill_group · run_shell_with_timeout)만 main 위에 옮긴다. 설치본에는 고아 test_project_root.py(10-24)가 남아 있다.

이 카드는 최상위 coralstay-software-factory TASK-19의 결정을 구현한다. 커밋 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다.

## 비즈니스 규칙
- B1 (AC #1) testCommand가 제한 시간 안에 끝나지 않으면 커밋을 거부한다(fail-closed), 제한 시간은 환경변수 > 프로젝트 설정 > 기본값 1500초 순이다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 fail-closed 테스트 타임아웃 회수: CC_AGILE_TEST_TIMEOUT > testTimeoutSeconds > 기본 1500초, 시간 초과면 프로세스 그룹을 끝내고 커밋을 거부한다. settings.hooks.json의 pre_commit_check 항목에 timeout 1800을 넣는다
- [ ] #2 [수동 검증] 이 카드 · TASK-75 반영 뒤 install.sh로 재설치하면 설치본과 저장소 hooks/*.py의 diff가 없고, 설치본의 고아 test_project_root.py는 저장소 것과 같거나(TASK-75가 만든 경우) 지워진다
- [ ] #3 [수동 검증] 유저가 ~/.claude/settings.json의 pre_commit_check 항목에 timeout 1800을 넣는다 — config_guard 대상이라 유저 조치
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 바뀐 훅이 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트와 맞는다
- [ ] #3 [수동 검증] README · CLAUDE.md.snippet 반영(testTimeoutSeconds · CC_AGILE_TEST_TIMEOUT · settings timeout 1800)
- [ ] #4 [수동 검증] 각 커밋에 TASK ID와 본문 'Refs: coralstay-software-factory TASK-19', push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-10-29 설치본에서만 고친 테스트 타임아웃을 저장소로 되돌려 놓으라고 했다. 2026-11-06 대상 저장소 판정 부분을 TASK-75로 나눴다.

### Objective
- 저장소 hooks/pre_commit_check.py는 testCommand를 subprocess.run(shell=True)로 제한 없이 돌린다(run_shell). Claude Code의 훅 기본 타임아웃(600초)이 먼저 걸리면 훅이 취소되고 커밋이 진행된다(fail-open).
- 회수 원본 ~/.cache/claude-hook-patch/new/claude-code-agile-hooks(2026-10-25)의 pre_commit_check에 TIMEOUT_ENV · commit_test_timeout · _kill_group · run_shell_with_timeout이 있고, fail-closed.patch(300줄)는 pre_commit_check.py · test_pre_commit_check.py만 고친다. 스냅숏은 TASK-59~63 · 72 · 74 이전이다.
- settings.hooks.json의 pre_commit_check 항목에 timeout이 없다. ~/.claude/settings.json은 config_guard 대상이라 유저가 고친다.
- 설치본에 고아 test_project_root.py가 있다.

### Assessment
타임아웃 hunk만 함수 단위로 main 위에 옮기고, 회수 원본과 함수 AST가 같은지 확인한다(이 부분은 그 뒤 바뀐 적이 없다). 제한 시간 초과는 프로세스 그룹째 끝내고 거부한다. 훅 등록 timeout(1800)이 내부 제한(1500)보다 커야 fail-closed가 성립한다. 설치본 정합은 TASK-75까지 반영한 뒤 한 번에 맞춘다.

### Plan
1. 회수 원본에서 타임아웃 hunk를 추출해 회수 목록을 노트에 적는다.
2. AC #1: 타임아웃 테스트 먼저(환경변수 > 설정 > 기본값, 초과 시 거부 · 프로세스 그룹 종료) → 구현, settings.hooks.json에 timeout 1800.
3. README · snippet, coverageCommand 100%.
4. TASK-75 반영 뒤 유저가 install.sh 재설치 · settings.json timeout → 설치본 diff 확인(AC #2 · #3).
<!-- SECTION:PLAN:END -->
