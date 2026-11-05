---
id: TASK-5
title: README 목적 재정의 + 1장 재작성
status: Done
assignee: []
created_date: '2026-09-18 16:12'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - README.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README 1장("왜 이게 있는가")을 "기계적으로 검증 가능한 규칙은 훅으로 물리적 강제, 판단이 필요한 지점(Phase 2 백로그 승인 / Phase 4.3 push 전 코드 리뷰)은 정직하게 사람에게 남긴다"는 경계선을 프로젝트 정의의 핵심으로 재서술한다. 27개 훅이 backlog.md 전용 5개 + 범용 보안/관측 22개로 나뉜다는 점도 "워크플로 준수 도구"가 아니라 "Claude의 모든 행동에 대한 보안 경계"라는 더 넓은 프레이밍으로 다시 쓴다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README 1장에 기계적 강제 vs 사람 판단(Phase 2/4.3)의 경계선을 프로젝트 정의 핵심으로 명시
- [x] #2 27개 훅 구성을 워크플로 준수 도구가 아닌 Claude의 모든 행동에 대한 보안 경계라는 프레이밍으로 재서술
- [x] #3 사용자 정의(이상한 방향 억제 + 보안 위협 방어 + 의도대로 동작)와 위 프레이밍을 통합
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README 1장을 재작성해 '기계적으로 검증 가능한 규칙은 훅으로 물리적 강제, 판단이 필요한 Phase 2 백로그 승인/Phase 4.3 push 전 코드 리뷰는 사람에게 남긴다'는 경계선을 프로젝트 정의 핵심으로 세우고, 27개→28개 훅(범용 22→23개, dedup_drift_guard.py 반영)을 '워크플로 준수 도구'가 아닌 'Claude의 모든 행동에 대한 보안 경계'로 재프레이밍했다. 사용자의 정의와 Claude의 관점(우회 불가능한 코드로 규칙 이전)을 하나의 문단으로 통합했다. 1/2/3/5/8/12장 전체에서 27→28, 22→23 숫자를 일관되게 갱신했고, 8장 Bash matcher 표에 누락돼 있던 dedup_drift_guard.py 행을 pre_commit_check.py 근처에 추가했다. 8장/10장의 기존 스펙 내용은 건드리지 않았다.
<!-- SECTION:FINAL_SUMMARY:END -->
