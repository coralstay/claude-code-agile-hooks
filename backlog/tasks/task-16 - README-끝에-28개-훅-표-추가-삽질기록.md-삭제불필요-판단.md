---
id: TASK-16
title: README 끝에 28개 훅 표 추가 + 삽질기록.md 삭제(불필요 판단)
status: Done
assignee: []
created_date: '2026-09-19 04:55'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README.md 끝에 28개 훅을 이름+한줄설명 표로 추가 (backlog 전용 5개 / 범용 23개 구분)
- [x] #2 삽질기록.md 삭제
- [x] #3 README.md, doc-2의 삽질기록.md에 대한 살아있는 링크/포인터 제거 (doc-1/decision-2 등 과거 회고성 언급은 역사적 기록이라 유지)
- [x] #4 hooks/dedup_drift_guard.py, hooks/test_dedup_registry.py의 '삽질기록.md' 참조 주석/메시지를 파일이 사라져도 뜻이 통하게 자체완결형으로 수정
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README 끝에 28개 훅(backlog 전용 5 + 범용 23)을 이름+한줄설명 표로 추가. 삽질기록.md은 필요없다는 판단에 따라 삭제하고, README/doc-2의 살아있는 링크를 제거했다. hooks/dedup_drift_guard.py와 hooks/test_dedup_registry.py의 주석/assert 메시지가 삭제된 파일을 가리키던 걸 decision-2(backlog)를 가리키도록 자체완결형으로 고쳤다. doc-1/decision-2의 회고성 언급은 당시 사실을 기록한 것이라 그대로 유지.
<!-- SECTION:FINAL_SUMMARY:END -->
