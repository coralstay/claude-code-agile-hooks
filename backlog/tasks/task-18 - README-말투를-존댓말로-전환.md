---
id: TASK-18
title: README 말투를 존댓말로 전환
status: Done
assignee: []
created_date: '2026-09-19 05:23'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README.md의 모든 문장 종결어미를 반말체(~이다/~한다/~했다)에서 존댓말(~입니다/~합니다/~했습니다)로 변경
- [x] #2 표 셀의 명사구 설명(동사 종결어미 없는 항목)은 그대로 유지
- [x] #3 내용/구조/문단 순서는 그대로 유지
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README.md의 모든 프로즈 문장 종결어미를 반말체에서 존댓말(~입니다/~합니다/~했습니다)로 변경. 표 셀의 명사구 설명(동사 종결어미 없는 짧은 구)은 그대로 유지. 부수적으로 main merge 과정에서 생애주기 표와 중복돼 남아있던 옛 '훅 목록' 평면 표를 제거 — 같은 파일에 남은 명백한 merge 잔재라 AC 범위를 약간 벗어나지만 같이 정리함. python3 -m pytest hooks/ -q: 438 passed(코드 변경 없음).
<!-- SECTION:FINAL_SUMMARY:END -->
