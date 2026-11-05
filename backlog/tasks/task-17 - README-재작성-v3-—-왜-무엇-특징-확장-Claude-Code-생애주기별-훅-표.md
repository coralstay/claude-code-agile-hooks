---
id: TASK-17
title: README 재작성 v3 — 왜/무엇/특징 확장 + Claude Code 생애주기별 훅 표
status: Done
assignee: []
created_date: '2026-09-19 05:05'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README에 '에이전트를 사용하기 위한 개인용 훅 모음집' 소개 문구 포함
- [x] #2 왜 필요했나/무엇을 만들었나 섹션 분리해서 명확화
- [x] #3 주요 특징에 Python 선택 이유(가독성, 작성자의 Python 생태계 친숙도) 포함
- [x] #4 훅 28개를 Claude Code 생애주기(11개 이벤트) 기준 표로 재구성 — settings.hooks.json 등록과 1:1 대응(41행)
- [x] #5 설치/포인터 섹션은 유지
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README에 '에이전트를 사용하기 위한 개인용 훅 모음집' 소개 문구 추가, 왜 필요했나/무엇을 만들었나 섹션 분리, 주요 특징에 Python 선택 이유(가독성+작성자 친숙도, bash에서 이식) 포함. 훅 28개를 Claude Code 11개 생애주기 이벤트 기준 41행 표로 재구성 — settings.hooks.json의 실제 등록(이벤트/matcher/if)과 python3로 직접 파싱 대조해 1:1 일치 확인. 같은 훅이 여러 이벤트에 걸린 경우(session_logger.py 등) 행마다 반복 나열.
<!-- SECTION:FINAL_SUMMARY:END -->
