---
id: TASK-68
title: >-
  착수 검사(계획 승인 · 형식 · 작업 순서)를 task 브랜치 생성 · 전환 때도 걸고, Edit/Write 게이트가 현재 task 브랜치
  카드의 In Progress를 확인하게 한다
status: To Do
assignee: []
created_date: '2026-10-29T12:20:00Z'
updated_date: '2026-10-29T23:50:00Z'
labels:
  - hooks
dependencies:
  - TASK-67
references:
  - decision-14
documentation:
  - >-
    https://github.com/coralstay/coralstay-software-factory/tree/task/task-19/design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정(2026-10-29, 최상위 TASK-19 A1 수정 · A2 · A5): '착수'는 main에 병합되지 않은 `task/<ID>` 브랜치가 있는 상태다. 착수 검사 세 가지 — 계획 승인(사람 키로 서명한 `Plan-Approved: <ID>` 커밋, 서명자가 `humanSigners`에 있음), 계획 · AC · DoD 형식(RAIL-020), 작업 순서 파일 최신 여부(RAIL-023) — 를 두 시점에 모두 한다. (a) Claude의 Bash가 `task/<ID>` 브랜치를 만들거나 그 브랜치로 전환할 때. (b) `backlog task edit <ID> -s "In Progress"` 때. (b)를 남기는 이유: agent-orchestrator는 자기 Java 프로세스에서 `git worktree add`로 브랜치를 만들어 훅이 그 시점을 보지 못한다. 대신 에이전트 세션의 In Progress 전환은 훅을 거친다. 검사는 훅이 설치된 경우에만 적용된다. 사람이 터미널에서 직접 한 일은 검사 대상이 아니다.

A2: Edit/Write 게이트 require_active_task는 지금 저장소 안 어느 카드든 In Progress면 통과한다. README · CLAUDE.md.snippet은 'In Progress 상태와 브랜치명을 확인한다'고 적고 있다. 이 둘을 맞춘다. 현재 `task/<ID>` 브랜치의 카드가 In Progress여야 통과한다.

