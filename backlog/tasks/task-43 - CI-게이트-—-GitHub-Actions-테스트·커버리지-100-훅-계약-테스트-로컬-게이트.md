---
id: TASK-43
title: CI 게이트 — GitHub Actions 테스트·커버리지 100% + 훅 계약 테스트 + 로컬 게이트
status: To Do
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 17:51'
labels:
  - ci
  - tests
dependencies:
  - TASK-42
  - TASK-47
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
훅은 Claude Code가 실제로 subprocess로 실행한다. 단위 테스트는 main()을 직접 부르므로 '설치·등록된 형태로 제대로 동작하는가'는 검증하지 못한다. 그래서 (1) settings.hooks.json에 등록된 모든 명령을 실제 subprocess로 실행하는 계약 테스트, (2) PR·push마다 테스트와 커버리지 100%를 강제하는 GitHub Actions, (3) 이 저장소 자체에 .claude-rails.json(testCommand·coverageCommand)을 둬 pre_commit_check/pre_push_coverage_check가 로컬에서도 같은 게이트를 걸게 한다(도그푸딩).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 계약 테스트: settings.hooks.json의 모든 명령이 가리키는 파일이 존재하고 각 훅에 테스트 파일이 있다
- [ ] #2 계약 테스트: 모든 훅을 실제 subprocess로 빈 stdin·깨진 JSON·정상 payload로 실행해 크래시 없이 정해진 종료 코드(0 또는 의도된 2)를 낸다 — 실제 HOME을 건드리지 않는다
- [ ] #3 GitHub Actions 워크플로가 PR·main push마다 테스트와 커버리지 100%(미달 시 실패)를 돌린다
- [ ] #4 이 저장소에 .claude-rails.json(testCommand, coverageCommand)을 두고 README·doc-2에 CI·로컬 게이트를 문서화한다
- [ ] #5 동시에 두 번 실행하거나 병렬(pytest-xdist)로 실행해도 통과한다 — 테스트가 tmp 밖 공유 경로를 쓰지 않는다(2026-10-04 동시 실행 중 1회 실패 관측)
<!-- AC:END -->
