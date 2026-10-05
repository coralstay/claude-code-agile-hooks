---
id: TASK-53
title: disler 유래 훅 2개를 자체 구현으로 다시 쓰기
status: Done
assignee: []
created_date: '2026-10-05 07:35'
updated_date: '2026-10-05 07:39'
labels:
  - license
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
hooks/permission_auto_allow.py와 hooks/pre_compact_backup.py는 라이선스가 없는 disler/claude-code-hooks-mastery에서 포팅했다고 적혀 있다. 재배포 권리가 없으므로 두 파일을 지우고 명세만 받은 구현자가 새로 구현한다(클린룸). backlog/docs/doc-2에서 disler를 MIT라고 한 문장도 바로잡는다. 유저가 '모두 직접 다시 쓰기'를 지시함.

수용 기준(승격 시 AC로 등록):
1. 두 훅을 지우고 명세만 받은 구현자가 이전 코드와 disler 저장소를 보지 않고 새로 구현한다
2. 두 훅의 머리말에서 disler 포팅 표기를 빼고 자체 구현임을 적는다
3. backlog/docs/doc-2의 disler MIT 표기를 바로잡는다
4. 기존 테스트와 커버리지 100% 게이트를 통과한다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 두 훅을 지우고 명세만 받은 구현자가 이전 코드와 disler 저장소를 보지 않고 새로 구현한다
- [x] #2 두 훅의 머리말에서 disler 포팅 표기를 빼고 자체 구현임을 적는다
- [x] #3 backlog/docs/doc-2의 disler MIT 표기를 바로잡는다
- [x] #4 기존 테스트와 커버리지 100% 게이트를 통과한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
permission_auto_allow.py와 pre_compact_backup.py(disler 유래 표기, 라이선스 없음)를 비우고, 명세만 받은 별도 구현자(서브에이전트)가 이전 코드·disler 저장소·설치본·backlog/docs를 보지 않고 새로 구현했다. 머리말은 자체 구현이라고 적었다. doc-2에서 disler를 MIT라고 한 두 문장을 고쳐 THIRD_PARTY_NOTICES.md를 가리키게 했다. 재작성 중 바뀐 실행 비트는 원래대로 644로 되돌렸다. 테스트 1672 통과, 커버리지 100%. 기존 동작과 같이 남은 한계: 같은 초에 두 번 백업하면 덮어씀, session_id에 /가 있으면 BACKUP_DIR 밖에 쓸 수 있음 — 범위 밖이라 유저에게 보고. 커밋 617329f, d46a658.
<!-- SECTION:FINAL_SUMMARY:END -->
