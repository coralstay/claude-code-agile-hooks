---
id: DRAFT-8
title: Sigkill Foundry 형식 설계 문서와 훅의 세 가지 성격
status: Draft
assignee: []
created_date: '2026-10-05 11:47'
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
