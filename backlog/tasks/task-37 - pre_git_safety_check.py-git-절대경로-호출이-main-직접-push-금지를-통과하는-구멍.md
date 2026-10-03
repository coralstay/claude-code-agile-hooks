---
id: TASK-37
title: 'pre_git_safety_check.py: git 절대경로 호출이 main 직접 push 금지를 통과하는 구멍'
status: Done
assignee: []
created_date: '2026-10-03 08:12'
updated_date: '2026-10-03 13:13'
labels:
  - hooks
  - security
dependencies: []
references:
  - decision-1
  - TASK-34
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-34 조사 중 발견. pre_git_safety_check.py의 git_args_after_subcommand는 tokens[i] != 'git'으로 비교해 basename 정규화를 하지 않는다. 그래서 /usr/bin/git으로 main에 직접 push하면 규칙을 통과한다(decision-1이 요구하는 basename 정규화 미적용). 또 명령 전체를 shlex로 나눠 따옴표 안 글자에도 반응하고, 파싱 실패 시 통과시킨다(fail-open). 보안 가드라 파싱 실패는 보수적으로 판정해야 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 git 실행 파일을 basename으로 비교해 절대·상대 경로 호출도 같은 규칙을 적용한다
- [x] #2 명령 위치의 git만 판정하고 따옴표 인자·heredoc 안 글자는 무시한다(TASK-29/34 헬퍼 재사용, REGISTRY 등록)
- [x] #3 파싱 실패 시 보수적으로 판정하고 그 근거를 docstring에 남긴다
- [x] #4 재현 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pre_git_safety_check.py가 git을 basename으로 비교하고(/usr/bin/git, ../bin/git 등), 명령 위치 판정 헬퍼(strip_heredoc_bodies/tokenize/split_segments/command_head, REGISTRY 등록)로 세그먼트마다 모든 git 호출을 검사한다. 따옴표 인자·heredoc 본문은 무시. xargs/timeout/find -exec 뒤의 따옴표 없는 git도 계속 판정한다(기존 차단을 풀지 않기 위해 — 대가로 따옴표 없는 echo git push origin main은 오탐으로 남음, 보안 훅이라 수용). 파싱 실패 시 git + push/branch + main/master가 보이면 막는다(이전엔 통과). settings.hooks.json의 if: Bash(git *) 필터를 제거했다 — 필터가 명령 텍스트로 매칭해 절대경로 호출엔 훅이 실행조차 되지 않았다. 44개 테스트 추가, 820 passed. 후속: gh 검사는 여전히 줄 전체 토큰 스캔이라 /usr/bin/gh 경로 호출 미검출. AC #4 설치는 일괄 설치 때.
<!-- SECTION:FINAL_SUMMARY:END -->
