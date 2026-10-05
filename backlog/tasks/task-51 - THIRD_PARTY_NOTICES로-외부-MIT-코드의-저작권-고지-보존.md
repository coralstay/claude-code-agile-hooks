---
id: TASK-51
title: THIRD_PARTY_NOTICES로 외부 MIT 코드의 저작권 고지 보존
status: Done
assignee: []
created_date: '2026-10-05 07:26'
updated_date: '2026-10-05 07:27'
labels:
  - license
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
hooks/의 17개 훅은 karanb192/claude-code-hooks(MIT)에서 포팅했다. MIT는 원 저작권 고지와 허가 문구를 사본에 포함하라고 요구하므로 THIRD_PARTY_NOTICES.md에 원문과 대상 파일을 모은다. README 외부 코드 문장 중 disler/claude-code-hooks-mastery를 MIT라고 한 부분은 틀렸으므로(해당 저장소는 라이선스 없음) 바로잡는다.

수용 기준(승격 시 AC로 등록):
1. THIRD_PARTY_NOTICES.md에 karanb192/claude-code-hooks의 MIT 고지 전문과 포팅한 파일 목록을 둔다
2. README 라이선스 절이 THIRD_PARTY_NOTICES.md를 가리키고, disler 저장소를 MIT라고 하지 않는다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 THIRD_PARTY_NOTICES.md에 karanb192/claude-code-hooks의 MIT 고지 전문과 포팅한 파일 목록을 둔다
- [x] #2 README 라이선스 절이 THIRD_PARTY_NOTICES.md를 가리키고, disler 저장소를 MIT라고 하지 않는다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
THIRD_PARTY_NOTICES.md에 karanb192/claude-code-hooks의 MIT 고지 전문(Copyright (c) 2026 Karan Bansal)과 포팅한 17개 훅 파일 목록을 두었다. README 라이선스 절의 외부 코드 문장은 이 파일을 가리키도록 고치고, 라이선스가 없는 disler/claude-code-hooks-mastery를 MIT라고 한 오류를 뺐다. disler 유래 부분(session_logger의 user_prompt_submit 로깅)의 권리 문제는 미해결로 유저에게 보고. 커밋 aa108ba.
<!-- SECTION:FINAL_SUMMARY:END -->
