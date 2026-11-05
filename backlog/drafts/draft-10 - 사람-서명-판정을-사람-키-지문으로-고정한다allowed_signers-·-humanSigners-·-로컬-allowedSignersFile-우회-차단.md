---
id: DRAFT-10
title: >-
  사람 서명 판정을 사람 키 지문으로 고정한다(allowed_signers · humanSigners · 로컬
  allowedSignersFile 우회 차단)
status: Draft
assignee: []
created_date: '2026-11-05T18:54:00Z'
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

## AC 후보
1. AI 키를 allowed_signers에 human으로 넣어 서명한 Plan-Approved를 거부한다
2. humanSigners에 AI principal이 있어도 지문이 없으면 거부한다
3. 저장소 로컬 gpg.ssh.allowedSignersFile을 바꿔도 판정이 바뀌지 않는다
4. 지문이 맞는 사람 서명은 통과한다
5. 지문 파일 없음 · 형식 오류는 거부하고 설정 방법을 안내한다
6. README · CLAUDE.md.snippet · install.sh 안내 갱신, 커버리지 100%
<!-- SECTION:DESCRIPTION:END -->
