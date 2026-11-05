---
id: TASK-13
title: 'README: 의도를 최상단으로 재배치'
status: Done
assignee: []
created_date: '2026-09-19 04:32'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 최상단 태그라인을 '의도(Claude와 함께 작업, 내가 의도한 대로 행동하게)' 먼저, '수단(backlog.md+범용 훅)' 나중 순서로 교체
- [x] #2 1장 정의 문단 순서를 '사용자 의도 → 기계적 강제 vs 사람 판단 경계선' 순으로 재배치
- [x] #3 0장 또는 1장에 backlog doc-1/decision-1~5 포인터 추가
- [x] #4 10장 구조적 한계 항목에 draft-1/draft-2 포인터 추가
- [x] #5 2~9,11~12장은 변경하지 않음, 숫자(28/5/23) 잔재 확인
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
최상단 태그라인 + 1장을 '의도(Claude가 내가 의도한 대로 행동하게)' 먼저, '어떻게 구현했는가(기계적 강제 vs 사람 판단)' 나중 순서로 재작성. 0장에 backlog doc-1/decision-1~5 포인터, 10장 두 구조적 한계 항목에 DRAFT-1(codegen 전환 검토)/DRAFT-2(syscall 샌드박스 검토) 포인터 추가. 2~9,11~12장 미변경, 27/22 숫자 잔재 없음(grep 확인), 28/5/23만 존재.
<!-- SECTION:FINAL_SUMMARY:END -->