브랜치 생성 · 전환으로 치는 명령(유저 결정 2026-10-30, 화이트리스트 — '단순히 생각해'): 대상이 `task/<ID>`인 `git switch`(`-c/-C` 포함)와 `git checkout`(`-b/-B` 포함)만. 그 밖의 명령(`git branch`, `git worktree add`, 경로 checkout `git checkout X -- path`, `fetch x:task/X`, `bash -c` 간접 실행 등)은 잡지 않는다 — 그 경로로 시작한 작업도 `-s "In Progress"` 시점 검사(AC #4)가 받친다. 이미 main에 병합된 task 브랜치로의 전환은 검사하지 않는다.

선행: DRAFT-8(대상 저장소 해석 · project_root — `cd <dir> && git switch`, 워크트리). TASK-64가 require_work_order의 트리거를 넓히므로 같은 파일에서 충돌한다. 먼저 끝나는 쪽 위에 쌓는다. 새 결정 decision-16이 decision-14의 '검사 시점'을 확장한다. 이 저장소의 `.claude-code-agile-hooks.json`에는 `humanSigners`가 없다. 그래서 지금도 이 저장소의 In Progress 전환은 전부 막힌다. 유저가 자기 principal을 넣어야 한다. 이 카드는 최상위 coralstay-software-factory TASK-19의 결정을 구현한다. 커밋 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다. H2 완료 뒤 유저의 ~/.claude/CLAUDE.md에 있는 같은 문구('훅이 In Progress 상태와 브랜치명을 확인한다')를 고치자고 제안만 한다(직접 고치지 않는다).

## 비즈니스 규칙
- B1 (AC #1) 사람이 서명한 Plan-Approved 승인 커밋이 없으면 `git switch -c task/X`(및 화이트리스트의 switch · checkout)를 거부한다
- B2 (AC #1) 승인 커밋 서명이 유효해도(%G? = G) 서명자(%GS)가 humanSigners에 없으면 거부한다
- B3 (AC #1) 카드에 SOAP 계획 · AC · DoD 중 하나라도 없으면 거부한다
- B4 (AC #1) task/ 가 아닌 브랜치의 생성 · 전환과, 이미 main에 병합된 task 브랜치로의 전환은 검사하지 않는다
- B5 (AC #2) 승인 커밋은 HEAD가 아니라 새 브랜치의 시작점에서 닿는 범위에서 찾는다 — HEAD가 승인 커밋 없는 다른 브랜치여도 `git switch -c task/X main`은 main에 승인 커밋이 있으면 통과한다
- B6 (AC #3) 작업 순서 파일(backlog/work-order.md)이 없거나 낡았으면 브랜치 생성 · 전환을 거부한다
- B7 (AC #4) `-s "In Progress"` 전환도 같은 세 검사를 한다
- B8 (AC #5) task/<ID> 브랜치에서는 그 카드가 In Progress일 때만 Edit/Write를 허용한다 — 다른 카드가 In Progress여도 거부한다
- B9 (AC #6) task 브랜치가 아닌 곳에서 프로젝트 안 파일의 Edit/Write는 거부한다. rebase가 진행 중이면 rebase 대상 브랜치로 판정한다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 브랜치 시점 검사: Claude의 Bash가 화이트리스트 명령 — 대상이 task/<ID>인 git switch(-c/-C 포함) · git checkout(-b/-B 포함) — 으로 미병합 task/<ID> 브랜치를 만들거나 전환하면, 대상 저장소(DRAFT-8 command_target_dir)에서 계획 승인과 계획 · AC · DoD 형식(RAIL-020)을 검사하고 없으면 거부한다. git branch · git worktree add 등 목록 밖 명령은 검사하지 않는다
- [ ] #2 승인 커밋은 새 브랜치의 시작점(명시 인자 → 없으면 대상 저장소 HEAD, 기존 브랜치면 그 tip, 원격만 있으면 origin/task/X)에서 닿는 범위에서 찾는다
- [ ] #3 작업 순서 파일 최신 여부(RAIL-023)도 브랜치 생성 · 전환 시점에 검사한다(require_work_order)
- [ ] #4 backlog task edit <ID> -s "In Progress" 시점의 세 검사(승인 · 형식 · 작업 순서)는 그대로 유지한다 — 오케스트레이터가 훅 밖에서 git worktree add로 만든 브랜치를 위해
- [ ] #5 require_active_task: 현재 브랜치가 task/<ID>면 그 카드가 In Progress일 때만 Edit/Write를 통과시킨다(다른 카드의 In Progress로는 통과하지 않는다)
- [ ] #6 require_active_task: task 브랜치가 아닌 곳에서는 프로젝트 안 파일의 Edit/Write를 task/<ID> 전환 안내와 함께 거부한다. rebase 중이면 rebase 대상 브랜치로 판정한다. 프로젝트 밖 경로는 지금처럼 통과한다
- [ ] #7 decision-16 작성: 착수 = 미병합 task/<ID> 브랜치, 착수 검사 두 시점, 브랜치 명령 목록, 사람의 터미널 작업은 대상 아님 — decision-14의 검사 시점을 확장한다(카드에 --add-ref decision-16)
- [ ] #8 브랜치 명령 파싱 함수(branch_start_targets)와 미병합 판정을 dedup REGISTRY 공유 함수로 등록한다. 새 훅 파일을 만들면 settings.hooks.json · REGISTRY · test_dedup_registry MODULES · test_hook_registration_contract CONTRACT/UNFILTERED 4곳에 등록한다
- [ ] #9 이 저장소 .claude-code-agile-hooks.json에 humanSigners(유저의 SSH/GPG principal)를 넣는다 — principal은 유저가 정하는 유저 조치 (수동)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 바뀐 훅이 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트와 맞는다
- [ ] #3 README · CLAUDE.md.snippet의 착수 · Edit/Write 게이트 설명을 실제 동작과 맞춘다 (수동)
- [ ] #4 임시 저장소에서 승인 없음 → 거부, 승인 뒤 → 통과, 낡은 작업 순서 → 거부를 실제로 재현한 로그를 final summary에 남긴다 (수동)
- [ ] #5 유저 ~/.claude/CLAUDE.md의 '훅이 In Progress 상태와 브랜치명을 확인한다' 문구 수정을 유저에게 제안한다 (수동)
- [ ] #6 각 커밋에 TASK ID와 본문 'Refs: coralstay-software-factory TASK-19', push 전 Done + final summary (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-10-29 착수 판단을 '미병합 task/<ID> 브랜치가 있음'으로 정했다(A2). 그래서 승인 없이 브랜치만 만들어도 착수가 되지 않도록 착수 검사를 브랜치 생성 · 전환 시점으로 옮기라고 했다(A1 수정, A5). 오케스트레이터가 훅 밖에서 브랜치를 만드는 경우가 있어 In Progress 시점 검사도 남기라고 했다(A1 보완). 또 Edit/Write 게이트가 문서 설명처럼 현재 브랜치 카드를 보게 하라고 했다(A2).

### Objective
- require_implementation_plan.py:229-241 segment_gate는 `draft promote`(형식 검사)와 `task edit -s "In Progress"`(형식 + 승인)만 잡는다. git 브랜치 명령(화이트리스트 switch · checkout)은 보지 않는다.
- require_implementation_plan.py:358-381 approval_status는 `git log --format=%H %s HEAD`(L365)로 HEAD에서 닿는 커밋만 찾는다. 브랜치를 만드는 순간 HEAD는 아직 이전 브랜치다.
- require_implementation_plan.py:459-476 check_card는 kind == "start"일 때만 approval_problem을 더한다. humanSigners는 human_signers(L125-147)가 프로젝트 설정에서 읽는다.
- require_work_order.py:137-183 command_starts_stage는 `draft promote`와 `-s "In Progress"`만 감지한다. main(L311-344)은 작업 트리의 태스크 파일로 해시를 비교한다.
- require_active_task.py:29-36 has_active_task가 `backlog task list --status "In Progress"`의 결과가 비었는지만 본다. 브랜치는 보지 않는다(L74-78 거부 문구). README.md:116 'In Progress 태스크 없으면 차단', CLAUDE.md.snippet:53-54 'In Progress 상태와 브랜치명을 확인한다'.
- git 명령 위치 파싱은 pre_commit_check.git_subcommand_index · command_runs_git(pre_commit_check.py:105-142, REGISTRY 공유)에 있다. 기준 브랜치 목록은 require_design_propagation.base_refs(L370-384)에 있다.
- 이 저장소 .claude-code-agile-hooks.json에는 testCommand · coverageCommand만 있고 humanSigners가 없다 → README.md:345대로 In Progress 전환이 막힌다.
- 마지막 결정 ID는 decision-15다. decision-14는 계획 승인 = 사람 키로 서명한 빈 커밋, 검사는 In Progress 시점이다.

### Assessment
새 공유 함수 `branch_start_targets(command, cwd)`를 만든다. 반환값은 (대상 저장소, 브랜치 이름, 시작점, 새로 만듦 여부) 목록이다. 대상 저장소는 DRAFT-8의 command_target_dir로 정한다. 시작점은 명시된 인자, 없으면 대상 저장소 HEAD, 기존 브랜치면 그 브랜치 tip, 원격만 있으면 origin/task/X로 잡는다. require_implementation_plan(형식 · 승인)과 require_work_order(작업 순서)가 이 함수를 REGISTRY로 공유해 각자 검사한다. 새 훅 파일을 만들지 않는 쪽이 등록 4곳(settings.hooks.json · REGISTRY · test_dedup_registry MODULES · test_hook_registration_contract CONTRACT/UNFILTERED)을 늘리지 않아 우선이다. 만들게 되면 4곳에 모두 등록한다. approval_status는 기준 리비전을 인자로 받게 바꾼다(브랜치 시점 = 시작점, In Progress 시점 = HEAD). 형식 · 작업 순서도 시작점의 트리(`git show <시작점>:<경로>`)로 판정한다. 미병합 판정은 base_refs와 `git cherry`를 쓴다(최상위 TASK-19의 squash 대응: 병합 뒤 브랜치 삭제 규칙). 카드를 찾지 못한 ID는 지금 check_card처럼 통과시킨다. require_active_task는 브랜치가 task/<ID>면 그 카드 상태를, 아니면 거부한다. rebase 중에는 .git/rebase-merge(또는 rebase-apply)/head-name으로 브랜치를 정한다. 꺼진 대안: task 브랜치 밖에서는 지금처럼 '아무 카드나 In Progress'면 통과시키는 것. 이 대안은 버렸다. task 브랜치 밖의 변경은 pre_commit_check가 어차피 커밋을 막으므로 편집 시점에 미리 막는 쪽이 낫다. 리뷰 때 유저가 다시 고를 수 있다.

### Plan
1. decision-16 초안(착수 = 미병합 브랜치, 두 시점, 명령 목록, 사람 터미널 제외)을 쓰고 유저 확인을 받는다.
2. AC #1 · #2: branch_start_targets 테스트(명령별 표) 먼저, 그다음 require_implementation_plan 확장(시작점 기준 승인).
3. AC #3 · #4: require_work_order 브랜치 트리거 테스트 먼저, 구현. In Progress 시점 회귀 테스트.
4. AC #5 · #6: require_active_task 테스트 먼저(다른 카드 In Progress, 브랜치 밖, rebase 중), 구현.
5. AC #8 등록 · REGISTRY, README · CLAUDE.md.snippet 문구, coverageCommand 100%. 임시 저장소에서 승인 없음 → 거부, 승인 뒤 → 통과, 낡은 작업 순서 → 거부를 실제로 재현한다.
<!-- SECTION:PLAN:END -->
