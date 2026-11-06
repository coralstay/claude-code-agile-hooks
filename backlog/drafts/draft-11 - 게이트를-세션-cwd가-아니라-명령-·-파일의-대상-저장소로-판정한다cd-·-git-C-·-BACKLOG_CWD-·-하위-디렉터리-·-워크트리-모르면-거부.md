---
id: DRAFT-11
title: >-
  게이트를 세션 cwd가 아니라 명령 · 파일의 대상 저장소로 판정한다(cd · git -C · BACKLOG_CWD · 하위 디렉터리 ·
  워크트리, 모르면 거부)
status: Draft
assignee: []
created_date: '2026-11-06T01:07:00Z'
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
