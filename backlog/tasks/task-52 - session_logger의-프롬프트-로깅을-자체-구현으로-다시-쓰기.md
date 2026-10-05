---
id: TASK-52
title: session_logger의 프롬프트 로깅을 자체 구현으로 다시 쓰기
status: To Do
assignee: []
created_date: '2026-10-05 07:31'
labels:
  - license
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
hooks/session_logger.py의 UserPromptSubmit 로깅은 라이선스가 없는 disler/claude-code-hooks-mastery에서 합쳐 넣었다고 적혀 있다. 라이선스 없는 코드는 AGPL로 재배포할 권리가 없으므로, 해당 부분을 지우고 명세만으로 새로 구현한다(클린룸: 구현자는 지운 코드와 disler 저장소를 보지 않는다). 유저가 '직접 다시 쓰기'를 선택함.

수용 기준(승격 시 AC로 등록):
1. disler 유래 코드(handle_user_prompt_submit)를 지우고 명세만 받은 구현자가 새로 구현한다
2. 머리말에서 disler 출처 표기를 빼고 프롬프트 로깅이 자체 구현임을 적는다
3. 기존 테스트와 커버리지 100% 게이트를 통과한다
<!-- SECTION:DESCRIPTION:END -->
