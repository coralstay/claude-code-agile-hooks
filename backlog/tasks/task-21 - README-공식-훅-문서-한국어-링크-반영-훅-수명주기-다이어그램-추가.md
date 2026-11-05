---
id: TASK-21
title: 'README: 공식 훅 문서 한국어 링크 반영 + 훅 수명주기 다이어그램 추가'
status: Done
assignee: []
created_date: '2026-09-19 12:49'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README.md의 Claude Code hooks 공식 문서 링크를 한국어 버전(https://code.claude.com/docs/ko/hooks)으로 갱신
- [x] #2 훅 생애주기 표(훅 리스트) 언급 전에 Mermaid 기반 훅 수명주기 다이어그램 삽입
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README.md의 hooks 공식 문서 링크를 영어(/docs/en/hooks)에서 한국어(/docs/ko/hooks)로 2곳(19번째 줄, '훅을 생애주기별로 정리해 드립니다' 문단) 모두 갱신했다. 훅 생애주기 표(리스트) 바로 앞에 Mermaid flowchart를 삽입 — 세션 생애주기(SessionStart/SessionEnd), 대화 루프(UserPromptSubmit→Claude 처리→도구 호출 서브그래프[PreToolUse/PermissionRequest/도구실행/PostToolUse/PostToolUseFailure]→Stop), 그 외 이벤트(PreCompact/InstructionsLoaded/ConfigChange) 3개 그룹으로 11개 공식 이벤트 전체 흐름을 표현했다. mermaid 라벨에 CLAUDE.md처럼 마침표가 든 문자열이 들어가면 dotted-edge 라벨 구분자(.-> )와 충돌할 수 있어 '지침 파일 로드 시'로 순화했다.
<!-- SECTION:FINAL_SUMMARY:END -->
