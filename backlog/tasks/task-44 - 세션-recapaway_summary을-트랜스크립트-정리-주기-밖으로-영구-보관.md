---
id: TASK-44
title: 세션 recap(away_summary)을 트랜스크립트 정리 주기 밖으로 영구 보관
status: To Do
assignee:
  - '@claude'
created_date: '2026-09-24 11:19'
updated_date: '2026-10-03 12:39'
labels:
  - hooks
  - observability
dependencies:
  - TASK-43
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 왜

Claude Code가 턴 끝에 회색으로 보여주는 recap은 세션 트랜스크립트에 'type: system, subtype: away_summary' 레코드로 저장된다. 화면에서만 사라지는 게 아니라 ~/.claude/projects/<프로젝트 슬러그>/<sessionId>.jsonl 안에 gitBranch와 timestamp까지 붙어 남는다.

문제는 보존 기간이다. settings.json의 cleanupPeriodDays(기본 30일)가 지나면 트랜스크립트 파일 자체가 지워지고 recap도 같이 사라진다. 실측(git-format 저장소, 2026-09-24)으로 확인한 결과 세션 파일 9개에 recap 13건이 남아 있었지만, 저장소 첫날(8/24, 31일 전) 세션은 이미 사라진 뒤였고 예전 경로 슬러그 디렉터리는 비어 있었다.

recap은 세션 간 인수인계 로그로 쓸 만한 밀도를 가진다 - '어느 브랜치에서 무엇을 하다 멈췄는지'가 한 줄로 들어 있다. 30일 뒤 통째로 날아가게 두는 건 아깝다.

## 무엇을

SessionStart(또는 SessionEnd) 훅에서 이 저장소의 훅 규약대로 away_summary 레코드만 긁어 append-only 로그로 적재한다. 스케치:

- ~/.claude/projects/*/*.jsonl 을 훑어 subtype이 away_summary인 줄만 추출
- (sessionId, uuid) 기준 중복 제거 - 같은 세션이 여러 번 열려도 한 번만 적재
- timestamp, gitBranch, cwd, content를 한 줄 JSONL로 ~/.claude/recap-archive.jsonl 에 append
- 조회용 얇은 CLI 하나(프로젝트별/기간별 필터)

## 검토해야 할 것

- 적재 시점: SessionStart가 맞는지(직전 세션 recap이 이미 기록된 뒤인지) 아니면 SessionEnd/Stop이 맞는지 실측 필요
- 트랜스크립트가 이미 지워진 뒤에는 복구 불가 - 이 훅을 붙이기 전 구간은 포기해야 한다
- recap을 /config에서 끈 상태면 애초에 생성되지 않으므로 적재할 것도 없다
- 이 저장소의 훅은 Python으로 포팅된 상태이니 Python으로 작성한다
- 프라이버시: recap 본문에 작업 내용이 그대로 들어가므로 홈 디렉터리 밖으로 내보내지 않는다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 away_summary 레코드를 (sessionId, uuid) 기준 중복 없이 append-only JSONL로 적재하는 훅을 만든다
- [ ] #2 적재 시점(SessionStart/SessionEnd)을 실측으로 정하고 근거를 남긴다
- [ ] #3 프로젝트·기간 필터로 조회하는 얇은 CLI를 둔다
- [ ] #4 테스트(커버리지 100% 유지)를 추가하고 설치본을 갱신한다
<!-- AC:END -->
