---
id: DRAFT-9
title: 'pre_commit_check·pre_push_coverage_check·backlog_commit_scope: 명령 문자열 매칭 오탐 정리'
status: Draft
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-03 08:12'
labels:
  - hooks
  - bug
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-34 조사 중 발견. 세 훅이 공유하는 command_invokes_git_subcommand는 명령 전체를 shlex로 나눠 git 다음 단어만 본다. 그래서 'echo git commit', heredoc 본문, 따옴표 인자 안의 글자에도 commit/push로 반응한다(pre_push_coverage_check는 커버리지 실행까지 돈다). TASK-34의 command_head 기반 판정으로 바꾼다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 세 훅이 명령 위치의 git 하위 명령만 판정한다
- [ ] #2 공용 헬퍼 교체를 REGISTRY와 테스트에 반영하고 drift가 없다
- [ ] #3 재현 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->
