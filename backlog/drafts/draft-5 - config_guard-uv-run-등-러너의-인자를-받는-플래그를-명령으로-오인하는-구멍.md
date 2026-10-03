---
id: DRAFT-5
title: 'config_guard: uv run 등 러너의 인자를 받는 플래그를 명령으로 오인하는 구멍'
status: Draft
assignee: []
created_date: '2026-10-03 17:51'
updated_date: '2026-10-03 17:51'
labels:
  - hooks
  - security
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-41 커버리지 작업 중 발견. effective_head가 uv run의 플래그를 한 토큰씩만 건너뛰어, uv run --with x rm <보호 경로>에서 플래그 인자 x를 실행 명령으로 본다. 그래서 실제 쓰기 명령 rm이 판정되지 않고 통과한다. --with=x 형태와 nice -n, timeout -s, xargs -I처럼 인자 받는 플래그가 등록된 러너는 정상 차단된다. uv run/uvx(--with, --python, --from, --project, --directory 등)를 비롯한 러너들의 인자 받는 플래그를 RUNNER_FLAGS_WITH_ARG에 넣고, 모르는 플래그 뒤의 판정은 보수적으로 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 uv run·uvx의 인자 받는 플래그(--with, --python, --from, --project, --directory, -p 등) 뒤의 실제 명령을 판정해 보호 경로 쓰기를 막는다
- [ ] #2 알 수 없는 플래그가 있는 러너 줄에서 보호 경로 쓰기 가능성이 보이면 보수적으로 막는다
- [ ] #3 재현 테스트를 추가하고 줄·분기 커버리지 100%·전체 스위트를 유지하며 설치본을 갱신한다
<!-- AC:END -->
