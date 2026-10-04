---
id: TASK-39
title: 'pre_commit_check·pre_push_coverage_check·backlog_commit_scope: 명령 문자열 매칭 오탐 정리'
status: Done
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-04 01:14'
labels:
  - hooks
  - bug
dependencies: []
references:
  - TASK-34
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-34 조사 중 발견. 세 훅이 공유하는 command_invokes_git_subcommand는 명령 전체를 shlex로 나눠 git 다음 단어만 본다. 그래서 'echo git commit', heredoc 본문, 따옴표 인자 안의 글자에도 commit/push로 반응한다(pre_push_coverage_check는 커버리지 실행까지 돈다). TASK-34의 command_head 기반 판정으로 바꾼다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 세 훅이 명령 위치의 git 하위 명령만 판정한다
- [x] #2 공용 헬퍼 교체를 REGISTRY와 테스트에 반영하고 drift가 없다
- [x] #3 재현 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pre_commit_check·pre_push_coverage_check·backlog_commit_scope가 명령 문자열 전체를 shlex로 훑던 command_invokes_git_subcommand 대신 명령 위치 판정(TASK-34 헬퍼 4종 + 새 공용 헬퍼 git_subcommand_index/command_runs_git, REGISTRY 등록)을 쓴다. echo·따옴표 인자·heredoc 본문 속 글자는 무시하고, /usr/bin/git, -C/-c/--git-dir, env/sudo 접두, 연쇄 세그먼트, (git commit), 줄 이음은 잡는다. 파싱 불가 줄은 게이트 훅이라 보수적으로 판정. backlog_commit_scope의 git add 재생도 같은 세그먼트를 쓰도록 맞췄다(heredoc 속 git add 재생 오탐 제거). settings.hooks.json에서 pre_commit_check·backlog_commit_scope의 if: Bash(git *) 필터 제거(경로·접두 호출이 게이트를 우회했음), pre_push_coverage_check는 옵트인 리포트라 유지(한계는 docstring). 1061 passed, 세 파일 커버리지 100%(__main__ 제외). 남은 차이: xargs/timeout 뒤 git은 이 훅들에선 미검출(pre_git_safety_check는 보수적으로 검출). AC #3 설치는 일괄.
<!-- SECTION:FINAL_SUMMARY:END -->
