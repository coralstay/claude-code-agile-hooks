---
id: TASK-47
title: 'config_guard: uv run 등 러너의 인자를 받는 플래그를 명령으로 오인하는 구멍'
status: Done
assignee: []
created_date: '2026-10-03 17:51'
updated_date: '2026-10-04 01:14'
labels:
  - hooks
  - security
dependencies: []
references:
  - TASK-35
  - TASK-41
  - decision-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-41 커버리지 작업 중 발견. effective_head가 uv run의 플래그를 한 토큰씩만 건너뛰어, uv run --with x rm <보호 경로>에서 플래그 인자 x를 실행 명령으로 본다. 그래서 실제 쓰기 명령 rm이 판정되지 않고 통과한다. --with=x 형태와 nice -n, timeout -s, xargs -I처럼 인자 받는 플래그가 등록된 러너는 정상 차단된다. uv run/uvx(--with, --python, --from, --project, --directory 등)를 비롯한 러너들의 인자 받는 플래그를 RUNNER_FLAGS_WITH_ARG에 넣고, 모르는 플래그 뒤의 판정은 보수적으로 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 uv run·uvx의 인자 받는 플래그(--with, --python, --from, --project, --directory, -p 등) 뒤의 실제 명령을 판정해 보호 경로 쓰기를 막는다
- [x] #2 알 수 없는 플래그가 있는 러너 줄에서 보호 경로 쓰기 가능성이 보이면 보수적으로 막는다
- [x] #3 재현 테스트를 추가하고 줄·분기 커버리지 100%·전체 스위트를 유지하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config_guard.py에 러너·래퍼 플래그 인자 처리를 넣었다. skip_flags()가 값을 받는 플래그는 다음 토큰까지 소비하고 --, --flag=value, -Xvalue를 처리하며 모르는 플래그를 보고한다. uv run/uvx/uv 전역 플래그, uv tool run, poetry/pipx/pdm, nice/ionice/xargs/stdbuf/doas/caffeinate/timeout, 그리고 래퍼(sudo -u root rm X에서 root를 명령으로 보던 같은 구멍 포함)의 값 플래그를 등록했다. 모르는 플래그가 있는 러너·래퍼 세그먼트는 보호 경로 언급 + 쓰기 가능 명령 단어가 있으면 보수적으로 차단(env -S, npx -c는 의도적으로 모르는 플래그로 둠). 실패 상태 재현 테스트 29건 → 수정 후 통과, 차단 40건·통과 15건. 기존 테스트 변경 없음, pragma 없음. 1423 passed, 커버리지 100%. 알려진 오탐: 모르는 플래그 + 쓰기 도구 이름이 들어간 읽기 전용 명령. 남은 차이: /usr/bin/sudo 경로 래퍼는 래퍼로 인식 안 함(공용 command_head 범위). AC #3 설치는 일괄.
<!-- SECTION:FINAL_SUMMARY:END -->
