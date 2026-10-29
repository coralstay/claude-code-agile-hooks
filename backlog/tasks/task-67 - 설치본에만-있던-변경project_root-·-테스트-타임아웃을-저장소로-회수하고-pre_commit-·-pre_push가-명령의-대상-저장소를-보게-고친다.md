---
id: TASK-67
title: >-
  설치본에만 있던 변경(project_root · 테스트 타임아웃)을 저장소로 회수하고, pre_commit · pre_push가 명령의 대상
  저장소를 보게 고친다
status: To Do
assignee: []
created_date: '2026-10-29T12:17:00Z'
updated_date: '2026-10-29T23:36:00Z'
labels:
  - hooks
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정 · 발견(2026-10-29): ① 설치본(~/.claude/hooks/claude-code-agile-hooks)에만 있던 변경 — `project_root()`(하위 디렉터리 · 링크된 워크트리 지원)와 pre_commit_check의 fail-closed 테스트 타임아웃(`testTimeoutSeconds` · `CC_AGILE_TEST_TIMEOUT`) — 을 저장소로 회수한다. ② 설치된 pre_commit_check · pre_push_check가 명령이 실제로 겨누는 저장소(`cd <dir> && git ...`, `git -C <dir> ...`)가 아니라 훅 입력의 `cwd`(세션 cwd)로 판정하는 버그를 고친다. 실제로 본 증상: 저장소 A에서 한 커밋이 저장소 B의 testCommand를 돌렸고, 이 저장소에서 한 push가 최상위 저장소의 task 브랜치(In Progress) 때문에 막혔다.

