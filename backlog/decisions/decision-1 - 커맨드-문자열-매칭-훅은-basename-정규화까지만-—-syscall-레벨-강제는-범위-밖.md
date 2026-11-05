---
id: decision-1
title: 커맨드 문자열 매칭 훅은 basename 정규화까지만 — syscall 레벨 강제는 범위 밖
date: '2026-09-19 01:59'
status: accepted
---
## Context

독립 재감사(TASK-7 배경)에서 `command_invokes_git_subcommand`(5개 파일), `config_guard.py`,
`case_insensitive_guard.py`, `protect_tests.py`가 verb를 `tokens[0]` 정확 일치로만 비교해
`/usr/bin/git`, `/bin/rm` 같은 절대/상대경로 호출에 전부 뚫리는 걸 확인했다. 리서치 결과
이건 sudoers 등에서 잘 알려진 클래스의 문제이고, LLM 에이전트 런타임 보안 연구도
"정규식/토큰 기반 커맨드 매칭은 인코딩 트릭·alias·간접 실행으로 우회 가능하다"고
결론짓는다. 진짜 확실한 방어는 커널 레벨 강제(seccomp-bpf/eBPF/Landlock)인데, Claude
Code 훅은 애초에 커맨드 문자열만 받는 PreToolUse API라 이 훅 스크립트들 안에서 syscall
레벨 강제를 구현하는 것 자체가 불가능하다.

## Decision

발견된 절대/상대경로 우회는 `os.path.basename()` 정규화로 실제로 막는다(TASK-7). 하지만
"정규식/토큰 매칭으로 위험한 행동을 완벽히 막을 수 있다"는 인상은 주지 않는다 — syscall
레벨 강제(seccomp/eBPF 등)는 이 저장소(훅 스크립트 모음)의 범위 밖으로 명시적으로
제외하고, 대신 Claude Code 자체의 `permissions.deny`/sandbox 기능과 병행하라고 README
10장에 정직하게 안내한다(TASK-11, 업스트림 protect-secrets.js의 "Native pairing" 절 참고).

## Consequences

- basename 정규화로 지금 발견된 구멍은 막히지만, 앞으로도 "발견되면 고치는" 사후 대응
  구조는 그대로 남는다 — 새로운 우회 클래스가 또 나올 수 있다는 전제를 안고 간다.
- 이 저장소만으로는 완결된 방어선이 될 수 없다는 걸 README에 명시했으므로, 진짜 강한
  보장이 필요하면 사용자가 별도로 Claude Code의 sandbox/permissions 설정을 구성해야
  한다 — 이 훅들이 그걸 대신 해주지 않는다.
- 만약 나중에 syscall 레벨 강제가 필요하다고 판단되면, 그건 이 저장소를 확장하는 게
  아니라 별도의 프로젝트(예: Claude Code 프로세스를 감싸는 sandbox 레이어)가 필요하다.
