---
id: decision-3
title: 라우터/dispatcher 훅 도입 안 함 — 완전 독립형 설계 유지
date: '2026-09-19 01:59'
status: accepted
---
## Context

TASK-1의 dedup 버그를 본 뒤 사용자가 "라우터 훅을 도입할까 생각중"이라고 제안했다.
공용 dispatcher/shared module로 묶으면 `is_backlog_project()` 같은 중복 버그를 근본적으로
없앨 수 있지만, 이 저장소가 애초에 bash 시절 공용 함수 파일(`_lib.sh`)을 버리고
"완전 독립형"(다른 훅 파일을 import하지 않음) 27개로 간 이유 — "한 훅의 버그가 다른 훅을
절대 안 깨뜨린다" — 를 정면으로 되돌리는 결정이다. 업스트림 두 곳
(`karanb192/claude-code-hooks`, `disler/claude-code-hooks-mastery`)을 fork해서 확인한
결과, 둘 다 여전히 "훅 1개 = 스크립트 1개" 구조를 유지하고 있어 라우터 패턴의 선례가
없다는 것도 확인했다.

## Decision

라우터/dispatcher 훅을 도입하지 않는다. 대신 dedup 문제는 `dedup_drift_guard.py`(사후
검증, decision-2)로 대응한다. 이 판단은 사용자가 명시적으로 "훅 설계는 하지 않고"라고
방향을 정리하면서 확정됐다.

## Consequences

- 공용 모듈 하나의 버그가 안전 훅 전체를 동시에 무력화하는 리스크는 피했다 — 특히
  `config_guard.py`/`protect_secrets.py`/`block_dangerous_commands.py` 같은 보안 훅은
  독립적으로 있는 게 오히려 장점이다.
- 대신 코드 중복과 drift 재발 가능성은 계속 안고 간다 — `dedup_drift_guard.py`의
  REGISTRY를 계속 유지보수해야 한다.
- 업스트림 두 원본과 설계 원칙이 일치한다는 걸 근거로 확보했으므로, 나중에 이 판단을
  뒤집으려면 "업스트림도 안 하는 걸 왜 우리만 해야 하는가"에 대한 별도 근거가 필요하다.
