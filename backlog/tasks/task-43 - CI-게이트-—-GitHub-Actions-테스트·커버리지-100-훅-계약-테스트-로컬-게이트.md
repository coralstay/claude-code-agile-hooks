---
id: TASK-43
title: CI 게이트 — GitHub Actions 테스트·커버리지 100% + 훅 계약 테스트 + 로컬 게이트
status: Done
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 18:35'
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
- [x] #1 계약 테스트: settings.hooks.json의 모든 명령이 가리키는 파일이 존재하고 각 훅에 테스트 파일이 있다
- [x] #2 계약 테스트: 모든 훅을 실제 subprocess로 빈 stdin·깨진 JSON·정상 payload로 실행해 크래시 없이 정해진 종료 코드(0 또는 의도된 2)를 낸다 — 실제 HOME을 건드리지 않는다
- [x] #3 GitHub Actions 워크플로가 PR·main push마다 테스트와 커버리지 100%(미달 시 실패)를 돌린다
- [x] #4 이 저장소에 .claude-rails.json(testCommand, coverageCommand)을 두고 README·doc-2에 CI·로컬 게이트를 문서화한다
- [x] #5 동시에 두 번 실행하거나 병렬(pytest-xdist)로 실행해도 통과한다 — 테스트가 tmp 밖 공유 경로를 쓰지 않는다(2026-10-04 동시 실행 중 1회 실패 관측)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #3(CI)은 워크플로 추가·actionlint·check-jsonschema 검증까지 완료, GitHub에서 PR 실행으로 확인 전이라 미체크. 동시 실행 실패 원인: backlog_commit_scope 임시 인덱스 copyfile이 mtime을 새로 찍어 git racy 판정이 사라짐 → copy2로 수정(결정적 재현 테스트 추가). 검증: 순차 --cov 1575 passed 100%, xdist -n auto --cov 100%, 3개 동시 xdist×3회·순차+xdist 동시 모두 통과, py3.11/3.13 100%, 최소 PATH(backlog·gh·ruff 없음)+빈 HOME에서 100%.

2026-10-04 PR #39에서 첫 CI 실행: test (ubuntu-latest, py3.11/3.12), test (macos-latest, py3.11/3.12) 4개 모두 pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CI 게이트와 훅 실행 계약을 만들었다. test_hook_runtime_contract.py(151건): 등록 명령↔파일↔테스트 파일 대응, 그리고 모든 등록 훅을 install.sh처럼 임시 HOME에 복사해 등록된 명령 문자열 그대로 sh -c로 빈 입력·깨진 JSON·이벤트별 정상 payload로 실행해 트레이스백 없음·종료 코드 0·임시 디렉토리 밖 쓰기 없음을 단언(주입한 쓰기·import 크래시를 잡는 것 확인). 동시 실행 간헐 실패를 재현해 원인을 찾았다 — backlog_commit_scope가 인덱스를 shutil.copyfile로 복사해 mtime이 바뀌면서 같은 초의 같은 크기 수정을 git이 racy로 보지 않아 git add -A 재현이 놓치는 실제 미탐. copy2로 수정하고 결정적 재현 테스트 추가. nerf_receipts 읽기 불가 테스트를 chmod 0 대신 PermissionError 주입으로 바꿔 root에서도 통과. .github/workflows/ci.yml: push(main)·PR, ubuntu·macOS × Python 3.11·3.12, contents: read, bash -n install.sh, JSON 검증, xdist 병렬 + 커버리지 100% 게이트. 로컬 게이트 .claude-rails.json(testCommand: 커밋마다 약 12초, coverageCommand: push마다). 1575 passed, 커버리지 100%(직렬·xdist·동시 3중 실행 반복 모두 통과, Python 3.11·3.13 확인). AC #3(GitHub에서의 실제 CI 실행)은 PR 실행 결과로 확인 후 체크한다.
<!-- SECTION:FINAL_SUMMARY:END -->
