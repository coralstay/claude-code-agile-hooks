---
id: TASK-72
title: >-
  사람 서명 판정을 사람 키 지문으로 고정한다(allowed_signers · humanSigners · 로컬
  allowedSignersFile 우회 차단)
status: In Progress
assignee: []
created_date: '2026-11-05T18:54:00Z'
updated_date: '2026-11-06T00:33:00Z'
labels:
  - security
  - workflow
dependencies:
  - TASK-74
references:
  - 'upkeep friction: 사람 서명 판정 설정 미보호'
documentation:
  - ~/.claude/plans/giggly-kindling-snowglobe.md
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
- B6 (AC #7) 서명을 읽는 git 호출은 서명 검증 프로그램도 고정한다(gpg.ssh.program=ssh-keygen, gpg.program=gpg, gpg.x509.program=gpgsm) — 저장소 · 전역 설정과 환경 변수로 검증 프로그램을 바꿔 판정을 지어낼 수 없다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 AI 키를 allowed_signers에 human principal로 올려 서명한 Plan-Approved 커밋을 거부한다
- [x] #2 humanSigners에 AI principal을 넣어도 그 키 지문이 목록에 없으면 거부한다
- [x] #3 저장소 로컬 gpg.ssh.allowedSignersFile을 가짜 파일로 바꿔도 판정이 바뀌지 않는다
- [x] #4 지문 목록에 있는 키의 유효 서명(G)은 통과하고, 거부 메시지가 missing · invalid · not_human(지문 불일치)을 구별한다
- [x] #5 지문 목록 파일이 없거나 비었거나 형식이 틀리면 거부하고 만드는 방법(ssh-keygen -lf <사람 공개키>)을 안내한다
- [x] #6 지문 목록 파일은 훅 파일 옆에서만 읽고, 그 경로 쓰기가 config_guard에 막힘을 테스트로 고정한다
- [x] #7 저장소 로컬 · 전역 설정이나 환경 변수로 gpg.ssh.program · gpg.program · gpg.x509.program을 가짜 프로그램으로 바꿔도 판정이 바뀌지 않는다(가짜가 '사람 지문 G'를 지어내도 거부)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [x] #2 [수동 검증] README · CLAUDE.md.snippet · install.sh 안내에 지문 목록 파일과 만드는 방법을 반영한다
- [x] #3 [수동 검증] 설치 후 실제 저장소에서 사람 키 Plan-Approved는 통과하고 AI 키 서명은 거부됨을 확인한다
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

### 계획 변경(2026-11-06, 유저 결정 — 다시 승인 필요)
구현 검증 중 남은 우회를 재현했다: 저장소 로컬 gpg.ssh.program을 가짜 스크립트로 바꾸면 AI 서명 커밋도 git이 'G + 사람 지문 + human'으로 보고해 지문 판정까지 통과한다. 명령줄 -c gpg.ssh.program=ssh-keygen 고정 시 다시 U(거부). 유저 결정: 맥락상 이 카드에서 막는다.
5. AC #7: 가짜 검증 프로그램 시나리오 테스트 먼저(gpg.ssh.program · gpg.program · gpg.x509.program, 저장소 로컬 · 전역 · 환경 변수) → git_log()에 -c 고정 추가(ssh-keygen은 PATH에서 찾는다 — 훅 프로세스의 PATH는 Claude Code 환경에서 오고 저장소 설정으로 바꿀 수 없음, 판단을 주석에 남김). README 반영.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## 구현과 검증(2026-11-06)
- 구현(서브에이전트): 2b0e96c(AC #1~#5), de39f52(AC #6), 056c825(DoD #2 문서), da099d9(AC #7 검증 프로그램 고정). 테스트: hooks/test_human_signature.py(신규), test_require_implementation_plan.py · test_config_guard.py 갱신
- %GK 실측(git 2.54.0): 유효 서명 G|SHA256:<43자 base64>|principal, allowed_signers에 없으면 U(지문은 보임), 미설정이면 N(지문 빔)
- 메인 세션 독립 검증: 실제 훅 모듈 approval_status에 우회 4겹(allowed_signers에 AI 키를 human으로, 로컬 allowedSignersFile 가짜, 로컬 gpg.ssh.program 가짜, 환경 변수 GIT_CONFIG_COUNT로 gpg.ssh.program 가짜)을 한꺼번에 건 저장소 → 그냥 git은 AI 서명을 'G|사람 지문|human'으로 보고, 훅은 ('not_human', <AI 지문>). 같은 저장소의 사람 서명은 ('approved', <사람 지문>)
- 증거: TASK-72#D1 — 메인 세션 `coverageCommand`: require_implementation_plan.py 100%, TOTAL 5598 stmts · 2318 branches 100%, 2509 passed
- 증거: TASK-72#D2 — README.md(human-signers 4곳, ssh-keygen -lf 예시 L343), CLAUDE.md.snippet L51, install.sh L73(파일이 없거나 비면 안내, 만들지 않음)
- 남은 것(범위 밖, 기록): config_guard 매처는 Bash|Edit|Write라 MultiEdit 같은 다른 편집 도구는 못 봄. 이미 설치된 ~/.claude/CLAUDE.md는 마커 블록이 있어 새 안내 문구가 반영되지 않음(블록 삭제 후 재설치 필요). 이름으로 고정한 ssh-keygen · gpg · gpgsm은 훅 프로세스 PATH를 믿는다(코드 주석). revocationFile · minTrustLevel은 사람 서명을 막을 수만 있고 위조는 못 함. TASK-73이 서명 헬퍼를 복제할 때 dedup REGISTRY 등록

- 증거: TASK-72#D3 — 유저가 install.sh 실행 + human-signers에 사람 서명 키 지문 1줄(`ssh-keygen -lf ~/.ssh/secretive_git_signing.pub`와 일치) 작성, 설치본 4개 파일이 브랜치와 동일(`cmp`). 실전: (1) ~/githubs 아래 임시 backlog 프로젝트에 AI 서명 Plan-Approved + humanSigners에 ai-claude-code 넣고 `backlog task edit TASK-1 -s "In Progress"` → 설치된 훅이 거부(%GK = SHA256:ve62…, ai-claude-code 지문, humanSigners 미사용 안내) (2) 이 저장소 TASK-72(사람 서명 ddf02d7)에서 같은 전환 → 통과
- 발견(범위 밖): 처음엔 /tmp에서 시도했는데 세션 cwd가 ~/githubs로 되돌아가 훅이 backlog 프로젝트가 아니라고 보고 검사 없이 통과시켰다 — 훅이 명령의 대상이 아니라 세션 cwd로 판정하는 문제(TASK-67)라 'cd <다른 저장소> && backlog task edit … -s In Progress'로 승인 검사를 건너뛸 수 있다
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
사람 서명 판정을 사람 키 지문으로 고정했다. Plan-Approved 커밋은 %G? = G이고 서명 키 지문(%GK)이 설치된 훅 옆의 human-signers 목록에 있어야 승인으로 본다. principal 이름과 프로젝트 설정 humanSigners는 더 이상 판정에 쓰지 않는다. 서명을 읽는 git 호출은 allowedSignersFile(/Users/flynn_macpro/.ssh/allowed_signers)과 검증 프로그램(gpg.ssh.program=ssh-keygen, gpg.program=gpg, gpg.x509.program=gpgsm)을 -c로 고정해, 저장소 · 전역 · 환경 변수 설정으로 판정을 바꾸거나 지어낼 수 없다(구현 중 발견한 가짜 검증 프로그램 우회를 유저 결정으로 AC #7에 추가 · 재승인). 지문 목록이 없거나 틀리면 거부(fail-closed)하고 만드는 방법을 안내한다. 커버리지 100%, 설치 후 실전에서 AI 서명 거부 · 사람 서명 통과 확인. 남은 것: 세션 cwd 기준 판정으로 'cd 다른 저장소 &&'가 검사를 건너뜀(TASK-67), config_guard가 MultiEdit 같은 다른 편집 도구를 보지 않음, 기존 ~/.claude/CLAUDE.md 안내 블록은 재설치로 갱신되지 않음.
<!-- SECTION:FINAL_SUMMARY:END -->
