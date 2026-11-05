---
id: DRAFT-2
title: 커맨드 문자열 매칭의 구조적 한계를 보완할 syscall 레벨 샌드박스 레이어 검토
status: Draft
assignee: []
created_date: '2026-09-19 04:31'
updated_date: '2026-09-19 04:31'
labels: []
dependencies: []
documentation:
  - >-
    backlog/decisions/decision-1 -
    커맨드-문자열-매칭-훅은-basename-정규화까지만-—-syscall-레벨-강제는-범위-밖.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-1/README 10장에서 "Claude Code 훅 API는 커맨드 문자열만 받으므로 syscall 레벨 강제(seccomp/eBPF/Landlock)는 이 저장소 범위 밖"이라고 명시했다. 범위 밖이라는 게 영원히 안 한다는 뜻은 아니므로, 별도 프로젝트로 분리할 가치가 있는지만 탐색해둔다. 리서치했던 선례(Sandlock arXiv:2605.26298, 커널 강제 샌드박스 구현 블로그)가 출발점. 아직 할지 말지도 정해지지 않은 탐색 단계라 draft로 남기고 promote하지 않는다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 claude-rails 저장소 자체 범위가 아니라 Claude Code 프로세스를 감싸는 별도 레이어여야 하는 근거를 README 10장 논리보다 구체화
- [ ] #2 seccomp-bpf/eBPF/Landlock/bubblewrap 중 macOS 환경에서 실제로 쓸 수 있는 게 무엇인지 리서치(Linux 전용 기술이 많아 Endpoint Security 등 다른 접근이 필요할 수 있음 확인)
- [ ] #3 별도 프로젝트로 분리할 가치가 있는지, Claude Code 자체 sandbox 설정만으로 충분한지 판단
- [ ] #4 이 draft도 promote하지 않고 사용자 검토 대기
<!-- AC:END -->
