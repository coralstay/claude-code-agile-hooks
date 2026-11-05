---
id: decision-2
title: 복붙 함수 drift는 REGISTRY 사후검증으로 — codegen 전환은 보류
date: '2026-09-19 01:59'
status: accepted
---
## Context

`is_backlog_project()`가 5개 훅 파일에 복붙돼 있는데 1곳만 버그가 고쳐지고 나머지 4곳은
방치돼 있던 걸 TASK-1에서 발견했다(삽질기록.md 2026-09-10 교훈이 절반만 반영된 사례).
이 클래스의 버그를 막는 방법을 리서치한 결과, Kubernetes의 `hack/update-codegen.sh` +
`hack/verify-codegen.sh` 패턴(하나의 소스에서 생성 → CI가 재생성 후 diff로 검증)이
업계 표준 해법 중 하나로 확인됐다. 이 방식은 "생성(generate)"과 "검증(verify)" 두
절반으로 이뤄지는데, `dedup_drift_guard.py`(TASK-6)는 검증 절반만 구현하고 있다.

## Decision

지금 단계에서는 `dedup_drift_guard.py`의 REGISTRY를 확장하는 사후검증 방식을 유지한다
(TASK-9: `command_invokes_git_subcommand`/`has_command`/`has_active_task`/`run_shell`
추가 등록). Kubernetes식 codegen(하나의 소스에서 N개 파일을 생성)으로 전환하는 건 이번
세션에서 하지 않고 다음 단계 후보로 남겨둔다 — 아키텍처를 더 크게 바꾸는 일이라 신중한
설계가 필요하다고 판단했다.

## Consequences

- 여전히 사람(또는 Claude)이 5곳을 손으로 고쳐야 하고, `dedup_drift_guard.py`는 "다
  고친 뒤에 어긋났는지 확인"만 한다 — 애초에 손으로 복붙 못 하게 막는 건 아니다.
- REGISTRY에 없는 새로운 복붙 함수가 생기면 또 사각지대가 될 수 있다(TASK-9에서 실제로
  `dedup_drift_guard.py` 자신의 `command_invokes_git_subcommand`가 사각지대였던 걸
  발견해서 등록했다).
- codegen 전환은 아직 판단 보류 상태 — 필요성이 더 쌓이면(REGISTRY가 계속 커지거나
  drift가 실제로 재발하면) 다시 검토해야 한다.
