---
id: DRAFT-10
title: 테스트의 git 하위 프로세스를 사용자 전역 · 시스템 · 환경 변수 git 설정에서 격리한다(서명 간헐 실패 · Touch ID 폭주)
status: Draft
assignee: []
created_date: '2026-11-05T20:31:00Z'
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
