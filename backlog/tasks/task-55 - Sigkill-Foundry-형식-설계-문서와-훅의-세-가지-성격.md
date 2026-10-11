---
id: TASK-55
title: Sigkill Foundry 형식 설계 문서와 훅의 세 가지 성격
status: Done
assignee: []
created_date: '2026-10-05 11:47'
updated_date: '2026-10-10 22:38'
labels:
  - docs
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
최상위 Sigkill Foundry 설계 문서와 같은 5문서 세트(design/: 0 문서 정보, 1 제안서 ~ 5 구현 결과 보고서, 부록)를 이 저장소에 세우고, Claude 앱 문서를 편집 원본으로 둔다. 이번에 채우는 장: 1.01 배경과 문제(CLAUDE.md의 약속을 코드로 강제), 1.02 원칙, 3.01 시스템 구성(훅의 세 가지 성격: ① 절차 강제 — 애자일(스크럼·칸반) 의식 ↔ 훅 대응표 ② 품질·안전 게이트 — CI 품질 게이트·DevSecOps ③ 기록·관측 — 스탠드업·회고·부채 기록; 32개 훅 분류표와 DOT 다이어그램), 4.03 미결 사항(config_guard 우회, pre_compact_backup 한계). 나머지 장은 골격.

수용 기준(승격 시 AC로 등록):
1. design/ 구조·장 형식이 최상위 Sigkill Foundry와 같다
2. 3.01에 세 가지 성격과 32개 훅 분류표(누락·중복 없음, 근거는 각 훅 docstring)와 DOT 다이어그램이 있다
3. 1.01 · 1.02 · 4.03을 채우고 나머지는 골격으로 둔다, 진척 서술 없음
4. Claude 앱에 장별 문서와 목차 문서를 만들고 design/README.md에 링크한다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 design/ 구조·장 형식이 최상위 Sigkill Foundry와 같다
- [x] #2 3.01에 세 가지 성격과 32개 훅 분류표(누락·중복 없음, 근거는 각 훅 docstring)와 DOT 다이어그램이 있다
- [x] #3 1.01 · 1.02 · 4.03을 채우고 나머지는 골격으로 둔다, 진척 서술 없음
- [x] #4 설계 문서의 원본은 design/ 하나다 — Claude 앱 편집 원본 문구 · 링크 칸을 두지 않고, 목차 상태는 실제 파일 기준
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
최상위 Sigkill Foundry와 같은 5문서 설계 세트(design/)를 세웠다. 장 파일 구성은 최상위와 diff로 일치.
- 1.01 배경과 문제(규율 레이어, 최상위 3.03 §2), 1.02 원칙 P-1~P-5, 3.01 시스템 구성(훅의 세 가지 성격: ① 절차 강제 8 ② 품질·안전 게이트 12 ③ 기록·관측 12, 32개 훅 분류표와 근거, 두 성격에 걸친 11개 설명, 생애주기 DOT 다이어그램 — 연결선 50개 = settings.hooks.json 등록 50건), 4.03 미결 Q-1~Q-14. 나머지는 골격.
- 요구사항 ID는 최상위 번호만 쓴다. 분류에서 드러난 4개를 최상위 2.03에 RAIL-015~018로 올리고 반영.
- 원본은 design/ 하나(Claude 앱 편집 원본 규칙 없음).
- 발견: session_id를 경로에 그대로 쓰는 훅이 pre_compact_backup 외 4개 더 있음(4.03 Q-3).
- 검증: 테스트 1695 통과.
<!-- SECTION:FINAL_SUMMARY:END -->
