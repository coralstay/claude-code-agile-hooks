---
id: TASK-19
title: README 어투를 더 정중한 존댓말로 재작성 + 훅 목록 2곳에 실제 파일 링크 추가
status: Done
assignee: []
created_date: '2026-09-19 05:29'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README.md 전체를 겸손하고 정중한 존댓말(경어체)로 다시 작성 — 단순 -습니다 종결을 넘어 정중한 어휘/문장 구조 사용
- [x] #2 README.md의 생애주기 표에서 각 훅 이름을 hooks/<파일명> 상대경로 링크로 연결
- [x] #3 backlog doc-2의 8장 훅 스펙 표(이벤트별 여러 섹션)에서도 각 훅 이름을 hooks/<파일명> 링크로 연결(doc-2 위치 기준 상대경로)
- [x] #4 내용/구조/정보는 그대로 유지, 링크가 실제로 유효한 파일을 가리키는지 확인
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README.md 전체를 겸손하고 정중한 경어체로 재작성 — 단순 -습니다 종결을 넘어 '말씀드립니다', '소개해 드립니다', '~하였습니다' 등 정중한 어휘/문장 구조 사용. README의 생애주기 표(41행)와 doc-2 8장의 이벤트별 훅 스펙 표(41행) 양쪽 모두 훅 이름을 hooks/<파일명> 상대경로 링크로 변경(doc-2는 backlog/docs/reference/ 기준 ../../../hooks/ 상대경로). python3 스크립트로 일괄 치환 후 모든 링크 대상 파일이 실제로 존재하는지 확인. 내용/구조는 그대로 유지, 전체 테스트 438 passed(코드 변경 없음).
<!-- SECTION:FINAL_SUMMARY:END -->
