---
id: TASK-42
title: 훅 테스트 커버리지 100% (2/2) — 나머지 훅·scripts·커버리지 설정
status: In Progress
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 17:51'
labels:
  - tests
  - coverage
dependencies:
  - TASK-41
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
(1/2) 이후 남은 훅과 scripts/merge_settings.py의 미커버를 채운다. if __name__ == '__main__' 진입점은 coverage 설정에서 제외하고(표준 관행), merge_settings.py CLI는 subprocess 대신 main()을 직접 호출하는 테스트로 측정되게 한다. 커버리지 설정 파일(.coveragerc 또는 pyproject.toml)에 측정 대상·제외 규칙·fail_under=100을 둔다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 저장소 루트에서 hooks·scripts 전체의 줄·분기 커버리지가 100%다
- [ ] #2 커버리지 설정 파일에 측정 대상·제외 규칙·fail_under=100이 있다
- [ ] #3 추가한 테스트는 각각 해당 분기의 기대 동작을 단언한다
<!-- AC:END -->
