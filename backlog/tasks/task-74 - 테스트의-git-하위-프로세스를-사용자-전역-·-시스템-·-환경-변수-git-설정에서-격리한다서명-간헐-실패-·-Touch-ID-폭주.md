---
id: TASK-74
title: 테스트의 git 하위 프로세스를 사용자 전역 · 시스템 · 환경 변수 git 설정에서 격리한다(서명 간헐 실패 · Touch ID 폭주)
status: To Do
assignee: []
created_date: '2026-11-05T20:31:00Z'
updated_date: '2026-11-05T20:34:00Z'
labels:
  - tests
  - workflow
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 결정(2026-11-06): TASK-72보다 먼저 해결한다. source-header DRAFT-3(테스트 git 격리) 중 이 저장소 분이다.
실측(2026-11-06): 커밋 전 testCommand(pytest -n auto, 2450개)가 매번 1~3개씩 무작위로 실패(git commit exit 128 — test_auto_stage · test_block_stop_if_dirty · test_pre_push_check · test_pre_push_coverage_check 등 임시 저장소에서 커밋하는 테스트). commit.gpgsign=false를 환경으로 넣고 돌리면 2회 모두 2450 passed, 그대로는 2회 모두 1 failed. 원인: 테스트의 git이 전역 commit.gpgsign=true와 Claude Code 환경의 GIT_CONFIG_COUNT/KEY/VALUE(user.signingkey=AI 키)를 물려받아 테스트 커밋마다 Secretive 서명을 요청하고, 병렬로 몰리면 실패한다. 사람 터미널에서는 테스트 커밋마다 Touch ID 창이 뜬다. 이 때문에 이 저장소의 커밋이 절반쯤 막힌다.
주의: GIT_CONFIG_GLOBAL을 비워도 환경 변수 설정(GIT_CONFIG_COUNT · GIT_CONFIG_PARAMETERS)은 계속 적용되므로 함께 지워야 한다.

## 비즈니스 규칙
- B1 (AC #1) 테스트 중 실행되는 git은 사용자 전역 · 시스템 설정과 환경 변수 설정(GIT_CONFIG_COUNT/KEY_n/VALUE_n, GIT_CONFIG_PARAMETERS)을 읽지 않는다
- B2 (AC #3) 서명을 다루는 테스트는 테스트 안에서 명시한 키 · 설정만 쓴다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 hooks/conftest.py의 autouse 픽스처가 GIT_CONFIG_GLOBAL을 빈 임시 파일로, GIT_CONFIG_NOSYSTEM=1로 두고 GIT_CONFIG_COUNT · GIT_CONFIG_KEY_n · GIT_CONFIG_VALUE_n · GIT_CONFIG_PARAMETERS를 지운다
- [ ] #2 격리를 확인하는 테스트: 전역 · 환경 변수로 commit.gpgsign=true와 존재하지 않는 서명 키를 넣은 상태에서도 테스트 안의 git commit이 성공하고 git config로 그 값이 보이지 않는다
- [ ] #3 이미 자체 격리하던 테스트(test_require_implementation_plan · test_pre_git_safety_check · test_hook_runtime_contract)는 그대로 통과하고, 서명 테스트는 테스트가 명시한 키만 쓴다
- [ ] #4 [수동 검증] Claude Code 환경에서 testCommand(pytest -n auto) 전체를 5회 연속 돌려 실패가 없다
- [ ] #5 [수동 검증] 사람 터미널에서 테스트를 돌려도 Touch ID 요청이 뜨지 않는다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 [수동 검증] install.sh가 conftest.py를 설치본에 함께 복사하는지 확인하고(설치본 옆 테스트 실행 시에도 격리), 필요하면 반영한다
- [ ] #3 [수동 검증] source-header DRAFT-3에 이 저장소 분 완료를 기록한다(commit-tool 분은 그쪽 카드)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-11-06 '먼저 해결하자'고 정했다. 커밋마다 도는 testCommand가 서명 설정 때문에 간헐 실패해 이 저장소 커밋이 절반쯤 막히고, TASK-72(서명 판정)의 테스트도 격리된 git이 필요하다.

### Objective
- hooks/에 conftest.py가 없다. git을 실행하는 테스트 파일이 13개 이상이고, 대부분 subprocess.run(['git', ...])로 사용자 설정을 그대로 물려받는다.
- 이미 격리하는 곳: test_require_implementation_plan.py L107(GIT_CONFIG_GLOBAL · NOSYSTEM), test_pre_git_safety_check.py L17, test_hook_runtime_contract.py L255.
- Claude Code 환경은 settings.json env로 GIT_CONFIG_COUNT=1 · user.signingkey=AI 키를 넣고, 전역 설정은 commit.gpgsign=true다. 환경 변수 설정은 GIT_CONFIG_GLOBAL보다 우선한다.
- 실측: commit.gpgsign=false를 환경으로 주면 2회 모두 2450 passed, 그대로면 매번 1~3 failed.

### Assessment
테스트마다 고치는 대신 hooks/conftest.py autouse 픽스처 하나로 모든 테스트의 git 하위 프로세스를 격리한다(monkeypatch.setenv/delenv라 테스트 끝나면 원복). 자체 격리 테스트는 같은 변수를 다시 설정하므로 충돌하지 않는다. 훅 본체는 바꾸지 않는다 — 실제 사용 중 훅은 사용자 설정을 읽어야 한다. 설치본은 hooks/*.py를 복사하므로 conftest.py도 따라간다(확인만).

### Plan
1. AC #2 테스트 먼저(오염된 전역 · 환경 변수 설정 아래에서 git commit 성공, 값 비노출) → 실패 확인.
2. AC #1: hooks/conftest.py 작성 → AC #2 통과.
3. AC #3: 전체 실행으로 기존 격리 테스트 확인, coverageCommand 100%.
4. AC #4 · #5: 5회 연속 실행 로그, 사람 터미널 확인(유저).
<!-- SECTION:PLAN:END -->
