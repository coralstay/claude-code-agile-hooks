---
id: DRAFT-11
title: 'backlog_commit_scope: 충돌 병합을 마무리하는 커밋(MERGE_HEAD)은 막지 않는다'
status: Draft
assignee: []
created_date: '2026-11-22T11:36:00Z'
labels:
  - hooks
  - merge
dependencies: []
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
