---
id: TASK-77
title: 'backlog_commit_scope: 충돌 병합을 마무리하는 커밋(MERGE_HEAD)은 막지 않는다'
status: To Do
assignee: []
created_date: '2026-11-22T11:36:00Z'
updated_date: '2026-11-22T11:41:00Z'
labels:
  - hooks
  - merge
dependencies: []
references:
  - TASK-75
documentation:
  - /Users/flynn_macpro/.claude/plans/agile-hooks-merge-commit-scope.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
source-header TASK-42(미병합 브랜치 정리)에서 task/TASK-20 병합의 work-order.md 충돌을 풀고 git commit 으로 마무리하려 하자 backlog_commit_scope 가 '상태 전환 커밋에 다른 변경이 섞였다'며 막았다(TASK-3·16 → Done, TASK-17~22 archive 가 병합으로 함께 스테이징). 그 변경들은 원래 브랜치에서 이미 한 커밋씩 이 훅을 통과했다. 충돌 없는 병합은 git 이 직접 커밋해 훅이 보지 못하므로(TASK-25 병합 통과) 충돌 있는 병합만 막히는 우연한 기준이다. upkeep TASK-8(task/TASK-1, work-order.md add/add 충돌)도 같다.
유저 결정(2026-11-22): 훅을 고친다(A안), cherry-pick 으로 다시 쌓지 않는다.
계획: ~/.claude/plans/agile-hooks-merge-commit-scope.md (승인됨)

## 비즈니스 규칙
- B1 (AC #1) 병합 진행 중(대상 저장소에 MERGE_HEAD)인 커밋은 규칙 1~5로 막지 않는다
- B2 (AC #2) 병합 중이 아니면 기존 규칙 그대로(회귀 없음)
- B3 (AC #2) MERGE_HEAD 확인이 실패하면 검사한다(조용히 통과하지 않음)

## 하지 않는 것
cherry-pick·revert·rebase 진행 중 예외, 다른 훅의 병합 처리
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 충돌 병합을 마무리하는 git commit(상태 전환 + 다른 변경이 섞인 스테이징)이 대상 저장소에 MERGE_HEAD 가 있으면 통과한다. 실제 git 저장소에서 충돌 병합을 만들어 재현하는 테스트가 있다(B1)
- [ ] #2 병합 중이 아니면 같은 스테이징이 지금처럼 거부되고, MERGE_HEAD 확인이 실패하면 기존 검사로 이어진다(B2·B3)
- [ ] #3 README 에 예외와 이유(병합되는 커밋은 각 브랜치에서 이미 검사됨)가 있고 coverageCommand 100%·source-header lint 0 이다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 출력을 Notes 에 첨부
- [ ] #2 [수동 검증] 설치 후 source-header TASK-42 에서 task/TASK-20 병합 마무리 커밋이 실제로 통과함을 확인
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저(2026-11-22)가 정리 카드(source-header TASK-42, upkeep TASK-8)의 병합을 막는 훅을 고치기로 했다(A안). 계획: ~/.claude/plans/agile-hooks-merge-commit-scope.md

### Objective
- backlog_commit_scope.py 는 git commit 때 git diff --cached --name-status -M -z 로 스테이징을 읽어 규칙 1~5(draft 생성·승격·2장 이상·상태 전환·작업 순서 커밋 단독)를 검사한다. 대상 저장소는 TASK-75 의 command_target_dir·project_root 로 정한다.
- 충돌 없는 git merge 는 git 이 직접 커밋해 훅이 보지 않는다. 충돌 병합 마무리 git commit 만 검사된다.
- 실패 사례: source-header task/TASK-42 에서 task/TASK-20 병합(work-order.md 충돌) 마무리 커밋이 규칙 4 로 거부.

### Assessment
대상 저장소에 MERGE_HEAD 가 있으면 병합 마무리로 보고 규칙을 건너뛴다. 병합되는 커밋은 각 브랜치에서 이미 검사됐다. 확인 실패는 검사 쪽으로 기운다.

### Plan
1. 테스트 먼저: 임시 git 저장소에서 상태 전환 + 다른 변경이 섞인 충돌 병합을 만들어 마무리 커밋이 통과(#1·#B1), 병합 아님 → 거부, MERGE_HEAD 확인 실패 → 검사(#2·#B2·#B3) — 실패 확인.
2. backlog_commit_scope.py 에 merge_in_progress(root) 추가·main 분기, 표식·노트.
3. README, coverageCommand 100%, lint.
4. 유저 설치 → TASK-42 재시도로 실전 확인 → Done → PR.
<!-- SECTION:PLAN:END -->
