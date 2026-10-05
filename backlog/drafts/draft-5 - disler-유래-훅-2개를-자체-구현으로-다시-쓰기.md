---
id: DRAFT-5
title: disler 유래 훅 2개를 자체 구현으로 다시 쓰기
status: Draft
assignee: []
created_date: '2026-10-05 07:35'
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
