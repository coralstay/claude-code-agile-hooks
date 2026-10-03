---
id: TASK-29
title: backlog 드래프트→승격 단계 분리를 훅으로 강제한다
status: Done
assignee: []
created_date: '2026-09-26 03:34'
updated_date: '2026-10-03 08:01'
labels:
  - backlog
  - workflow
dependencies:
  - TASK-26
references:
  - decision-1
  - decision-3
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저가 2026-09-26에 명시한 작업 리듬을 훅으로 강제할 수 있는지 검토한다.

## 규칙

backlog에 새 작업을 올릴 때는 이 순서를 지키고 **각 단계를 별도 커밋으로** 남긴다.

1. `backlog draft create` + `draft edit`으로 카드를 채운다
2. 커밋 (드래프트 생성 자체를 이력에 남긴다)
3. `backlog draft promote <ID>`
4. 커밋 (승격을 이력에 남긴다)
5. 그 다음에 실제 구현을 시작한다

## 왜 훅이 필요한가

지금은 CLAUDE.md의 서술로만 존재해서 실제로 어겨졌다. 에이전트가 `backlog task create`로
드래프트를 건너뛰고 태스크를 바로 만들었고, 유저가 지적해 되돌렸다(태스크를 아카이브하고
드래프트로 다시 만든 사례). 드래프트를 경유하는 이유는
승격 전에 유저가 카드를 검토할 창을 만드는 것이고, 생성과 승격이 각각 독립 커밋으로 남아야
나중에 "언제 무엇이 태스크가 됐는지"를 이력에서 읽을 수 있다.

## 훅으로 강제할 수 있는 지점 (조사 대상)

**A. PreToolUse(Bash)에서 `backlog task create`를 차단한다.** 가장 직접적이다. 명령
문자열에 `backlog task create`가 있으면 거부하고 "드래프트를 경유하세요"로 안내한다.
기존 커맨드 매칭 훅들과 같은 방식이라 구현이 단순하다. 다만 DRAFT-2가 지적한 커맨드
문자열 매칭의 구조적 한계를 그대로 물려받는다(따옴표·변수·heredoc 우회).
예외가 필요한 경우가 있는지 먼저 확인해야 한다 — 예를 들어 이미 진행 중인 작업을
사후에 기록하는 경우.

**B. 커밋 시점에 스테이징 내용으로 단계 혼합을 차단한다.** 이쪽이 우회에 강하다.
- 스테이징에 `backlog/drafts/*.md` 신규 추가가 있으면서 그 밖의 파일도 있으면 거부
- 승격(= `backlog/drafts/` → `backlog/tasks/` 이름 변경)이 있으면서 다른 변경도 있으면 거부
  `git diff --cached --name-status -M`으로 R(rename) 항목을 보면 승격을 판별할 수 있다
- 즉 "드래프트 생성 커밋"과 "승격 커밋"은 각각 그것만 담아야 한다

**C. 둘 다 한다.** A가 실수를 조기에 막고, B가 우회를 막는다.

## 착수 전에 정할 것

- B를 어느 레이어에 둘지. claude-rails 훅은 Claude Code의 PreToolUse/Stop 계열이라 git 훅
  (pre-commit 등)과 레이어가 다르다. 결정(2026-10-03): 이 저장소의 다른 커밋 검사
  (pre_commit_check.py)와 같이 PreToolUse(Bash)에서 `git commit`을 가로채 판정한다 —
  Claude Code 세션의 커밋에만 적용되고, 사람이 터미널에서 직접 하는 커밋은 범위 밖이다.
- backlog을 쓰지 않는 저장소에서는 이 검사가 조용히 통과해야 한다(DRAFT-3과 연결).
- 사람이 직접 `git commit`하는 경우에도 적용할지, Claude Code 세션에만 적용할지.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog 프로젝트에서 PreToolUse(Bash)가 'backlog task create'를 차단하고 'backlog draft create'를 안내한다 (A)
- [x] #2 git commit 시 스테이징에 새 드래프트(backlog/drafts/ 신규 추가)와 그 밖의 파일이 섞여 있으면 차단한다 (B)
- [x] #3 git commit 시 스테이징에 승격(backlog/drafts/ → backlog/tasks/ rename)과 그 밖의 파일이 섞여 있으면 차단한다 (B) — 승격된 태스크 파일 자체의 수정(--add-ref 등)은 허용
- [x] #4 backlog를 쓰지 않는 저장소에서는 조용히 통과한다
- [x] #5 테스트를 추가하고 전체 스위트가 통과하며, settings.hooks.json·README 훅 표·설치된 사본에 반영한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
훅 2개 추가. require_draft_first.py(PreToolUse Bash, if 필터 없음): backlog 프로젝트에서 실제 명령 위치의 'backlog task create'를 차단하고 draft create → 승인 후 promote를 안내한다. 따옴표 인자·heredoc 안의 같은 글자는 통과. backlog_commit_scope.py(PreToolUse Bash, if: Bash(git *)): git commit 시 스테이징(-z, rename 감지)을 보고 드래프트 신규 추가+그 밖의 파일, 승격(drafts→tasks)+backlog/tasks 밖의 파일이 섞이면 차단. 같은 명령의 git add / commit -a는 임시 인덱스(GIT_INDEX_FILE)로 재현해 판정하고 실제 인덱스는 건드리지 않는다. 미커버: git rm/mv 혼합, pathspec 커밋, bash -c/별칭, Claude Code 밖 커밋. 공용 헬퍼는 dedup REGISTRY에 등록. settings.hooks.json·README(훅 30개)·doc-2·CLAUDE.md.snippet(태스크 생성 단계를 draft 흐름으로) 반영. uvx pytest 532 passed. AC #5의 설치본 부분은 마지막 일괄 설치 때 체크.
<!-- SECTION:FINAL_SUMMARY:END -->