주의(조사 결과): 설치본은 2026-10-29 20:44 install.sh 재설치로 저장소 main과 같아졌다(hooks/*.py 전부 diff 없음). 설치본에 남은 흔적은 고아가 된 test_project_root.py(10-24)뿐이다. 회수 원본은 ~/.cache/claude-hook-patch/new/claude-code-agile-hooks(2026-10-25 스냅숏, fail-closed 패치 적용 뒤)와 ~/.cache/claude-hook-patch/fail-closed.patch다. 이 스냅숏은 TASK-59 ~ 63 이전 기준이라 파일째 덮으면 안 되고, project_root · 타임아웃 부분만 main 위에 옮긴다.

이 카드는 최상위 coralstay-software-factory TASK-19의 결정을 구현한다. 커밋 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다. H2(착수 검사) · H4(커밋 메시지 ID)가 이 카드의 대상 저장소 해석을 재사용한다.

## 비즈니스 규칙
- B1 (AC #2) 세션 cwd가 저장소의 하위 디렉터리여도 그 저장소의 게이트가 걸린다
- B2 (AC #2) 링크된 워크트리(.git이 파일)에서도 게이트가 걸린다
- B3 (AC #3) testCommand가 제한 시간 안에 끝나지 않으면 커밋을 거부한다(fail-closed), 제한 시간은 환경변수 > 프로젝트 설정 > 기본값 1500초 순이다
- B4 (AC #4) 세션 cwd가 저장소 A일 때 `cd <B> && git commit`은 A가 아니라 B의 testCommand · 브랜치 규칙으로 판정한다
- B5 (AC #4) `git -C <B> commit`도 B로 판정하고, 상대 경로는 앞선 `cd`를 반영해 푼다
- B6 (AC #5) 세션 cwd 저장소 A의 task 브랜치가 In Progress여도 `cd <B> && git push`는 B의 브랜치 · 카드로만 판정한다
- B7 (AC #4) 대상 디렉터리를 정적으로 알 수 없으면(변수 · 명령 치환 경로) 세션 cwd로 판정한다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 회수: project_root()를 8개 훅(require_active_task · pre_commit_check · pre_push_check · block_stop_if_dirty · session_start · require_draft_first · backlog_commit_scope · require_test_first)에 넣어 is_backlog_project를 대체하고, dedup REGISTRY · test_dedup_registry를 project_root로 바꾸고, hooks/test_project_root.py를 회수한다 — 회수 원본(~/.cache/claude-hook-patch/new/claude-code-agile-hooks)과 project_root 함수 AST · test_project_root.py가 같다
- [ ] #2 세션 cwd가 저장소의 하위 디렉터리이거나 링크된 워크트리여도 git top-level을 루트로 잡아 게이트가 걸리고, testCommand · 설정 · backlog CLI는 그 루트에서 돈다
- [ ] #3 fail-closed 테스트 타임아웃 회수: CC_AGILE_TEST_TIMEOUT > testTimeoutSeconds > 기본 1500초, 시간 초과면 프로세스 그룹을 끝내고 커밋을 거부한다. settings.hooks.json의 pre_commit_check 항목에 timeout 1800을 넣는다
- [ ] #4 pre_commit_check가 같은 줄의 앞선 cd <dir>와 git -C <dir>로 명령의 대상 저장소를 정하고 그 저장소로 판정한다 — '저장소 A 세션에서 cd B && git commit이 A의 testCommand를 돌린' 실패를 재현하는 테스트가 있다
- [ ] #5 pre_push_check도 같은 방식으로 대상 저장소를 판정한다 — '최상위 저장소 task 브랜치가 In Progress라서 hooks 저장소 push가 막힌' 실패를 재현하는 테스트가 있다
- [ ] #6 대상 저장소 해석 함수(command_target_dir)를 dedup REGISTRY 공유 함수로 등록해 H2 · H4가 같은 함수를 쓴다
- [ ] #7 회수 뒤 install.sh로 재설치하면 설치본과 저장소 hooks/*.py의 diff가 없고, 설치본의 고아 test_project_root.py도 저장소 것과 같다 (수동)
- [ ] #8 유저가 ~/.claude/settings.json의 pre_commit_check 항목에 timeout 1800을 넣는다 — config_guard 대상이라 유저 조치 (수동)
- [ ] #9 대상 저장소 해석(command_target_dir)을 backlog_commit_scope와 backlog 명령을 검사하는 훅들(require_implementation_plan · require_work_order · require_stage_committed · require_draft_first 등 cd <dir> && backlog … 를 보는 훅)에도 적용한다 — 세션 위치가 아니라 명령의 대상 저장소의 스테이징 · 카드 · 설정으로 판정하는 테스트가 훅마다 있다 (유저 결정 2026-10-30)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 바뀐 훅이 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트와 맞는다
- [ ] #3 README · CLAUDE.md.snippet 반영 (수동)
- [ ] #4 각 커밋에 TASK ID와 본문 'Refs: coralstay-software-factory TASK-19', push 전 Done + final summary (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-10-29 두 가지를 요청했다. 설치본에서만 고친 project_root · 테스트 타임아웃을 저장소로 되돌려 놓을 것, 그리고 다른 저장소를 겨누는 git 명령이 세션 cwd 저장소로 판정되는 버그를 고칠 것. 회수한 부분은 설치본과 저장소가 같아야 한다.

### Objective
- hooks/pre_commit_check.py:211 · hooks/pre_push_check.py:195가 `cwd = data.get("cwd")`를 그대로 쓴다. 이후 is_backlog_project · has_active_task · current_branch · testCommand 실행이 모두 이 cwd 기준이다(pre_commit_check.py:217-236, pre_push_check.py:201-207).
- 저장소 main의 is_backlog_project(cwd)는 `isdir(cwd/.git)`를 본다(pre_commit_check.py:145-150, 같은 함수가 REGISTRY "is_backlog_project"로 여러 훅에 복사돼 있다). 그래서 하위 디렉터리나 링크된 워크트리(.git이 파일)에서 시작한 세션은 게이트가 꺼진다.
- 설치본 ~/.claude/hooks/claude-code-agile-hooks/*.py는 2026-10-29 20:44 install.sh(install.sh:18 `cp hooks/*.py`)로 덮어써져 저장소와 같다. 설치본에만 남은 파일은 test_project_root.py(2026-10-24)이고 work_order.py는 scripts/에서 복사된 것이다.
- 회수 원본 ~/.cache/claude-hook-patch/new/claude-code-agile-hooks(2026-10-25): project_root()가 8개 훅(require_active_task · pre_commit_check · pre_push_check · block_stop_if_dirty · session_start · require_draft_first · backlog_commit_scope · require_test_first)에 있고, dedup_drift_guard REGISTRY 키가 "project_root"이며, test_dedup_registry가 project_root의 AST 일치를 검사한다. pre_commit_check에는 TIMEOUT_ENV(L51) · commit_test_timeout(L253) · _kill_group(L276) · run_shell_with_timeout(L283)이 있다. fail-closed.patch(300줄)는 pre_commit_check.py · test_pre_commit_check.py만 고친다.
- 그 스냅숏은 main과 다른 곳이 많다(backlog_commit_scope 308줄 · pre_push_coverage_check 188줄 등은 TASK-59 ~ 63 변경). 파일째 복사하면 그 변경이 사라진다.
- ~/.claude/settings.json의 pre_commit_check 항목에는 `timeout`이 없다(기본 600초). 그래서 내부 제한 1500초보다 Claude Code가 먼저 취소하고 커밋이 그냥 진행된다(fail-open).
- git 명령 파싱 함수(strip_heredoc_bodies · tokenize · split_segments · command_head · git_subcommand_index)는 REGISTRY로 공유돼 있다(dedup_drift_guard.py:83-161).

### Assessment
회수는 함수 · 테스트 단위로 main 위에 옮긴다. 기준은 '회수 원본과 함수 AST가 같다'로 잡는다. 설치본이 이미 덮어써졌으므로 '설치본 == 저장소'는 회수 뒤 install.sh로 다시 맞추고 diff로 확인한다. 대상 저장소 해석은 새 공유 함수 `command_target_dir(command, cwd)` 하나로 만든다. git 세그먼트마다 같은 줄에서 앞선 `cd <dir>`(&& · ; 연결)와 `git -C <dir>`를 누적해 디렉터리를 정하고 project_root를 적용한다. 정적으로 알 수 없는 경로면 세션 cwd로 돌아간다(B7). 이 함수는 REGISTRY에 등록해 H2 · H4가 재사용한다. 다른 훅(backlog CLI를 `cd`로 겨누는 경우 등)의 같은 문제는 이 카드 범위 밖이다. 발견하면 유저에게 묻는다.

### Plan
1. 회수 원본에서 project_root · test_project_root.py · 타임아웃 hunk를 추출해 회수 목록을 노트에 적는다.
2. AC #1 · #2: project_root 테스트 먼저(test_project_root.py 회수), 8개 훅의 is_backlog_project를 project_root로 바꾸고 REGISTRY · test_dedup_registry를 맞춘다.
3. AC #3: 타임아웃 테스트 먼저, fail-closed 구현, settings.hooks.json pre_commit_check에 timeout 1800을 넣는다.
4. AC #4 · #5: 관찰된 두 실패를 재현하는 테스트(임시 저장소 두 개) 먼저, 그다음 command_target_dir 구현 · 공유 등록.
5. install.sh 재설치 뒤 설치본 · 저장소 diff를 확인하고, README · CLAUDE.md.snippet을 고치고, coverageCommand 100%를 확인한다.
<!-- SECTION:PLAN:END -->
