---
id: DRAFT-10
title: >-
  pre_git_safety_check: gh api · GraphQL로 main에 직접 쓰는 경로(merges · git/refs ·
  contents PUT · 자동 병합)도 막는다
status: Draft
assignee: []
created_date: '2026-11-05T22:10:00Z'
labels:
  - security
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 확인(2026-11-06): PR #1 병합을 'gh pr merge'로 하려다 pre_git_safety_check에 막혔다(의도대로). 점검해 보니 gh api 규칙(GH_API_RULES · GH_GRAPHQL_MUTATIONS)은 pulls/<n>/merge · 저장소/릴리스 삭제 · PR/이슈 닫기만 다루고, main에 직접 쓰는 다른 API 경로는 통과한다. 지금 새 저장소는 모두 private이라 GitHub 쪽 main 보호(ruleset)가 없어, 이 경로들이 실제로 main을 바꿀 수 있다.

## 통과하는 경로(코드의 규칙 목록으로 확인, 실행해 보지 않음)
- POST repos/<o>/<r>/merges — 브랜치를 기본 브랜치에 직접 병합
- PATCH · POST repos/<o>/<r>/git/refs(/heads/<기본 브랜치>) — ref를 직접 이동 · 생성
- PUT · DELETE repos/<o>/<r>/contents/<path> — 기본 브랜치에 커밋 생성
- GraphQL enablePullRequestAutoMerge · mergeBranch · updateRef · updateRefs · createCommitOnBranch
- 규칙 자체 · 보호 해제: DELETE · PUT repos/<o>/<r>/rulesets/<id>, branches/<b>/protection

## 한계(이 카드로 못 막음, 기록만)
curl + gh auth token, 스크립트 · bash -c · eval 안의 호출, SSH 키로 하는 git push 변형은 문자열 판정으로 다 막을 수 없다. 근본 대책은 GitHub 쪽 보호(public ruleset 또는 유료 요금제)와 에이전트 전용 자격 증명 — upkeep TASK-5(보안 기준선)에서 정한다.

## AC 후보
1. 위 REST 경로를 GET이 아닌 메서드로 부르면 거부한다(GH_API_RULES 확장)
2. 위 GraphQL mutation 이름이 든 요청을 거부한다
3. 같은 경로의 GET(조회)은 통과한다
4. README의 Known gaps에 curl · 스크립트 · SSH push 한계와 GitHub 쪽 보호가 근본 대책임을 적는다
<!-- SECTION:DESCRIPTION:END -->
