---
id: DRAFT-10
title: >-
  사람 서명 판정을 사람 키 지문으로 고정한다(allowed_signers · humanSigners · 로컬
  allowedSignersFile 우회 차단)
status: Draft
assignee: []
created_date: '2026-11-05T18:54:00Z'
updated_date: '2026-11-05T20:10:00Z'
labels:
  - security
  - workflow
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 결정(2026-11-06): 운영 카드 Done 게이트 재설계 계획(~/.claude/plans/giggly-kindling-snowglobe.md 2절 A). 지금 require_implementation_plan은 Plan-Approved 커밋의 %G?=G와 서명자 principal(%GS)이 프로젝트 설정 humanSigners에 있는지로 사람 서명을 판정한다. 그런데 ~/.ssh/allowed_signers, 저장소의 .claude-code-agile-hooks.json(humanSigners), .git/config의 gpg.ssh.allowedSignersFile은 config_guard 보호 대상이 아니라 에이전트가 고칠 수 있다.
우회 경로: A1 AI 키를 allowed_signers에 human principal로 추가, A2 humanSigners에 AI principal 추가, A3 저장소 로컬 설정으로 allowedSignersFile을 가짜 파일로 바꿈.

## 제안
- 사람 키 지문(SHA256:…) 목록을 ~/.claude/hooks/claude-code-agile-hooks/human-signers에 둔다(config_guard 보호 위치, 유저만 작성)
- 사람 서명 = %G? = G 이고 %GK가 지문 목록에 있음. principal 이름 · humanSigners로 판정하지 않는다
- 훅의 git 호출은 -c gpg.ssh.allowedSignersFile=$HOME/.ssh/allowed_signers로 저장소 로컬 설정을 무시한다
- 지문 파일이 없거나 형식이 틀리면 거부하고 만드는 방법(ssh-keygen -lf <사람 공개키>)을 안내한다
- 같은 판정을 수동 검증 게이트(Manual-Verified, 별도 카드)도 쓴다
## 비즈니스 규칙
- B1 (AC #1) 사람 서명은 %G? = G 이고 서명 키 지문(%GK)이 사람 키 지문 목록에 있을 때만이다
- B2 (AC #2) 서명자 principal(%GS)과 프로젝트 설정 humanSigners는 사람 서명 판정에 쓰지 않는다
- B3 (AC #3) 서명을 읽는 git 호출은 저장소 · 전역 설정과 무관하게 gpg.ssh.allowedSignersFile=$HOME/.ssh/allowed_signers를 쓴다
- B4 (AC #5) 지문 목록 파일이 없거나 비었거나 형식이 틀리면 승인 게이트는 거부한다(fail-closed)
- B5 (AC #6) 지문 목록 파일은 설치된 훅과 같은 디렉터리(~/.claude/hooks/claude-code-agile-hooks/human-signers)에서만 읽는다 — 환경 변수 · 프로젝트 설정으로 경로를 바꿀 수 없다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AI 키를 allowed_signers에 human principal로 올려 서명한 Plan-Approved 커밋을 거부한다
- [ ] #2 humanSigners에 AI principal을 넣어도 그 키 지문이 목록에 없으면 거부한다
- [ ] #3 저장소 로컬 gpg.ssh.allowedSignersFile을 가짜 파일로 바꿔도 판정이 바뀌지 않는다
- [ ] #4 지문 목록에 있는 키의 유효 서명(G)은 통과하고, 거부 메시지가 missing · invalid · not_human(지문 불일치)을 구별한다
- [ ] #5 지문 목록 파일이 없거나 비었거나 형식이 틀리면 거부하고 만드는 방법(ssh-keygen -lf <사람 공개키>)을 안내한다
- [ ] #6 지문 목록 파일은 훅 파일 옆에서만 읽고, 그 경로 쓰기가 config_guard에 막힘을 테스트로 고정한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 [수동 검증] README · CLAUDE.md.snippet · install.sh 안내에 지문 목록 파일과 만드는 방법을 반영한다
- [ ] #3 [수동 검증] 설치 후 실제 저장소에서 사람 키 Plan-Approved는 통과하고 AI 키 서명은 거부됨을 확인한다
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-11-06 사람 서명 판정의 우회 경로(A1~A3)를 모두 막기로 했다(계획 ~/.claude/plans/giggly-kindling-snowglobe.md 2절 A). 수동 검증 게이트(DRAFT-11)도 같은 판정을 쓴다.

### Objective
- hooks/require_implementation_plan.py human_signers()(L126)가 프로젝트 설정 humanSigners를 읽고, approval_status()(L360)가 git log --format=%G?%x00%GS로 상태와 principal을 읽어 principal이 humanSigners에 있으면 승인으로 본다.
- git_log()는 저장소 · 전역 git 설정을 그대로 따른다 → 로컬 allowedSignersFile 변경이 판정에 영향.
- config_guard.py는 ~/.claude/hooks/ 아래 쓰기를 막지만 ~/.ssh/allowed_signers · .claude-code-agile-hooks.json · .git/config는 막지 않는다.
- dedup_drift_guard.REGISTRY가 훅 사이에 복제된 함수의 동일성을 검사한다.

### Assessment
판정 기준을 서명 키 지문(%GK)으로 바꾸면 allowed_signers · humanSigners를 바꿔도 속일 수 없다(SSH 서명은 키 없이 위조 불가). 지문 목록은 config_guard가 이미 보호하는 훅 디렉터리에 둔다. 경로를 환경 변수로 열면 우회가 생기므로 __file__ 기준으로만 찾는다(테스트는 훅을 임시 디렉터리에 복사해 지문 파일을 둔다). humanSigners는 하위 호환을 위해 읽기만 하고 판정에 쓰지 않으며, 메시지에서 '더 이상 쓰지 않음'을 안내한다. 서명 조회 함수(human_signature)는 DRAFT-11의 Manual-Verified와 card_gate.py가 그대로 복제해 쓰므로 REGISTRY에 올린다.

### Plan
1. AC #1~#4: 테스트 먼저 — 임시 저장소에 사람 · AI 테스트 키(ssh-keygen)로 서명, allowed_signers 조작 · humanSigners 조작 · 로컬 allowedSignersFile 조작 시나리오. 그다음 approval_status를 %G?%x00%GK 기준으로 바꾸고 git 호출에 -c gpg.ssh.allowedSignersFile 고정.
2. AC #5 · #6: 지문 파일 로딩(형식: 한 줄에 SHA256:… 하나, # 주석 허용) · fail-closed 메시지 테스트 → 구현. config_guard 테스트에 human-signers 경로 쓰기 차단 추가.
3. REGISTRY에 human_signature 등록, README · CLAUDE.md.snippet · install.sh 안내, coverageCommand 100%.
4. 유저가 install.sh 실행 · 지문 파일 작성 → 실제 저장소에서 확인(DoD #3).
<!-- SECTION:PLAN:END -->
