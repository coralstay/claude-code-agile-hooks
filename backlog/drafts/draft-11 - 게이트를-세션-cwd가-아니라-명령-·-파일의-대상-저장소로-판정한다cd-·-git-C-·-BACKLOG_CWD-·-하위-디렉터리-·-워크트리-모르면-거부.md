---
id: DRAFT-11
title: >-
  게이트를 세션 cwd가 아니라 명령 · 파일의 대상 저장소로 판정한다(cd · git -C · BACKLOG_CWD · 하위 디렉터리 ·
  워크트리, 모르면 거부)
status: Draft
assignee: []
created_date: '2026-11-06T01:07:00Z'
updated_date: '2026-11-06T01:08:00Z'
labels:
  - security
  - workflow
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 결정(2026-11-06): TASK-67에서 '대상 저장소 판정' 부분을 이 카드로 나눈다(TASK-67에는 설치본 회수 · 테스트 타임아웃만 남김). 빈틈부터 메운다.
실제로 본 우회(2026-11-06, TASK-72 DoD #3 확인 중): 세션 cwd가 backlog 프로젝트가 아닐 때 'cd <다른 저장소> && backlog task edit TASK-1 -s "In Progress"'가 AI 서명 승인으로도 통과했다. 훅 21개가 data.get("cwd")(세션 cwd)로 판정하고, 그중 backlog 게이트 14개는 세션 cwd가 backlog 프로젝트가 아니면 검사 없이 통과시킨다. 이전에 본 증상(TASK-67): 저장소 A 세션에서 'cd B && git commit'이 A의 testCommand를 돌렸고, 다른 저장소의 task 브랜치 때문에 push가 막혔다.
같은 종류의 빈틈: (1) backlog CLI는 BACKLOG_CWD 환경 변수로 다른 프로젝트를 겨눈다 (2) 세션 cwd가 저장소의 하위 디렉터리이거나 링크된 워크트리(.git이 파일)면 is_backlog_project가 false라 게이트가 꺼진다 (3) Edit/Write 게이트(require_active_task · require_test_first의 편집 검사 등)는 편집 파일이 속한 저장소가 아니라 세션 cwd로 판정한다 (4) TASK-67 원래 계획 B7('대상을 정적으로 알 수 없으면 세션 cwd로')은 변수 하나로 같은 우회가 된다.

## 비즈니스 규칙
- B1 (AC #1) 저장소 루트는 git top-level로 정한다 — 하위 디렉터리와 링크된 워크트리에서도 그 저장소의 게이트가 걸린다
- B2 (AC #2) git commit · push 게이트는 같은 줄의 앞선 cd <dir>(&& · ; 연결)와 git -C <dir>로 정한 대상 저장소로 판정하고, 상대 경로는 앞선 cd를 반영해 푼다
- B3 (AC #3) backlog 명령 게이트는 같은 방식으로 정한 대상 저장소로 판정한다
- B4 (AC #4) BACKLOG_CWD=<dir>(명령 앞 대입 · env 래퍼)가 있으면 그 디렉터리가 backlog 명령의 대상이다
- B5 (AC #5) Edit/Write 게이트는 편집하는 파일이 속한 저장소로 판정한다
- B6 (AC #6) 게이트 대상 명령(git commit · push, backlog task edit -s, draft promote/create)에서 대상 디렉터리를 정적으로 알 수 없으면(변수 · 명령 치환 경로) 거부한다
- B7 (AC #7) 대상이 backlog 프로젝트가 아닌 곳이면 게이트를 걸지 않는다(세션 cwd와 무관)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 project_root(dir): git top-level을 저장소 루트로 정하는 공유 함수 — 하위 디렉터리 · 링크된 워크트리에서도 backlog 프로젝트로 인식하고, 게이트 훅의 is_backlog_project(cwd)를 project_root 기준으로 바꾼다(회수 원본 ~/.cache/claude-hook-patch는 참고만, 그대로 복사하지 않음)
- [ ] #2 command_target_dir(command, cwd): 같은 줄의 앞선 cd <dir>와 git -C <dir>를 누적해 대상 디렉터리를 정하고, pre_commit_check · pre_push_check가 그 저장소의 브랜치 · 카드 · testCommand로 판정한다 — 'A 세션에서 cd B && git commit이 A의 testCommand를 돌림' · 'A의 task 브랜치 때문에 B push가 막힘'을 재현하는 테스트
- [ ] #3 backlog 명령 게이트(require_implementation_plan · require_test_first · require_work_order · require_stage_committed · require_draft_first · require_coverage_on_done · backlog_commit_scope)가 대상 저장소로 판정한다 — 훅마다 'backlog 프로젝트가 아닌 세션 cwd에서 cd <프로젝트> && backlog …'가 그 프로젝트 규칙으로 거부되는 테스트
- [ ] #4 BACKLOG_CWD=<dir> 대입(명령 앞 · env 래퍼)을 backlog 명령의 대상으로 본다
- [ ] #5 Edit/Write 게이트(require_active_task · require_test_first 편집 검사 · require_test_layout 등)가 편집 파일이 속한 저장소로 판정한다
- [ ] #6 게이트 대상 명령에서 대상 디렉터리를 정적으로 알 수 없으면(cd "$X", cd $(…), git -C "$D", BACKLOG_CWD=$Y) 거부하고 이유를 안내한다
- [ ] #7 대상이 backlog 프로젝트가 아니면 세션 cwd가 프로젝트여도 그 명령에는 게이트를 걸지 않는다
- [ ] #8 command_target_dir · project_root를 dedup REGISTRY 공유 함수로 등록하고 쓰는 훅이 모두 같은 구현을 쓴다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 [수동 검증] README(Known gaps 갱신: 세션 cwd 문제 해소, 남는 한계는 bash -c · eval · 스크립트) · CLAUDE.md.snippet 반영
- [ ] #3 [수동 검증] 설치 후 실전: ~/githubs(비프로젝트) 세션에서 'cd <프로젝트> && backlog task edit … -s "In Progress"'가 AI 서명 승인으로 거부됨, 'cd "$X" && …'도 거부됨을 확인
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-11-06 'cd 다른 저장소 &&'로 승인 검사를 건너뛰는 빈틈을 메우라고 했고, TASK-67에서 대상 저장소 판정 부분을 나누라고 했다. 대상을 모르면 막는다(fail-closed).

### Objective
- 훅 21개가 data.get("cwd")로 판정하고 backlog 게이트 14개가 is_backlog_project(cwd)(= isdir(cwd/.git) + backlog/config.yml)로 걸릴지 정한다. 그래서 세션 cwd가 비프로젝트 · 하위 디렉터리 · 워크트리면 게이트가 꺼진다.
- 명령 파싱 함수(strip_heredoc_bodies · tokenize · split_segments · command_head)는 REGISTRY로 공유돼 있다(dedup_drift_guard.py). 훅은 self-contained(외부 import 없음).
- TASK-67의 원래 계획 B7은 '모르면 세션 cwd'였다. 회수 원본(~/.cache/claude-hook-patch/new, 2026-10-25)은 TASK-59~63 · 72 · 74 이전이라 파일째 쓰면 변경이 사라진다.
- 실측: TASK-72 DoD #3 확인 중 /tmp 대상 명령이 세션 cwd ~/githubs로 판정돼 통과.

### Assessment
project_root와 command_target_dir 두 공유 함수로 '대상 저장소'를 정의하고, 세션 cwd는 대상이 명시되지 않은 명령의 기본값으로만 쓴다. Edit/Write는 파일 경로가 대상이다. 정적으로 풀 수 없는 경로는 게이트 대상 명령에서 거부한다(우회보다 거부가 회복 가능). 훅이 많으므로 공유 함수를 먼저 만들고 훅 단위로 테스트 → 전환한다. bash -c · eval · 스크립트 안 명령은 이 카드로도 못 보며 README에 남긴다.

### Plan
1. AC #1 · #8: project_root 테스트 먼저(하위 디렉터리 · 워크트리 · 비저장소) → 구현 · REGISTRY 등록.
2. AC #2 · #6 · #7: command_target_dir 테스트 먼저(cd 누적 · git -C 상대 경로 · 변수 경로 거부 · 비프로젝트 대상) → pre_commit_check · pre_push_check 전환.
3. AC #3 · #4: backlog 명령 게이트 훅마다 대상 저장소 테스트 → 전환, BACKLOG_CWD 처리.
4. AC #5: Edit/Write 게이트를 파일 경로 기준으로 전환.
5. README · snippet, coverageCommand 100%. 유저 설치 후 실전 확인.
<!-- SECTION:PLAN:END -->
